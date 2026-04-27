"""
Health Agent: Monitor pipeline health, check data quality, and surface errors for debugging.

Runs in two modes:
  pre  — before the Data Agent: verify schemas, DB, and CDN are ready
  post — after the Data Agent: check data quality and review error log

Usage:
    python health_agent.py --mode pre
    python health_agent.py --mode post

Output: PASS / WARN / BLOCK per check, with an overall status.
Triggers: Update Agent if BLOCK is returned.
"""

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone

import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT          = os.path.join(os.path.dirname(__file__), "../../..")
DATA_DIR      = os.path.join(ROOT, "data")
SCHEMAS_DIR   = os.path.join(ROOT, ".claude/schemas")
DB_PATH       = os.path.join(DATA_DIR, "referee_tracker.db")
ERROR_LOG     = os.path.join(DATA_DIR, "error_log.jsonl")
LAST_RUN      = os.path.join(DATA_DIR, "last_run.json")
CDN_TEST_URL  = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

MIN_FOULS_PER_GAME    = 10    # below this → WARN
ERROR_RATE_WARN_PCT   = 5.0   # above this → WARN
ERROR_RATE_BLOCK_PCT  = 20.0  # above this → BLOCK
NULL_RATE_WARN_PCT    = 2.0   # for official_id / official_name → WARN
TECH_RATE_WARN_PCT    = 10.0  # technicals > 10% of all fouls → WARN

# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------

PASS  = "PASS"
WARN  = "WARN"
BLOCK = "BLOCK"


def result(status, check, message):
    return {"status": status, "check": check, "message": message}


def overall_status(results):
    """Roll up: any BLOCK → BLOCK, any WARN → WARN, else PASS."""
    statuses = {r["status"] for r in results}
    if BLOCK in statuses:
        return BLOCK
    if WARN in statuses:
        return WARN
    return PASS


def print_report(results, mode):
    print(f"\n=== Health Agent — {mode.upper()} RUN CHECK ===\n")
    for r in results:
        icon = {"PASS": "✓", "WARN": "!", "BLOCK": "✗"}.get(r["status"], "?")
        print(f"  [{r['status']}] {icon}  {r['check']}: {r['message']}")
    status = overall_status(results)
    print(f"\n  Overall: {status}\n")
    return status


# ---------------------------------------------------------------------------
# Pre-run checks
# ---------------------------------------------------------------------------

def check_schemas():
    """Verify all schema files are present and valid JSON."""
    expected = [
        "foul_event.schema.json",
        "referee.schema.json",
        "player.schema.json",
        "game.schema.json",
    ]
    missing, invalid = [], []

    for fname in expected:
        path = os.path.join(SCHEMAS_DIR, fname)
        if not os.path.exists(path):
            missing.append(fname)
            continue
        try:
            with open(path) as f:
                json.load(f)
        except json.JSONDecodeError:
            invalid.append(fname)

    if missing:
        return result(BLOCK, "Schemas", f"Missing: {missing}")
    if invalid:
        return result(BLOCK, "Schemas", f"Invalid JSON: {invalid}")
    return result(PASS, "Schemas", f"{len(expected)} schema files valid")


def check_database():
    """Verify DB file exists and all expected tables are present."""
    if not os.path.exists(DB_PATH):
        return result(WARN, "Database", "DB file not found — will be created on first run")

    try:
        conn = sqlite3.connect(DB_PATH)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
    except Exception as e:
        return result(BLOCK, "Database", f"Cannot connect: {e}")

    expected_tables = {"games", "foul_events", "players", "referees"}
    missing = expected_tables - tables
    if missing:
        return result(BLOCK, "Database", f"Missing tables: {missing}")

    return result(PASS, "Database", "Accessible, all tables present")


def check_cdn():
    """Verify NBA CDN is reachable."""
    try:
        r = requests.get(CDN_TEST_URL, timeout=10)
        if r.status_code == 200:
            return result(PASS, "CDN", "cdn.nba.com reachable")
        return result(BLOCK, "CDN", f"CDN returned status {r.status_code}")
    except requests.exceptions.Timeout:
        return result(BLOCK, "CDN", "CDN request timed out")
    except Exception as e:
        return result(BLOCK, "CDN", f"CDN unreachable: {e}")


def run_pre_check():
    results = [
        check_schemas(),
        check_database(),
        check_cdn(),
    ]
    return results


# ---------------------------------------------------------------------------
# Post-run checks
# ---------------------------------------------------------------------------

def check_last_run():
    """Check last_run.json exists and error rate is acceptable."""
    if not os.path.exists(LAST_RUN):
        return result(WARN, "Last Run", "last_run.json not found — has the Data Agent run yet?")

    with open(LAST_RUN) as f:
        run = json.load(f)

    rate = run.get("error_rate_pct", 0)
    summary = (
        f"run_id={run.get('run_id')}  "
        f"games={run.get('games_processed')}  "
        f"fouls={run.get('total_fouls')}  "
        f"errors={run.get('total_errors')} ({rate}%)"
    )

    if rate >= ERROR_RATE_BLOCK_PCT:
        return result(BLOCK, "Last Run", f"Error rate {rate}% exceeds {ERROR_RATE_BLOCK_PCT}% threshold. {summary}")
    if rate >= ERROR_RATE_WARN_PCT:
        return result(WARN, "Last Run", f"Error rate {rate}% exceeds {ERROR_RATE_WARN_PCT}% threshold. {summary}")
    return result(PASS, "Last Run", summary)


