"""
Data Agent: Fetch, transform, and store NBA foul events to SQLite.

Usage:
    python agent.py --mode daily              # yesterday's Final games from scoreboard
    python agent.py --season 2023-24          # full season backfill (regular + playoffs)
    python agent.py --game 0042500164         # single game
    python agent.py --mode daily --dry-run    # fetch + transform only, no DB write

CDN data available: 2019-20 through 2025-26.
Schema reference: .claude/schemas/
DB location:      data/referee_tracker.db
"""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import requests
from database import init_db, insert_game, insert_foul_events, insert_players, insert_referees, insert_game_officials
from transform import transform_game, build_officials_lookup

CDN_BASE        = "https://cdn.nba.com/static/json/liveData"
CDN_SCOREBOARD  = f"{CDN_BASE}/scoreboard/todaysScoreboard_00.json"
DATA_DIR        = os.path.join(os.path.dirname(__file__), "../../../data")
DB_PATH         = os.path.join(DATA_DIR, "referee_tracker.db")
ERROR_LOG_PATH  = os.path.join(DATA_DIR, "error_log.jsonl")
LAST_RUN_PATH   = os.path.join(DATA_DIR, "last_run.json")

# Earliest season available on the CDN
EARLIEST_SEASON = "2019-20"

# Round 1 of 2025-26 playoffs — series 1-8, games 1-7 (default fallback)
# game_id format: 00425001{series}{game}
ROUND_1_GAME_IDS = [
    f"00425001{series}{game}"
    for series in range(1, 9)
    for game in range(1, 8)
]


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def fetch_json(url):
    """Fetch JSON from NBA CDN. Returns None on failure."""
    try:
        r = requests.get(url, timeout=15)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def fetch_game_data(game_id):
    """Fetch play-by-play and boxscore for a game. Returns (actions, boxscore) or (None, None)."""
    pbp  = fetch_json(f"{CDN_BASE}/playbyplay/playbyplay_{game_id}.json")
    box  = fetch_json(f"{CDN_BASE}/boxscore/boxscore_{game_id}.json")
    if not pbp or not box:
        return None, None
    return pbp["game"]["actions"], box


FETCH_WORKERS = 20  # concurrent CDN requests


def fetch_all_games_parallel(game_ids):
    """
    Fetch play-by-play + boxscore for all game IDs concurrently.
    Returns list of (game_id, actions, boxscore) for games that exist, sorted by game_id.
    404s and failures are silently dropped (same behaviour as sequential fetch).
    """
    total   = len(game_ids)
    found   = []
    fetched = 0

    def fetch_one(game_id):
        actions, boxscore = fetch_game_data(game_id)
        return game_id, actions, boxscore

    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
        futures = {executor.submit(fetch_one, gid): gid for gid in game_ids}
        for future in as_completed(futures):
            game_id, actions, boxscore = future.result()
            fetched += 1
            if actions is not None:
                found.append((game_id, actions, boxscore))
            if total > 20 and fetched % 100 == 0:
                print(f"  Fetching... {fetched}/{total} checked, {len(found)} found")

    return sorted(found, key=lambda x: x[0])


# ---------------------------------------------------------------------------
# Game ID discovery
# ---------------------------------------------------------------------------

def get_daily_game_ids():
    """
    Return game IDs for daily mode.

    If the Automation Agent wrote pending_game_ids.json (which handles catch-up
    across missed days), use that list. Otherwise fall back to fetching
    yesterday's Final games directly from the CDN scoreboard.
    """
    pending_file = os.path.join(DATA_DIR, "pending_game_ids.json")
    if os.path.exists(pending_file):
        with open(pending_file) as f:
            ids = json.load(f)
        os.remove(pending_file)  # consume once
        print(f"  Daily mode: {len(ids)} game(s) from Automation Agent (catch-up included)")
        return ids

    # Fallback: check scoreboard directly (for manual --mode daily runs)
    data = fetch_json(CDN_SCOREBOARD)
    if not data:
        print("  WARNING: Could not fetch CDN scoreboard.")
        return []

    yesterday = (datetime.now(timezone.utc) - timedelta(hours=5) - timedelta(days=1)).date()
    target = str(yesterday)

    games = data.get("scoreboard", {}).get("games", [])
    ids = []
    for game in games:
        game_date = (game.get("gameEt") or game.get("gameTimeUTC") or "")[:10]
        if game.get("gameStatus") == 3 and game_date == target:
            ids.append(game["gameId"])

    print(f"  Daily mode: {len(ids)} Final game(s) found for {target}")
    return ids


