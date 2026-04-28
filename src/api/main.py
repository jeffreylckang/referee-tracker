"""
Referee Tracker API — FastAPI backend.

Endpoints:
    GET /api/filters           — available seasons, foul types, teams
    GET /api/graph             — aggregated nodes + links for network graph
    GET /api/referees          — all referees ranked by foul count
    GET /api/players           — all players ranked by foul count
    GET /api/referee/{id}      — referee detail + top players fouled
    GET /api/player/{id}       — player detail + top referees

Common filter params (where supported):
    season      — e.g. "2024-25"
    game_type   — "regular" | "playoff"
    foul_detail — e.g. "shooting" | "technical" | etc.

Run locally:
    DATABASE_URL=... uvicorn src.api.main:app --reload
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from .db import get_conn

app = FastAPI(title="Referee Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# game_type SQL fragment reused across queries
# regular = no playoff_round; playoff = has playoff_round
GAME_TYPE_CLAUSE = """
    AND (%(game_type)s IS NULL
         OR (%(game_type)s = 'regular' AND g.playoff_round IS NULL)
         OR (%(game_type)s = 'playoff' AND g.playoff_round IS NOT NULL))
"""

# ---------------------------------------------------------------------------
# /api/filters
# ---------------------------------------------------------------------------

@app.get("/api/filters")
def get_filters():
    conn = get_conn()
    cur  = conn.cursor()

    cur.execute("SELECT DISTINCT season FROM games WHERE season IS NOT NULL ORDER BY season")
    seasons = [r["season"] for r in cur.fetchall()]

    cur.execute("SELECT DISTINCT foul_detail FROM foul_events WHERE foul_detail IS NOT NULL ORDER BY foul_detail")
    foul_types = [r["foul_detail"] for r in cur.fetchall()]

    cur.execute("SELECT DISTINCT fouler_team_tricode FROM foul_events WHERE fouler_team_tricode IS NOT NULL ORDER BY fouler_team_tricode")
    teams = [r["fouler_team_tricode"] for r in cur.fetchall()]

    cur.close()
    conn.close()
    return {"seasons": seasons, "foul_types": foul_types, "teams": teams}


# ---------------------------------------------------------------------------
# /api/graph
# ---------------------------------------------------------------------------

@app.get("/api/graph")
def get_graph(
    season:      Optional[str] = Query(None),
    foul_detail: Optional[str] = Query(None),
    game_type:   Optional[str] = Query(None),
    team:        Optional[str] = Query(None),
    min_fouls:   int           = Query(3, ge=1),
):
    conn = get_conn()
    cur  = conn.cursor()

    cur.execute(f"""
        SELECT
            f.official_id,
            f.official_name,
            f.fouler_player_id,
            f.fouler_player_name,
            COUNT(*) AS foul_count
        FROM foul_events f
        JOIN games g ON f.game_id = g.game_id
        WHERE f.official_id      IS NOT NULL
          AND f.fouler_player_id IS NOT NULL
          AND (%(season)s      IS NULL OR g.season              = %(season)s)
          AND (%(foul_detail)s IS NULL OR f.foul_detail         = %(foul_detail)s)
          AND (%(team)s        IS NULL OR f.fouler_team_tricode = %(team)s)
          {GAME_TYPE_CLAUSE}
        GROUP BY f.official_id, f.official_name, f.fouler_player_id, f.fouler_player_name
        HAVING COUNT(*) >= %(min_fouls)s
        ORDER BY foul_count DESC
    """, {"season": season, "foul_detail": foul_detail, "team": team,
          "game_type": game_type, "min_fouls": min_fouls})

    rows = cur.fetchall()
    cur.close()
    conn.close()

    referees, players, links = {}, {}, []
    for r in rows:
        rid = f"r_{r['official_id']}"
        pid = f"p_{r['fouler_player_id']}"

        if rid not in referees:
            referees[rid] = {"id": rid, "type": "referee", "name": r["official_name"], "foul_count": 0}
        referees[rid]["foul_count"] += r["foul_count"]

        if pid not in players:
            players[pid] = {"id": pid, "type": "player", "name": r["fouler_player_name"], "foul_count": 0}
        players[pid]["foul_count"] += r["foul_count"]

        links.append({"source": rid, "target": pid, "count": r["foul_count"]})

    return {"nodes": list(referees.values()) + list(players.values()), "links": links}


# ---------------------------------------------------------------------------
# /api/referees
# ---------------------------------------------------------------------------

@app.get("/api/referees")
def get_referees(
    season:      Optional[str] = Query(None),
    game_type:   Optional[str] = Query(None),
    foul_detail: Optional[str] = Query(None),
):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(f"""
        SELECT
            r.official_id,
            r.official_name,
            COUNT(f.official_id) AS total_fouls
        FROM referees r
        LEFT JOIN foul_events f ON r.official_id = f.official_id
        LEFT JOIN games g ON f.game_id = g.game_id
        WHERE (%(season)s      IS NULL OR g.season      = %(season)s      OR g.season IS NULL)
          AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s OR f.foul_detail IS NULL)
          {GAME_TYPE_CLAUSE}
        GROUP BY r.official_id, r.official_name
        ORDER BY total_fouls DESC
    """, {"season": season, "game_type": game_type, "foul_detail": foul_detail})
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# /api/players
# ---------------------------------------------------------------------------

@app.get("/api/players")
def get_players(
    season:      Optional[str] = Query(None),
    game_type:   Optional[str] = Query(None),
    foul_detail: Optional[str] = Query(None),
):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(f"""
        WITH latest_team AS (
            SELECT DISTINCT ON (fouler_player_id)
                fouler_player_id,
                fouler_team_tricode
            FROM foul_events
            WHERE fouler_team_tricode IS NOT NULL
            ORDER BY fouler_player_id, game_id DESC
        )
        SELECT
            p.player_id,
            p.player_name,
            lt.fouler_team_tricode AS team_tricode,
            COUNT(f.fouler_player_id) AS total_fouls
        FROM players p
        LEFT JOIN latest_team lt ON lt.fouler_player_id = p.player_id
        LEFT JOIN foul_events f ON p.player_id = f.fouler_player_id
        LEFT JOIN games g ON f.game_id = g.game_id
        WHERE (%(season)s      IS NULL OR g.season      = %(season)s      OR g.season IS NULL)
          AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s OR f.foul_detail IS NULL)
          {GAME_TYPE_CLAUSE}
        GROUP BY p.player_id, p.player_name, lt.fouler_team_tricode
        ORDER BY total_fouls DESC
    """, {"season": season, "game_type": game_type, "foul_detail": foul_detail})
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# /api/teams
# ---------------------------------------------------------------------------

@app.get("/api/teams")
def get_teams(
    season:      Optional[str] = Query(None),
    game_type:   Optional[str] = Query(None),
    foul_detail: Optional[str] = Query(None),
):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(f"""
        SELECT
            f.fouler_team_tricode AS team_tricode,
            COUNT(*) AS total_fouls
        FROM foul_events f
        JOIN games g ON f.game_id = g.game_id
        WHERE f.fouler_team_tricode IS NOT NULL
          AND (%(season)s      IS NULL OR g.season      = %(season)s)
          AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
          {GAME_TYPE_CLAUSE}
        GROUP BY f.fouler_team_tricode
        ORDER BY total_fouls DESC
    """, {"season": season, "game_type": game_type, "foul_detail": foul_detail})
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# /api/team/{tricode}
# ---------------------------------------------------------------------------

@app.get("/api/team/{team_tricode}")
def get_team(
    team_tricode: str,
    season:       Optional[str] = Query(None),
    game_type:    Optional[str] = Query(None),
    foul_detail:  Optional[str] = Query(None),
):
    conn = get_conn()
    cur  = conn.cursor()

    params = {"team_tricode": team_tricode, "season": season,
              "game_type": game_type, "foul_detail": foul_detail}

    cur.execute(f"""
        SELECT
            f.official_id,
            f.official_name,
            COUNT(*)                                                        AS total_fouls,
            SUM(CASE WHEN f.foul_detail = 'shooting'   THEN 1 ELSE 0 END) AS shooting,
            SUM(CASE WHEN f.foul_detail = 'personal'   THEN 1 ELSE 0 END) AS personal,
            SUM(CASE WHEN f.foul_detail = 'offensive'  THEN 1 ELSE 0 END) AS offensive,
            SUM(CASE WHEN f.foul_detail = 'loose_ball' THEN 1 ELSE 0 END) AS loose_ball,
            SUM(CASE WHEN f.foul_detail = 'flagrant_1' THEN 1 ELSE 0 END) AS flagrant_1,
            SUM(CASE WHEN f.foul_detail = 'flagrant_2' THEN 1 ELSE 0 END) AS flagrant_2,
            SUM(CASE WHEN f.foul_detail = 'technical'  THEN 1 ELSE 0 END) AS technical
        FROM foul_events f
        JOIN games g ON f.game_id = g.game_id
        WHERE f.fouler_team_tricode = %(team_tricode)s
          AND f.official_id IS NOT NULL
          AND (%(season)s      IS NULL OR g.season      = %(season)s)
          AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
          {GAME_TYPE_CLAUSE}
        GROUP BY f.official_id, f.official_name
        ORDER BY total_fouls DESC
        LIMIT 25
    """, params)
    top_referees = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT foul_detail, COUNT(*) AS count
        FROM foul_events f
        JOIN games g ON f.game_id = g.game_id
        WHERE f.fouler_team_tricode = %(team_tricode)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {GAME_TYPE_CLAUSE}
        GROUP BY foul_detail
        ORDER BY count DESC
    """, params)
    foul_breakdown = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()
    return {"team_tricode": team_tricode, "top_referees": top_referees, "foul_breakdown": foul_breakdown}


