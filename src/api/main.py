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

import time
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from .db import get_conn

# ---------------------------------------------------------------------------
# Simple in-memory cache — avoids hitting the DB on every request
# ---------------------------------------------------------------------------

_cache: dict = {}
CACHE_TTL = 1800  # 30 minutes


def cache_get(key: str):
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < CACHE_TTL:
        return entry["data"]
    return None


def cache_set(key: str, data):
    _cache[key] = {"data": data, "ts": time.time()}

app = FastAPI(title="Referee Tracker API")


@app.on_event("startup")
async def warmup_cache():
    """Pre-warm common list queries so first Dashboard load is fast."""
    import threading
    def _warm():
        try:
            get_filters()
            get_referees()
            get_players()
            get_teams()
            get_summary()
        except Exception:
            pass
    threading.Thread(target=_warm, daemon=True).start()

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
    cached = cache_get("filters")
    if cached:
        return cached

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
    result = {"seasons": seasons, "foul_types": foul_types, "teams": teams}
    cache_set("filters", result)
    return result


# ---------------------------------------------------------------------------
# /api/stats
# ---------------------------------------------------------------------------

@app.get("/api/stats")
def get_stats():
    conn = get_conn()
    cur  = conn.cursor()

    cur.execute("SELECT COUNT(*) AS count FROM games")
    games = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) AS count FROM foul_events WHERE official_id IS NOT NULL")
    fouls = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) AS count FROM referees")
    referees = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) AS count FROM players WHERE team_tricode IS NOT NULL")
    players = cur.fetchone()["count"]

    cur.execute("SELECT MIN(season) AS min_season, MAX(season) AS max_season FROM games WHERE season IS NOT NULL")
    season_range = cur.fetchone()

    cur.execute("""
        SELECT season, COUNT(*) AS games,
               SUM(CASE WHEN playoff_round IS NOT NULL THEN 1 ELSE 0 END) AS playoff_games
        FROM games WHERE season IS NOT NULL
        GROUP BY season ORDER BY season
    """)
    by_season = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()
    return {
        "games":        games,
        "foul_events":  fouls,
        "referees":     referees,
        "players":      players,
        "season_range": {"min": season_range["min_season"], "max": season_range["max_season"]},
        "by_season":    by_season,
    }


# ---------------------------------------------------------------------------
# /api/summary  — league-wide headline stats (used by Dashboard banner)
# ---------------------------------------------------------------------------