def get_season_game_ids(season):
    """
    Generate candidate game IDs for a full season (regular season + playoffs).

    Season format: "2023-24"
    CDN available: 2019-20 through 2025-26.

    Regular season: game IDs 002{YY}0001 through 002{YY}1230 (over-generates; CDN returns 404 for unplayed)
    Playoffs:       004{YY}{round}{series}{game} for rounds 1-4, series 1-8, games 1-7
    """
    if season < EARLIEST_SEASON:
        print(f"  WARNING: Season {season} predates CDN availability ({EARLIEST_SEASON}+). Continuing anyway — most games will 404.")

    # Parse two-digit year from "2023-24" → "23"
    try:
        yy = season.split("-")[0][2:]  # "2023-24" → "23"
    except (IndexError, ValueError):
        print(f"  ERROR: Invalid season format '{season}'. Expected 'YYYY-YY' (e.g. 2023-24).")
        return []

    regular_season = [f"002{yy}{n:05d}" for n in range(1, 1231)]

    playoffs = [
        f"004{yy}00{round_}{series}{game}"
        for round_ in range(1, 5)
        for series in range(1, 9)
        for game in range(1, 8)
    ]

    return regular_season + playoffs


# ---------------------------------------------------------------------------
# Metadata extractors
# ---------------------------------------------------------------------------

ROUND_NAMES = {
    "1": "First Round",
    "2": "Conference Semifinals",
    "3": "Conference Finals",
    "4": "Finals",
}

def extract_game_meta(game_id, boxscore):
    """Build a game record from boxscore data and game_id."""
    game     = boxscore["game"]
    season   = f"20{game_id[3:5]}-{int(game_id[3:5]) + 1}"  # e.g. "2025-26"
    round_id = game_id[7] if len(game_id) > 7 else None
    date_raw = game.get("gameEt", game.get("gameTimeUTC", ""))
    game_date = date_raw[:10] if date_raw else None  # "YYYY-MM-DD"

    home = game["homeTeam"]
    away = game["awayTeam"]
    home_score = home.get("score")
    away_score = away.get("score")
    if home_score is not None and away_score is not None and home_score != away_score:
        winner_tricode = home["teamTricode"] if home_score > away_score else away["teamTricode"]
    else:
        winner_tricode = None

    return {
        "game_id":           game_id,
        "away_team_tricode": away["teamTricode"],
        "home_team_tricode": home["teamTricode"],
        "game_date":         game_date,
        "season":            season,
        "playoff_round":     ROUND_NAMES.get(round_id),
        "winner_tricode":    winner_tricode,
    }


def extract_players(records):
    """
    Build player registry entries from foul_event records.
    Fouler records (with team info) are added before fouled records
    so INSERT OR IGNORE preserves the richer entry.
    """
    seen = {}

    # Foulers first — have abbreviated name + team info
    for r in records:
        pid = r.get("fouler_player_id")
        if pid and pid not in seen:
            seen[pid] = {
                "player_id":   pid,
                "player_name": r.get("fouler_player_name"),
                "team_id":     r.get("fouler_team_id"),
                "team_tricode":r.get("fouler_team_tricode"),
            }

    # Fouled players — last name only, no team
    for r in records:
        pid = r.get("fouled_player_id")
        if pid and pid not in seen:
            seen[pid] = {
                "player_id":   pid,
                "player_name": r.get("fouled_player_name"),
                "team_id":     None,
                "team_tricode":None,
            }

    return list(seen.values())


def extract_referees(boxscore):
    """Build referee registry entries and game_officials entries from boxscore officials."""
    officials = boxscore["game"].get("officials", [])
    referees       = []
    game_officials = []
    for o in officials:
        referees.append({"official_id": o["personId"], "official_name": o["name"]})
        game_officials.append({"official_id": o["personId"], "assignment": o.get("assignment", "")})
    return referees, game_officials


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def write_logs(run_id, all_errors, total_fouls, total_team_fouls, total_games, skipped, all_referees, dry_run):
    """Write error_log.jsonl (append) and last_run.json (overwrite)."""
    if dry_run:
        return

    # Append each error as a JSON line
    with open(ERROR_LOG_PATH, "a") as f:
        for entry in all_errors:
            f.write(json.dumps({
                "timestamp":     run_id,
                "run_id":        run_id,
                "game_id":       entry["game_id"],
                "action_number": entry["action_number"],
                "reason":        entry["reason"],
                "raw":           entry["raw"],
            }) + "\n")

    # Overwrite last run summary
    error_rate = round(len(all_errors) / total_fouls * 100, 2) if total_fouls else 0
    with open(LAST_RUN_PATH, "w") as f:
        json.dump({
            "run_id":          run_id,
            "games_processed": total_games,
            "games_skipped":   skipped,
            "total_fouls":     total_fouls,
            "total_team_fouls":total_team_fouls,
            "total_errors":    len(all_errors),
            "error_rate_pct":  error_rate,
            "referees_seen":   len(all_referees),
        }, f, indent=2)


