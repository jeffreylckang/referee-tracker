"""
Referee Tracker API — FastAPI backend.

Endpoints:
    GET /api/filters           — available seasons, foul types, teams
    GET /api/graph             — aggregated nodes + links for network graph
    GET /api/referees          — all referees
    GET /api/players           — all players
    GET /api/referee/{id}      — referee detail + top players fouled
    GET /api/player/{id}       — player detail + top referees

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

# ---------------------------------------------------------------------------
# /api/filters
# ---------------------------------------------------------------------------

@app.get("/api/filters")
def get_filters():
    """Return available filter values for the UI dropdowns."""
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
    team:        Optional[str] = Query(None),
    min_fouls:   int           = Query(3, ge=1),
):
    """
    Return aggregated nodes and links for the network graph.

    Nodes:  referees (type=referee) and players (type=player)
    Links:  referee → player pairs with foul count >= min_fouls
    """
    conn = get_conn()
    cur  = conn.cursor()

    cur.execute("""
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
          AND (%(season)s      IS NULL OR g.season            = %(season)s)
          AND (%(foul_detail)s IS NULL OR f.foul_detail       = %(foul_detail)s)
          AND (%(team)s        IS NULL OR f.fouler_team_tricode = %(team)s)
        GROUP BY f.official_id, f.official_name, f.fouler_player_id, f.fouler_player_name
        HAVING COUNT(*) >= %(min_fouls)s
        ORDER BY foul_count DESC
    """, {"season": season, "foul_detail": foul_detail, "team": team, "min_fouls": min_fouls})

    rows = cur.fetchall()
    cur.close()
    conn.close()

    # Build deduplicated nodes and links
    referees = {}
    players  = {}
    links    = []

    for r in rows:
        rid = f"r_{r['official_id']}"
        pid = f"p_{r['fouler_player_id']}"

        if rid not in referees:
            referees[rid] = {
                "id":         rid,
                "type":       "referee",
                "name":       r["official_name"],
                "foul_count": 0,
            }
        referees[rid]["foul_count"] += r["foul_count"]

        if pid not in players:
            players[pid] = {
                "id":         pid,
                "type":       "player",
                "name":       r["fouler_player_name"],
                "foul_count": 0,
            }
        players[pid]["foul_count"] += r["foul_count"]

        links.append({
            "source": rid,
            "target": pid,
            "count":  r["foul_count"],
        })

    return {
        "nodes": list(referees.values()) + list(players.values()),
        "links": links,
    }


# ---------------------------------------------------------------------------
# /api/referees
# ---------------------------------------------------------------------------

@app.get("/api/referees")
def get_referees():
    """Return all referees with total foul counts."""
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT
            r.official_id,
            r.official_name,
            COUNT(f.official_id) AS total_fouls
        FROM referees r
        LEFT JOIN foul_events f ON r.official_id = f.official_id
        GROUP BY r.official_id, r.official_name
        ORDER BY total_fouls DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# /api/players
# ---------------------------------------------------------------------------

@app.get("/api/players")
def get_players():
    """Return all players with total fouls committed."""
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT
            p.player_id,
            p.player_name,
            p.team_tricode,
            COUNT(f.fouler_player_id) AS total_fouls
        FROM players p
        LEFT JOIN foul_events f ON p.player_id = f.fouler_player_id
        GROUP BY p.player_id, p.player_name, p.team_tricode
        ORDER BY total_fouls DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# /api/referee/{id}
# ---------------------------------------------------------------------------

@app.get("/api/referee/{official_id}")
def get_referee(official_id: int, season: Optional[str] = Query(None)):
    """Return referee detail and top players they fouled."""
    conn = get_conn()
    cur  = conn.cursor()

    cur.execute("SELECT * FROM referees WHERE official_id = %s", (official_id,))
    referee = cur.fetchone()
    if not referee:
        raise HTTPException(status_code=404, detail="Referee not found")

    cur.execute("""
        SELECT
            f.fouler_player_id,
            f.fouler_player_name,
            f.fouler_team_tricode,
            COUNT(*)                                             AS total_fouls,
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
          AND (%(season)s IS NULL OR g.season = %(season)s)
        GROUP BY f.fouler_player_id, f.fouler_player_name, f.fouler_team_tricode
        ORDER BY total_fouls DESC
        LIMIT 25
    """, {"official_id": official_id, "season": season})

    top_players = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT
            foul_detail,
            COUNT(*) AS count
        FROM foul_events f
        JOIN games g ON f.game_id = g.game_id
        WHERE f.official_id = %(official_id)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
        GROUP BY foul_detail
        ORDER BY count DESC
    """, {"official_id": official_id, "season": season})

    foul_breakdown = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()

    return {
        "referee":        dict(referee),
        "top_players":    top_players,
        "foul_breakdown": foul_breakdown,
    }


# ---------------------------------------------------------------------------
# /api/player/{id}
# ---------------------------------------------------------------------------

@app.get("/api/player/{player_id}")
def get_player(player_id: int, season: Optional[str] = Query(None)):
    """Return player detail and top referees who called fouls on them."""
    conn = get_conn()
    cur  = conn.cursor()

    cur.execute("SELECT * FROM players WHERE player_id = %s", (player_id,))
    player = cur.fetchone()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    cur.execute("""
        SELECT
            f.official_id,
            f.official_name,
            COUNT(*)                                             AS total_fouls,
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
          AND (%(season)s IS NULL OR g.season = %(season)s)
        GROUP BY f.official_id, f.official_name
        ORDER BY total_fouls DESC
        LIMIT 25
    """, {"player_id": player_id, "season": season})

    top_referees = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT foul_detail, COUNT(*) AS count
        FROM foul_events f
        JOIN games g ON f.game_id = g.game_id
        WHERE f.fouler_player_id = %(player_id)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
        GROUP BY foul_detail
        ORDER BY count DESC
    """, {"player_id": player_id, "season": season})

    foul_breakdown = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()

    return {
        "player":         dict(player),
        "top_referees":   top_referees,
        "foul_breakdown": foul_breakdown,
    }