@app.get("/api/summary")
def get_summary(
    season:      Optional[str] = Query(None),
    game_type:   Optional[str] = Query(None),
    foul_detail: Optional[str] = Query(None),
):
    cache_key = f"summary:{season}:{game_type}:{foul_detail}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    conn = get_conn()
    cur  = conn.cursor()

    if not season and not game_type:
        fd_filter = "AND (%(fd)s IS NULL OR foul_detail = %(fd)s)"
        p = {"fd": foul_detail}

        cur.execute(f"""
            SELECT COUNT(*) AS total_fouls,
                   COUNT(DISTINCT game_id) AS total_games,
                   COUNT(DISTINCT official_id) AS total_refs
            FROM foul_events
            WHERE official_id IS NOT NULL {fd_filter}
        """, p)
        row = cur.fetchone()
        total_fouls, total_games, total_refs = row["total_fouls"], row["total_games"], row["total_refs"]

        cur.execute(f"""
            WITH ref_game AS (
                SELECT official_id, game_id, COUNT(*) AS fouls
                FROM foul_events
                WHERE official_id IS NOT NULL {fd_filter}
                GROUP BY official_id, game_id
            )
            SELECT ROUND(AVG(fouls)::numeric, 1) AS avg_fpg,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fouls)::numeric, 1) AS med_fpg
            FROM ref_game
        """, p)
        agg = cur.fetchone()

        cur.execute(f"""
            WITH player_game AS (
                SELECT fouler_player_id, game_id, COUNT(*) AS fouls
                FROM foul_events
                WHERE fouler_player_id IS NOT NULL {fd_filter}
                GROUP BY fouler_player_id, game_id
            )
            SELECT ROUND(AVG(fouls)::numeric, 2) AS avg_fpg FROM player_game
        """, p)
        player_agg = cur.fetchone()

        cur.execute(f"""
            WITH team_game AS (
                SELECT fouler_team_tricode, game_id, COUNT(*) AS fouls
                FROM foul_events
                WHERE fouler_team_tricode IS NOT NULL {fd_filter}
                GROUP BY fouler_team_tricode, game_id
            )
            SELECT ROUND(AVG(fouls)::numeric, 2) AS avg_fpg FROM team_game
        """, p)
        team_agg = cur.fetchone()

        cur.execute(f"""
            SELECT official_id, official_name,
                   COUNT(*) AS total_fouls,
                   COUNT(DISTINCT game_id) AS games_worked,
                   ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT game_id), 0), 1) AS fouls_per_game
            FROM foul_events
            WHERE official_id IS NOT NULL {fd_filter}
            GROUP BY official_id, official_name
            ORDER BY total_fouls DESC LIMIT 1
        """, p)
        top_ref = dict(r) if (r := cur.fetchone()) else None

        cur.execute(f"""
            SELECT f.fouler_player_id AS player_id, p.player_name, COUNT(*) AS total_fouls
            FROM foul_events f
            JOIN players p ON p.player_id = f.fouler_player_id
            WHERE f.fouler_player_id IS NOT NULL {fd_filter}
            GROUP BY f.fouler_player_id, p.player_name
            ORDER BY total_fouls DESC LIMIT 1
        """, p)
        top_player = dict(r) if (r := cur.fetchone()) else None

        cur.execute(f"""
            SELECT fouler_team_tricode AS team_tricode, COUNT(*) AS total_fouls
            FROM foul_events
            WHERE fouler_team_tricode IS NOT NULL {fd_filter}
            GROUP BY fouler_team_tricode
            ORDER BY total_fouls DESC LIMIT 1
        """, p)
        top_team = dict(r) if (r := cur.fetchone()) else None

    else:
        p = {"season": season, "game_type": game_type, "fd": foul_detail}
        gt_clause = """
            AND (%(game_type)s IS NULL
                 OR (%(game_type)s = 'regular' AND g.playoff_round IS NULL)
                 OR (%(game_type)s = 'playoff' AND g.playoff_round IS NOT NULL))
        """
        fd_filter = "AND (%(fd)s IS NULL OR f.foul_detail = %(fd)s)"

        cur.execute(f"""
            SELECT COUNT(*) AS total_fouls,
                   COUNT(DISTINCT f.game_id) AS total_games,
                   COUNT(DISTINCT f.official_id) AS total_refs
            FROM foul_events f
            JOIN games g ON g.game_id = f.game_id
            WHERE f.official_id IS NOT NULL
              AND (%(season)s IS NULL OR g.season = %(season)s)
              {gt_clause} {fd_filter}
        """, p)
        row = cur.fetchone()
        total_fouls, total_games, total_refs = row["total_fouls"], row["total_games"], row["total_refs"]

        cur.execute(f"""
            WITH ref_game AS (
                SELECT f.official_id, f.game_id, COUNT(*) AS fouls
                FROM foul_events f
                JOIN games g ON g.game_id = f.game_id
                WHERE f.official_id IS NOT NULL
                  AND (%(season)s IS NULL OR g.season = %(season)s)
                  {gt_clause} {fd_filter}
                GROUP BY f.official_id, f.game_id
            )
            SELECT ROUND(AVG(fouls)::numeric, 1) AS avg_fpg,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fouls)::numeric, 1) AS med_fpg
            FROM ref_game
        """, p)
        agg = cur.fetchone()

        cur.execute(f"""
            WITH player_game AS (
                SELECT f.fouler_player_id, f.game_id, COUNT(*) AS fouls
                FROM foul_events f
                JOIN games g ON g.game_id = f.game_id
                WHERE f.fouler_player_id IS NOT NULL
                  AND (%(season)s IS NULL OR g.season = %(season)s)
                  {gt_clause} {fd_filter}
                GROUP BY f.fouler_player_id, f.game_id
            )
            SELECT ROUND(AVG(fouls)::numeric, 2) AS avg_fpg FROM player_game
        """, p)
        player_agg = cur.fetchone()

        cur.execute(f"""
            WITH team_game AS (
                SELECT f.fouler_team_tricode, f.game_id, COUNT(*) AS fouls
                FROM foul_events f
                JOIN games g ON g.game_id = f.game_id
                WHERE f.fouler_team_tricode IS NOT NULL
                  AND (%(season)s IS NULL OR g.season = %(season)s)
                  {gt_clause} {fd_filter}
                GROUP BY f.fouler_team_tricode, f.game_id
            )
            SELECT ROUND(AVG(fouls)::numeric, 2) AS avg_fpg FROM team_game
        """, p)
        team_agg = cur.fetchone()

        cur.execute(f"""
            SELECT f.official_id, f.official_name,
                   COUNT(*) AS total_fouls,
                   COUNT(DISTINCT f.game_id) AS games_worked,
                   ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT f.game_id), 0), 1) AS fouls_per_game
            FROM foul_events f
            JOIN games g ON g.game_id = f.game_id
            WHERE f.official_id IS NOT NULL
              AND (%(season)s IS NULL OR g.season = %(season)s)
              {gt_clause} {fd_filter}
            GROUP BY f.official_id, f.official_name
            ORDER BY total_fouls DESC LIMIT 1
        """, p)
        top_ref = dict(r) if (r := cur.fetchone()) else None

        cur.execute(f"""
            SELECT f.fouler_player_id AS player_id, pl.player_name, COUNT(*) AS total_fouls
            FROM foul_events f
            JOIN games g ON g.game_id = f.game_id
            JOIN players pl ON pl.player_id = f.fouler_player_id
            WHERE f.fouler_player_id IS NOT NULL
              AND (%(season)s IS NULL OR g.season = %(season)s)
              {gt_clause} {fd_filter}
            GROUP BY f.fouler_player_id, pl.player_name
            ORDER BY total_fouls DESC LIMIT 1
        """, p)
        top_player = dict(r) if (r := cur.fetchone()) else None

        cur.execute(f"""
            SELECT f.fouler_team_tricode AS team_tricode, COUNT(*) AS total_fouls
            FROM foul_events f
            JOIN games g ON g.game_id = f.game_id
            WHERE f.fouler_team_tricode IS NOT NULL
              AND (%(season)s IS NULL OR g.season = %(season)s)
              {gt_clause} {fd_filter}
            GROUP BY f.fouler_team_tricode
            ORDER BY total_fouls DESC LIMIT 1
        """, p)
        top_team = dict(r) if (r := cur.fetchone()) else None

    cur.close()
    conn.close()

    result = {
        "total_fouls":         total_fouls,
        "total_games":         total_games,
        "total_refs":          total_refs,
        "avg_fouls_per_game":  float(agg["avg_fpg"]) if agg["avg_fpg"] else None,
        "median_fouls_per_game": float(agg["med_fpg"]) if agg["med_fpg"] else None,
        "avg_player_fpg":      float(player_agg["avg_fpg"]) if player_agg and player_agg["avg_fpg"] else None,
        "avg_team_fpg":        float(team_agg["avg_fpg"])   if team_agg   and team_agg["avg_fpg"]   else None,
        "most_active_ref":     top_ref,
        "most_fouled_player":  top_player,
        "most_penalized_team": top_team,
    }
    cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# /api/graph