def check_error_log():
    """Surface recent errors from error_log.jsonl grouped by reason."""
    if not os.path.exists(ERROR_LOG):
        return result(PASS, "Error Log", "No error log file — no errors recorded yet")

    entries = []
    with open(ERROR_LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not entries:
        return result(PASS, "Error Log", "Error log is empty")

    # Group by reason
    reasons = {}
    for e in entries:
        reason = e.get("reason", "unknown")
        reasons[reason] = reasons.get(reason, 0) + 1

    lines = [f"{count}x '{reason}'" for reason, count in sorted(reasons.items(), key=lambda x: -x[1])]
    return result(WARN, "Error Log", f"{len(entries)} total errors logged — " + ", ".join(lines))


def check_data_quality():
    """Check foul_events table for data quality issues."""
    if not os.path.exists(DB_PATH):
        return [result(WARN, "Data Quality", "DB not found — skipping quality checks")]

    conn = sqlite3.connect(DB_PATH)
    results = []

    # Total counts
    total_fouls = conn.execute("SELECT COUNT(*) FROM foul_events").fetchone()[0]
    total_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]

    if total_fouls == 0:
        conn.close()
        return [result(BLOCK, "Data Quality", "foul_events table is empty")]

    # Games with 0 foul events
    empty_games = conn.execute("""
        SELECT g.game_id, g.away_team_tricode, g.home_team_tricode
        FROM games g
        LEFT JOIN foul_events f ON g.game_id = f.game_id
        GROUP BY g.game_id
        HAVING COUNT(f.action_number) = 0
    """).fetchall()
    if empty_games:
        ids = [f"{r[1]}@{r[2]} ({r[0]})" for r in empty_games]
        results.append(result(BLOCK, "Data Quality", f"Games with 0 fouls: {ids}"))
    else:
        results.append(result(PASS, "Data Quality — Empty games", f"All {total_games} games have foul events"))

    # Games with suspiciously low foul counts
    low_games = conn.execute(f"""
        SELECT g.game_id, g.away_team_tricode, g.home_team_tricode, COUNT(f.action_number) as foul_count
        FROM games g
        JOIN foul_events f ON g.game_id = f.game_id
        GROUP BY g.game_id
        HAVING foul_count < {MIN_FOULS_PER_GAME}
    """).fetchall()
    if low_games:
        ids = [f"{r[1]}@{r[2]} ({r[3]} fouls)" for r in low_games]
        results.append(result(WARN, "Data Quality — Low foul counts", f"Games below {MIN_FOULS_PER_GAME} fouls: {ids}"))
    else:
        results.append(result(PASS, "Data Quality — Low foul counts", f"All games at or above {MIN_FOULS_PER_GAME} fouls"))

    # Null rate on official_name
    null_officials = conn.execute(
        "SELECT COUNT(*) FROM foul_events WHERE official_name IS NULL"
    ).fetchone()[0]
    null_rate = round(null_officials / total_fouls * 100, 2)
    if null_rate > NULL_RATE_WARN_PCT:
        results.append(result(WARN, "Data Quality — Null official_name",
            f"{null_officials} nulls ({null_rate}%) — above {NULL_RATE_WARN_PCT}% threshold"))
    else:
        results.append(result(PASS, "Data Quality — Null official_name",
            f"{null_officials} nulls ({null_rate}%)"))

    # Null rate on fouled_player_id (technicals expected to be null)
    null_fouled = conn.execute(
        "SELECT COUNT(*) FROM foul_events WHERE fouled_player_id IS NULL AND foul_detail != 'technical'"
    ).fetchone()[0]
    if null_fouled > 0:
        results.append(result(WARN, "Data Quality — Null fouled_player_id",
            f"{null_fouled} non-technical fouls missing fouled_player_id"))
    else:
        results.append(result(PASS, "Data Quality — Null fouled_player_id",
            "All non-technical fouls have fouled_player_id"))

    # Technical foul rate
    tech_count = conn.execute(
        "SELECT COUNT(*) FROM foul_events WHERE foul_detail = 'technical'"
    ).fetchone()[0]
    tech_rate = round(tech_count / total_fouls * 100, 2)
    if tech_rate > TECH_RATE_WARN_PCT:
        results.append(result(WARN, "Data Quality — Technical foul rate",
            f"{tech_rate}% technical fouls — above {TECH_RATE_WARN_PCT}% threshold (unusual)"))
    else:
        results.append(result(PASS, "Data Quality — Technical foul rate",
            f"{tech_count} technicals ({tech_rate}% of {total_fouls} total)"))

    conn.close()
    return results


def run_post_check():
    results = [
        check_last_run(),
        check_error_log(),
    ]
    results += check_data_quality()
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NBA Referee Tracker — Health Agent")
    parser.add_argument("--mode", choices=["pre", "post"], required=True,
                        help="pre: check before Data Agent run. post: check after.")
    args = parser.parse_args()

    if args.mode == "pre":
        results = run_pre_check()
    else:
        results = run_post_check()

    status = print_report(results, args.mode)

    # Exit code: 0 = PASS/WARN, 1 = BLOCK (allows shell scripting / Orchestrator integration)
    exit(0 if status != BLOCK else 1)