# ---------------------------------------------------------------------------
# /api/referee/{id}
# ---------------------------------------------------------------------------

@app.get("/api/referee/{official_id}")
def get_referee(
    official_id: int,
    season:      Optional[str] = Query(None),
    game_type:   Optional[str] = Query(None),
    foul_detail: Optional[str] = Query(None),
):
    conn = get_conn()
    cur  = conn.cursor()

    cur.execute("SELECT * FROM referees WHERE official_id = %s", (official_id,))
    referee = cur.fetchone()
    if not referee:
        raise HTTPException(status_code=404, detail="Referee not found")

    params = {"official_id": official_id, "season": season,
              "game_type": game_type, "foul_detail": foul_detail}

    cur.execute(f"""
        SELECT
            f.fouler_player_id,
            f.fouler_player_name,
            f.fouler_team_tricode,
            COUNT(*)                                                        AS total_fouls,
            SUM(CASE WHEN f.foul_detail = 'shooting'   THEN 1 ELSE 0 END) AS shooting,
            SUM(CASE WHEN f.foul_detail = 'personal'   THEN 1 ELSE 0 END) AS personal,
            SUM(CASE WHEN f.foul_detail = 'offensive'  THEN 1 ELSE 0 END) AS offensive,
            SUM(CASE WHEN f.foul_detail = 'loose_ball' THEN 1 ELSE 0 END) AS loose_ball,
            SUM(CASE WHEN f.foul_detail = 'flagrant_1' THEN 1 ELSE 0 END) AS flagrant_1,
            SUM(CASE WHEN f.foul_detail = 'flagrant_2' THEN 1 ELSE 0 END) AS flagrant_2,
            SUM(CASE WHEN f.foul_detail = 'technical'  THEN 1 ELSE 0 END) AS technical
        FROM foul_events f
        JOIN games g ON f.game_id = g.game_id
        WHERE f.official_id = %(official_id)s
          AND (%(season)s      IS NULL OR g.season      = %(season)s)
          AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
          {GAME_TYPE_CLAUSE}
        GROUP BY f.fouler_player_id, f.fouler_player_name, f.fouler_team_tricode
        ORDER BY total_fouls DESC
        LIMIT 25
    """, params)
    top_players = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT foul_detail, COUNT(*) AS count
        FROM foul_events f
        JOIN games g ON f.game_id = g.game_id
        WHERE f.official_id = %(official_id)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {GAME_TYPE_CLAUSE}
        GROUP BY foul_detail
        ORDER BY count DESC
    """, params)
    foul_breakdown = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()
    return {"referee": dict(referee), "top_players": top_players, "foul_breakdown": foul_breakdown}


# ---------------------------------------------------------------------------
# /api/player/{id}
# ---------------------------------------------------------------------------

@app.get("/api/player/{player_id}")
def get_player(
    player_id:   int,
    season:      Optional[str] = Query(None),
    game_type:   Optional[str] = Query(None),
    foul_detail: Optional[str] = Query(None),
):
    conn = get_conn()
    cur  = conn.cursor()

    cur.execute("SELECT * FROM players WHERE player_id = %s", (player_id,))
    player = cur.fetchone()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    params = {"player_id": player_id, "season": season,
              "game_type": game_type, "foul_detail": foul_detail}

    cur.execute(f"""
        SELECT
            f.official_id,
            f.official_name,
            COUNT(*)                                                        AS total_fouls,
            SUM(CASE WHEN f.foul_detail = 'shooting'   THEN 1 ELSE 0 END) AS shooting,
            SUM(CASE WHEN f.foul_detail = 'personal'   THEN 1 ELSE 0 END) AS personal,
            SUM(CASE WHEN f.foul_detail = 'offensive'  THEN 1 ELSE 0 END) AS offensive,
            SUM(CASE WHEN f.foul_detail = 'loose_ball' THEN 1 ELSE 0 END) AS loose_ball,
            SUM(CASE WHEN f.foul_detail = 'flagrant_1' THEN 1 ELSE 0 END) AS flagrant_1,
            SUM(CASE WHEN f.foul_detail = 'flagrant_2' THEN 1 ELSE 0 END) AS flagrant_2,
            SUM(CASE WHEN f.foul_detail = 'technical'  THEN 1 ELSE 0 END) AS technical
        FROM foul_events f
        JOIN games g ON f.game_id = g.game_id
        WHERE f.fouler_player_id = %(player_id)s
          AND f.official_id IS NOT NULL
          AND (%(season)s      IS NULL OR g.season      = %(season)s)
          AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
          {GAME_TYPE_CLAUSE}
        GROUP BY f.official_id, f.official_name
        ORDER BY total_fouls DESC
        LIMIT 25
    """, params)
    top_referees = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT foul_detail, COUNT(*) AS count
        FROM foul_events f
        JOIN games g ON f.game_id = g.game_id
        WHERE f.fouler_player_id = %(player_id)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {GAME_TYPE_CLAUSE}
        GROUP BY foul_detail
        ORDER BY count DESC
    """, params)
    foul_breakdown = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()
    return {"player": dict(player), "top_referees": top_referees, "foul_breakdown": foul_breakdown}