# ---------------------------------------------------------------------------

@app.get("/api/graph")
def get_graph(
    season:      Optional[str] = Query(None),
    foul_detail: Optional[str] = Query(None),
    game_type:   Optional[str] = Query(None),
    team:        Optional[str] = Query(None),
    official_id: Optional[int] = Query(None),
    min_fouls:   int           = Query(3, ge=1),
):
    cache_key = f"graph:{season}:{foul_detail}:{game_type}:{team}:{official_id}:{min_fouls}"
    cached = cache_get(cache_key)
    if cached:
        return cached

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
          AND (%(official_id)s IS NULL OR f.official_id        = %(official_id)s)
          {GAME_TYPE_CLAUSE}
        GROUP BY f.official_id, f.official_name, f.fouler_player_id, f.fouler_player_name
        HAVING COUNT(*) >= %(min_fouls)s
        ORDER BY foul_count DESC
    """, {"season": season, "foul_detail": foul_detail, "team": team,
          "game_type": game_type, "official_id": official_id, "min_fouls": min_fouls})

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

    result = {"nodes": list(referees.values()) + list(players.values()), "links": links}
    cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# /api/referees
# ---------------------------------------------------------------------------

@app.get("/api/referees")
def get_referees(
    season:      Optional[str] = Query(None),
    game_type:   Optional[str] = Query(None),
    foul_detail: Optional[str] = Query(None),
):
    cache_key = f"referees:{season}:{game_type}:{foul_detail}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    conn = get_conn()
    cur  = conn.cursor()
    if not season and not game_type:
        cur.execute("""
            SELECT official_id, official_name, COUNT(*) AS total_fouls
            FROM foul_events
            WHERE official_id IS NOT NULL
              AND (%(foul_detail)s IS NULL OR foul_detail = %(foul_detail)s)
            GROUP BY official_id, official_name
            ORDER BY total_fouls DESC
        """, {"foul_detail": foul_detail})
    else:
        cur.execute(f"""
            SELECT r.official_id, r.official_name, COUNT(f.official_id) AS total_fouls
            FROM referees r
            JOIN foul_events f ON r.official_id = f.official_id
            JOIN games g ON f.game_id = g.game_id
            WHERE (%(season)s      IS NULL OR g.season      = %(season)s)
              AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
              {GAME_TYPE_CLAUSE}
            GROUP BY r.official_id, r.official_name
            ORDER BY total_fouls DESC
        """, {"season": season, "game_type": game_type, "foul_detail": foul_detail})
    rows = cur.fetchall()
    cur.close()
    conn.close()
    result = [dict(r) for r in rows]
    cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# /api/players
# ---------------------------------------------------------------------------

@app.get("/api/players")
def get_players(
    season:      Optional[str] = Query(None),
    game_type:   Optional[str] = Query(None),
    foul_detail: Optional[str] = Query(None),
):
    cache_key = f"players:{season}:{game_type}:{foul_detail}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    conn = get_conn()
    cur  = conn.cursor()
    if not season and not game_type:
        cur.execute("""
            WITH latest_team AS (
                SELECT DISTINCT ON (fouler_player_id)
                    fouler_player_id, fouler_team_tricode
                FROM foul_events
                WHERE fouler_team_tricode IS NOT NULL
                ORDER BY fouler_player_id, game_id DESC
            ),
            real_players AS (
                SELECT DISTINCT fouler_player_id
                FROM foul_events
                WHERE foul_detail != 'technical'
            )
            SELECT f.fouler_player_id       AS player_id,
                   MAX(f.fouler_player_name) AS player_name,
                   lt.fouler_team_tricode    AS team_tricode,
                   COUNT(*)                 AS total_fouls
            FROM foul_events f
            JOIN real_players rp ON rp.fouler_player_id = f.fouler_player_id
            LEFT JOIN latest_team lt ON lt.fouler_player_id = f.fouler_player_id
            WHERE f.fouler_player_id IS NOT NULL
              AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
            GROUP BY f.fouler_player_id, lt.fouler_team_tricode
            ORDER BY total_fouls DESC
        """, {"foul_detail": foul_detail})
    else:
        cur.execute(f"""
            WITH latest_team AS (
                SELECT DISTINCT ON (fouler_player_id)
                    fouler_player_id, fouler_team_tricode
                FROM foul_events
                WHERE fouler_team_tricode IS NOT NULL
                ORDER BY fouler_player_id, game_id DESC
            ),
            real_players AS (
                SELECT DISTINCT fouler_player_id
                FROM foul_events
                WHERE foul_detail != 'technical'
            )
            SELECT f.fouler_player_id                AS player_id,
                   MAX(f.fouler_player_name)         AS player_name,
                   lt.fouler_team_tricode            AS team_tricode,
                   COUNT(*)                          AS total_fouls
            FROM foul_events f
            JOIN games g ON f.game_id = g.game_id
            JOIN real_players rp ON rp.fouler_player_id = f.fouler_player_id
            LEFT JOIN latest_team lt ON lt.fouler_player_id = f.fouler_player_id
            WHERE f.fouler_player_id IS NOT NULL
              AND (%(season)s      IS NULL OR g.season      = %(season)s)
              AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
              {GAME_TYPE_CLAUSE}
            GROUP BY f.fouler_player_id, lt.fouler_team_tricode
            ORDER BY total_fouls DESC
        """, {"season": season, "game_type": game_type, "foul_detail": foul_detail})
    rows = cur.fetchall()
    cur.close()
    conn.close()
    result = [dict(r) for r in rows]
    cache_set(f"players:{season}:{game_type}:{foul_detail}", result)
    return result


# ---------------------------------------------------------------------------
# /api/teams
# ---------------------------------------------------------------------------

@app.get("/api/teams")
def get_teams(
    season:      Optional[str] = Query(None),
    game_type:   Optional[str] = Query(None),
    foul_detail: Optional[str] = Query(None),
):
    cache_key = f"teams:{season}:{game_type}:{foul_detail}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    conn = get_conn()
    cur  = conn.cursor()
    if not season and not game_type:
        cur.execute("""
            SELECT fouler_team_tricode AS team_tricode, COUNT(*) AS total_fouls
            FROM foul_events
            WHERE fouler_team_tricode IS NOT NULL
              AND (%(foul_detail)s IS NULL OR foul_detail = %(foul_detail)s)
            GROUP BY fouler_team_tricode
            ORDER BY total_fouls DESC
        """, {"foul_detail": foul_detail})
    else:
        cur.execute(f"""
            SELECT f.fouler_team_tricode AS team_tricode, COUNT(*) AS total_fouls
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
    result = [dict(r) for r in rows]
    cache_set(cache_key, result)
    return result


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
    cache_key = f"team:{team_tricode}:{season}:{game_type}:{foul_detail}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    conn = get_conn()
    cur  = conn.cursor()

    params = {"team_tricode": team_tricode, "season": season,
              "game_type": game_type, "foul_detail": foul_detail}

    cur.execute(f"""
        SELECT
            f.official_id,
            f.official_name,
            COUNT(*)                                                        AS total_fouls,
            COUNT(DISTINCT f.game_id)                                      AS games_shared,
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

    cur.execute(f"""
        SELECT g.season,
               COUNT(*)                      AS total_fouls,
               COUNT(DISTINCT f.game_id)     AS games_played,
               ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT f.game_id), 0), 2) AS fouls_per_game
        FROM foul_events f
        JOIN games g ON g.game_id = f.game_id
        WHERE f.fouler_team_tricode = %(team_tricode)s
          AND g.season IS NOT NULL
          AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
          {GAME_TYPE_CLAUSE}
        GROUP BY g.season ORDER BY g.season
    """, params)
    season_trend = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT COUNT(*) AS total_fouls, COUNT(DISTINCT f.game_id) AS games_played
        FROM foul_events f
        JOIN games g ON g.game_id = f.game_id
        WHERE f.fouler_team_tricode = %(team_tricode)s
          AND (%(season)s      IS NULL OR g.season      = %(season)s)
          AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
          {GAME_TYPE_CLAUSE}
    """, params)
    entity_stats = cur.fetchone()
    gp = entity_stats["games_played"] if entity_stats else 0

    cur.close()
    conn.close()
    result = {"team_tricode": team_tricode, "top_referees": top_referees, "foul_breakdown": foul_breakdown,
              "season_trend": season_trend,
              "games_played": gp,
              "fouls_per_game": round(entity_stats["total_fouls"] / gp, 2) if gp else None}
    cache_set(cache_key, result)
    return result


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
    cache_key = f"referee:{official_id}:{season}:{game_type}:{foul_detail}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    conn = get_conn()
    cur  = conn.cursor()

    cur.execute("SELECT * FROM referees WHERE official_id = %s", (official_id,))
    referee = cur.fetchone()
    if not referee:
        raise HTTPException(status_code=404, detail="Referee not found")

    params = {"official_id": official_id, "season": season,
              "game_type": game_type, "foul_detail": foul_detail}

    if not season and not game_type:
        # Fast path: restrict CTE + skip games join
        cur.execute("""
            WITH latest_team AS (
                SELECT DISTINCT ON (fouler_player_id)
                    fouler_player_id, fouler_team_tricode
                FROM foul_events
                WHERE fouler_team_tricode IS NOT NULL
                  AND official_id = %(official_id)s
                ORDER BY fouler_player_id, game_id DESC
            )
            SELECT f.fouler_player_id,
                   MAX(f.fouler_player_name)                               AS fouler_player_name,
                   lt.fouler_team_tricode,
                   COUNT(*)                                                AS total_fouls,
                   COUNT(DISTINCT f.game_id)                              AS games_shared,
                   SUM(CASE WHEN f.foul_detail = 'shooting'   THEN 1 ELSE 0 END) AS shooting,
                   SUM(CASE WHEN f.foul_detail = 'personal'   THEN 1 ELSE 0 END) AS personal,
                   SUM(CASE WHEN f.foul_detail = 'offensive'  THEN 1 ELSE 0 END) AS offensive,
                   SUM(CASE WHEN f.foul_detail = 'loose_ball' THEN 1 ELSE 0 END) AS loose_ball,
                   SUM(CASE WHEN f.foul_detail = 'flagrant_1' THEN 1 ELSE 0 END) AS flagrant_1,
                   SUM(CASE WHEN f.foul_detail = 'flagrant_2' THEN 1 ELSE 0 END) AS flagrant_2,
                   SUM(CASE WHEN f.foul_detail = 'technical'  THEN 1 ELSE 0 END) AS technical
            FROM foul_events f
            LEFT JOIN latest_team lt ON lt.fouler_player_id = f.fouler_player_id
            WHERE f.official_id = %(official_id)s
              AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
            GROUP BY f.fouler_player_id, lt.fouler_team_tricode
            ORDER BY total_fouls DESC LIMIT 25
        """, params)
        top_players = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT foul_detail, COUNT(*) AS count
            FROM foul_events
            WHERE official_id = %(official_id)s
              AND (%(foul_detail)s IS NULL OR foul_detail = %(foul_detail)s)
            GROUP BY foul_detail ORDER BY count DESC
        """, params)
        foul_breakdown = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT period, COUNT(*) AS count
            FROM foul_events
            WHERE official_id = %(official_id)s AND period IS NOT NULL
              AND (%(foul_detail)s IS NULL OR foul_detail = %(foul_detail)s)
            GROUP BY period ORDER BY period
        """, params)
        period_breakdown = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT g.season,
                   COUNT(*)                      AS total_fouls,
                   COUNT(DISTINCT f.game_id)     AS games_worked,
                   ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT f.game_id), 0), 2) AS fouls_per_game
            FROM foul_events f
            JOIN games g ON g.game_id = f.game_id
            WHERE f.official_id = %(official_id)s
              AND g.season IS NOT NULL
              AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
            GROUP BY g.season ORDER BY g.season
        """, params)
        season_trend = [dict(r) for r in cur.fetchall()]
    else:
        cur.execute(f"""
            WITH latest_team AS (
                SELECT DISTINCT ON (fouler_player_id)
                    fouler_player_id, fouler_team_tricode
                FROM foul_events
                WHERE fouler_team_tricode IS NOT NULL
                  AND official_id = %(official_id)s
                ORDER BY fouler_player_id, game_id DESC
            )
            SELECT f.fouler_player_id,
                   MAX(f.fouler_player_name)                               AS fouler_player_name,
                   lt.fouler_team_tricode,
                   COUNT(*)                                                AS total_fouls,
                   COUNT(DISTINCT f.game_id)                              AS games_shared,
                   SUM(CASE WHEN f.foul_detail = 'shooting'   THEN 1 ELSE 0 END) AS shooting,
                   SUM(CASE WHEN f.foul_detail = 'personal'   THEN 1 ELSE 0 END) AS personal,
                   SUM(CASE WHEN f.foul_detail = 'offensive'  THEN 1 ELSE 0 END) AS offensive,
                   SUM(CASE WHEN f.foul_detail = 'loose_ball' THEN 1 ELSE 0 END) AS loose_ball,
                   SUM(CASE WHEN f.foul_detail = 'flagrant_1' THEN 1 ELSE 0 END) AS flagrant_1,
                   SUM(CASE WHEN f.foul_detail = 'flagrant_2' THEN 1 ELSE 0 END) AS flagrant_2,
                   SUM(CASE WHEN f.foul_detail = 'technical'  THEN 1 ELSE 0 END) AS technical
            FROM foul_events f
            LEFT JOIN latest_team lt ON lt.fouler_player_id = f.fouler_player_id
            JOIN games g ON f.game_id = g.game_id
            WHERE f.official_id = %(official_id)s
              AND (%(season)s      IS NULL OR g.season      = %(season)s)
              AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
              {GAME_TYPE_CLAUSE}
            GROUP BY f.fouler_player_id, lt.fouler_team_tricode
            ORDER BY total_fouls DESC LIMIT 25
        """, params)
        top_players = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
            SELECT foul_detail, COUNT(*) AS count
            FROM foul_events f
            JOIN games g ON f.game_id = g.game_id
            WHERE f.official_id = %(official_id)s
              AND (%(season)s IS NULL OR g.season = %(season)s)
              AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
              {GAME_TYPE_CLAUSE}
            GROUP BY foul_detail ORDER BY count DESC
        """, params)
        foul_breakdown = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
            SELECT period, COUNT(*) AS count
            FROM foul_events f
            JOIN games g ON f.game_id = g.game_id
            WHERE f.official_id = %(official_id)s AND f.period IS NOT NULL
              AND (%(season)s      IS NULL OR g.season      = %(season)s)
              AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
              {GAME_TYPE_CLAUSE}
            GROUP BY period ORDER BY period
        """, params)
        period_breakdown = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
            SELECT g.season,
                   COUNT(*)                      AS total_fouls,
                   COUNT(DISTINCT f.game_id)     AS games_worked,
                   ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT f.game_id), 0), 2) AS fouls_per_game
            FROM foul_events f
            JOIN games g ON g.game_id = f.game_id
            WHERE f.official_id = %(official_id)s
              AND g.season IS NOT NULL
              AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
              {GAME_TYPE_CLAUSE}
            GROUP BY g.season ORDER BY g.season
        """, params)
        season_trend = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT COUNT(*) AS total_fouls, COUNT(DISTINCT f.game_id) AS games_worked
        FROM foul_events f
        JOIN games g ON g.game_id = f.game_id
        WHERE f.official_id = %(official_id)s
          AND (%(season)s      IS NULL OR g.season      = %(season)s)
          AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
          {GAME_TYPE_CLAUSE}
    """, params)
    entity_stats = cur.fetchone()
    gw = entity_stats["games_worked"] if entity_stats else 0

    cur.close()
    conn.close()
    result = {"referee": dict(referee), "top_players": top_players,
              "foul_breakdown": foul_breakdown, "period_breakdown": period_breakdown,
              "season_trend": season_trend,
              "games_worked": gw,
              "fouls_per_game": round(entity_stats["total_fouls"] / gw, 2) if gw else None}
    cache_set(cache_key, result)
    return result


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
    cache_key = f"player:{player_id}:{season}:{game_type}:{foul_detail}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    conn = get_conn()
    cur  = conn.cursor()

    cur.execute("SELECT * FROM players WHERE player_id = %s", (player_id,))
    player = cur.fetchone()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Use most recent team from foul_events (players table is static at ingest time)
    cur.execute("""
        SELECT fouler_team_tricode FROM foul_events
        WHERE fouler_player_id = %s AND fouler_team_tricode IS NOT NULL
        ORDER BY game_id DESC LIMIT 1
    """, (player_id,))
    team_row = cur.fetchone()
    player_dict = dict(player)
    if team_row:
        player_dict['team_tricode'] = team_row['fouler_team_tricode']

    params = {"player_id": player_id, "season": season,
              "game_type": game_type, "foul_detail": foul_detail}

    cur.execute(f"""
        SELECT
            f.official_id,
            f.official_name,
            COUNT(*)                                                        AS total_fouls,
            COUNT(DISTINCT f.game_id)                                      AS games_shared,
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

    cur.execute(f"""
        SELECT period, COUNT(*) AS count
        FROM foul_events f
        JOIN games g ON f.game_id = g.game_id
        WHERE f.fouler_player_id = %(player_id)s
          AND f.period IS NOT NULL
          AND (%(season)s      IS NULL OR g.season      = %(season)s)
          AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
          {GAME_TYPE_CLAUSE}
        GROUP BY period
        ORDER BY period
    """, params)
    period_breakdown = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT g.season,
               COUNT(*)                      AS total_fouls,
               COUNT(DISTINCT f.game_id)     AS games_played,
               ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT f.game_id), 0), 2) AS fouls_per_game
        FROM foul_events f
        JOIN games g ON g.game_id = f.game_id
        WHERE f.fouler_player_id = %(player_id)s
          AND g.season IS NOT NULL
          AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
          {GAME_TYPE_CLAUSE}
        GROUP BY g.season ORDER BY g.season
    """, params)
    season_trend = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT COUNT(*) AS total_fouls, COUNT(DISTINCT f.game_id) AS games_played
        FROM foul_events f
        JOIN games g ON g.game_id = f.game_id
        WHERE f.fouler_player_id = %(player_id)s
          AND (%(season)s      IS NULL OR g.season      = %(season)s)
          AND (%(foul_detail)s IS NULL OR f.foul_detail = %(foul_detail)s)
          {GAME_TYPE_CLAUSE}
    """, params)
    entity_stats = cur.fetchone()
    gp = entity_stats["games_played"] if entity_stats else 0

    cur.close()
    conn.close()
    result = {"player": player_dict, "top_referees": top_referees,
              "foul_breakdown": foul_breakdown, "period_breakdown": period_breakdown,
              "season_trend": season_trend,
              "games_played": gp,
              "fouls_per_game": round(entity_stats["total_fouls"] / gp, 2) if gp else None}
    cache_set(cache_key, result)
    return result