def run(game_ids, db_path, dry_run=False):
    """
    Fetch, transform, and store foul events for a list of game IDs.

    Args:
        game_ids: list of NBA game ID strings
        db_path:  path to the SQLite database file
        dry_run:  if True, skip all DB writes and logging
    """
    if not dry_run:
        conn = init_db(db_path)

    run_id            = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total_games       = 0
    total_fouls       = 0
    total_team_fouls  = 0
    skipped           = 0
    all_referees      = {}
    all_errors        = []  # collected across all games for error_log.jsonl

    print(f"{'DRY RUN — ' if dry_run else ''}Fetching {len(game_ids)} candidate game IDs ({FETCH_WORKERS} concurrent)...\n")

    game_results = fetch_all_games_parallel(game_ids)
    skipped      = len(game_ids) - len(game_results)

    print(f"  {len(game_results)} games found, {skipped} skipped (not played / not found)\n")

    for game_id, actions, boxscore in game_results:
        officials_lookup            = build_officials_lookup(boxscore)
        records, errors, team_fouls = transform_game(actions, game_id, officials_lookup)
        game_meta                   = extract_game_meta(game_id, boxscore)
        players                     = extract_players(records)
        referees, game_officials    = extract_referees(boxscore)

        matchup = f"{game_meta['away_team_tricode']}@{game_meta['home_team_tricode']}"
        print(f"  {game_id}  {matchup:<10}  fouls={len(records)}  team_fouls={team_fouls}  errors={len(errors)}")

        if not dry_run:
            insert_game(conn, game_meta)
            insert_referees(conn, referees)
            insert_game_officials(conn, game_id, game_officials)
            insert_players(conn, players)
            insert_foul_events(conn, records)
            conn.commit()

        for r in referees:
            all_referees[r["official_id"]] = r["official_name"]

        for e in errors:
            e["game_id"] = game_id
        all_errors       += errors
        total_games      += 1
        total_fouls      += len(records)
        total_team_fouls += team_fouls

    if not dry_run:
        conn.close()

    write_logs(run_id, all_errors, total_fouls, total_team_fouls, total_games, skipped, all_referees, dry_run)

    # Summary
    error_rate = f"{len(all_errors) / total_fouls * 100:.1f}%" if total_fouls else "n/a"
    print(f"""
--- Run Summary ---
Run ID          : {run_id}
Games processed : {total_games}
Games skipped   : {skipped} (not found / not yet played)
Foul events     : {total_fouls}
Team fouls      : {total_team_fouls} (excluded — no player attribution)
Errors          : {len(all_errors)}  ({error_rate} error rate)
Referees seen   : {len(all_referees)}
DB written      : {"no (dry run)" if dry_run else db_path}
Logs written    : {"no (dry run)" if dry_run else DATA_DIR}
""")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NBA Referee Tracker — Data Agent")
    parser.add_argument("--mode",    choices=["daily"], default=None,
                        help="daily: fetch yesterday's Final games from CDN scoreboard.")
    parser.add_argument("--season",  help="Season to backfill, e.g. 2023-24. Generates regular season + playoff IDs.")
    parser.add_argument("--game",    help="Single game ID to process.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch + transform only, no DB write.")
    args = parser.parse_args()

    if args.game:
        game_ids = [args.game]
    elif args.season:
        game_ids = get_season_game_ids(args.season)
    elif args.mode == "daily":
        game_ids = get_daily_game_ids()
        if not game_ids:
            print("  No games to process. Exiting.")
            exit(0)
    else:
        # Default: current round 1 game IDs (useful for manual re-runs)
        game_ids = ROUND_1_GAME_IDS

    run(game_ids, db_path=DB_PATH, dry_run=args.dry_run)
