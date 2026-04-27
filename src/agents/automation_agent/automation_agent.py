"""
Automation Agent: Daily cron entry point for the Referee Tracker pipeline.

Runs at 11am ET every day via macOS cron. Checks the NBA CDN season schedule
for all Final games since the last successful run. If games are found, invokes
the Orchestrator in daily mode with all missed game IDs. Logs every run.

Catch-up logic: if the laptop was off for N days, the next run collects all
Final games from the missed dates and processes them in one pipeline run.

Usage:
    python automation_agent.py           # normal daily run (with catch-up)
    python automation_agent.py --dry-run # check only, do not invoke orchestrator

Crontab (11am ET = 15:00 UTC):
    0 15 * * * cd "/Users/jeffreykang/Referee Tracker" && /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 "/Users/jeffreykang/Referee Tracker/src/agents/automation_agent/automation_agent.py" >> "/Users/jeffreykang/Referee Tracker/data/automation_cron.log" 2>&1
"""

import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT          = os.path.join(os.path.dirname(__file__), "../../..")
DATA_DIR      = os.path.join(ROOT, "data")
LAST_AUTO_RUN = os.path.join(DATA_DIR, "last_automation_run.json")
ORCHESTRATOR  = os.path.join(ROOT, "src/agents/orchestrator/orchestrator.py")

CDN_SCHEDULE  = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"
PYTHON        = sys.executable

# ---------------------------------------------------------------------------
# Schedule helpers
# ---------------------------------------------------------------------------

def fetch_schedule():
    """Fetch the full CDN season schedule. Returns (data, error_message)."""
    try:
        r = requests.get(CDN_SCHEDULE, timeout=30)
        if r.status_code == 200:
            return r.json(), None
        return None, f"HTTP {r.status_code}"
    except requests.exceptions.Timeout:
        return None, "Request timed out"
    except Exception as e:
        return None, str(e)


def get_final_games_for_dates(schedule_data, target_dates):
    """
    Return game IDs from the schedule that are Final (gameStatus == 3)
    and fall on any of the target dates (set of 'YYYY-MM-DD' strings).

    CDN gameDate format: 'MM/DD/YYYY HH:MM:SS'
    """
    game_dates = schedule_data.get("leagueSchedule", {}).get("gameDates", [])
    found = {}  # date -> [game_id, ...]

    for entry in game_dates:
        raw = entry.get("gameDate", "")
        # Parse 'MM/DD/YYYY HH:MM:SS' → 'YYYY-MM-DD'
        try:
            dt = datetime.strptime(raw, "%m/%d/%Y %H:%M:%S")
            date_str = dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

        if date_str not in target_dates:
            continue

        for game in entry.get("games", []):
            if game.get("gameStatus") == 3:
                found.setdefault(date_str, []).append(game["gameId"])

    return found  # {date_str: [game_ids]}

# ---------------------------------------------------------------------------
# Last run tracking
# ---------------------------------------------------------------------------

def load_last_run():
    """Return last_automation_run.json or None if it doesn't exist."""
    if not os.path.exists(LAST_AUTO_RUN):
        return None
    with open(LAST_AUTO_RUN) as f:
        return json.load(f)


def get_date_range_to_check():
    """
    Return a set of 'YYYY-MM-DD' strings covering all dates that need checking:
    from the day after the last successful run through yesterday (ET).

    If no prior run exists, checks only yesterday.
    """
    # "Yesterday" in ET — approximate as UTC-5 (works for 11am ET runs)
    yesterday = (datetime.now(timezone.utc) - timedelta(hours=5) - timedelta(days=1)).date()

    last = load_last_run()
    if last and last.get("action") in ("ran", "skipped") and last.get("last_date_checked"):
        try:
            last_date = date.fromisoformat(last["last_date_checked"])
        except ValueError:
            last_date = yesterday - timedelta(days=1)
    else:
        last_date = yesterday - timedelta(days=1)

    # Dates from last_date+1 through yesterday (inclusive)
    dates = set()
    d = last_date + timedelta(days=1)
    while d <= yesterday:
        dates.add(str(d))
        d += timedelta(days=1)

    return dates, str(yesterday)


# ---------------------------------------------------------------------------
# Run log
# ---------------------------------------------------------------------------

def write_run_log(run_id, dates_checked, action, games_found, last_date_checked, error=None):
    entry = {
        "run_id":             run_id,
        "dates_checked":      sorted(dates_checked),
        "last_date_checked":  last_date_checked,
        "action":             action,   # "ran" | "ran-block" | "skipped" | "error" | "dry-run"
        "games_found":        games_found,
        "error":              error,
    }
    with open(LAST_AUTO_RUN, "w") as f:
        json.dump(entry, f, indent=2)
    return entry

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(dry_run=False):
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    dates_to_check, yesterday = get_date_range_to_check()

    print(f"\n{'=' * 60}")
    print(f"  AUTOMATION AGENT — {run_id}")
    if len(dates_to_check) > 1:
        print(f"  Catch-up: checking {len(dates_to_check)} dates: {sorted(dates_to_check)}")
    else:
        print(f"  Checking for Final games on {sorted(dates_to_check)}")
    print(f"{'=' * 60}\n")

    # 1. Fetch season schedule
    data, err = fetch_schedule()
    if err:
        print(f"  ERROR: CDN schedule unreachable — {err}")
        write_run_log(run_id, dates_to_check, "error", [], yesterday, error=err)
        return 1

    # 2. Find Final games across all dates
    games_by_date = get_final_games_for_dates(data, dates_to_check)
    all_game_ids  = [gid for ids in games_by_date.values() for gid in ids]

    if not games_by_date:
        print(f"  No Final games found for checked dates. Skipping pipeline.")
        write_run_log(run_id, dates_to_check, "skipped", [], yesterday)
        return 0

    for d in sorted(games_by_date):
        print(f"  {d}: {len(games_by_date[d])} Final game(s) — {games_by_date[d]}")
    print(f"\n  Total: {len(all_game_ids)} game(s) to process.")

    if dry_run:
        print("  [DRY RUN] Would invoke Orchestrator with the above game IDs.")
        write_run_log(run_id, dates_to_check, "dry-run", all_game_ids, yesterday)
        return 0

    # 3. Invoke Orchestrator — pass game IDs via a temp file so we don't shell-escape a long list
    games_file = os.path.join(DATA_DIR, "pending_game_ids.json")
    with open(games_file, "w") as f:
        json.dump(all_game_ids, f)

    print(f"\n  Invoking Orchestrator (--mode daily)...\n")
    result = subprocess.run(
        [PYTHON, ORCHESTRATOR, "--mode", "daily"],
        capture_output=False,
        text=True,
    )

    action = "ran" if result.returncode == 0 else "ran-block"
    write_run_log(run_id, dates_to_check, action, all_game_ids, yesterday)
    return result.returncode

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="NBA Referee Tracker — Automation Agent")
    parser.add_argument("--dry-run", action="store_true",
                        help="Check schedule only — do not invoke Orchestrator.")
    args = parser.parse_args()

    sys.exit(run(dry_run=args.dry_run))
