"""
Orchestrator: Coordinate all agents in the correct sequence.

Pipeline sequence:
  1. Health Agent  pre-run
  2. Data Agent
  3. Health Agent  post-run

Two pipeline modes:
  daily       — run yesterday's Final games (used by Automation Agent)
  historical  — backfill a full season by year (manual)

Usage:
    python orchestrator.py                         # daily mode (yesterday's games)
    python orchestrator.py --mode historical --season 2023-24
    python orchestrator.py --game 0042500164       # single game

Notifications: macOS native (osascript) — appears in Notification Center.
Exit code: 0 = pipeline completed (PASS or WARN), 1 = pipeline halted (BLOCK).
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT          = os.path.join(os.path.dirname(__file__), "../../..")
DATA_DIR      = os.path.join(ROOT, "data")
AGENTS_DIR    = os.path.join(ROOT, "src/agents")
LAST_ORCH_RUN = os.path.join(DATA_DIR, "last_orchestrator_run.json")

PYTHON        = sys.executable  # use same Python env as orchestrator

# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------

def notify(title, message):
    """Send a macOS native notification via osascript."""
    script = f'display notification "{message}" with title "{title}"'
    try:
        subprocess.run(["osascript", "-e", script], check=False)
    except FileNotFoundError:
        pass  # osascript not available (non-Mac)
    print(f"\n  NOTIFICATION: {title} — {message}\n")


def notify_block(agent_name, detail):
    notify(
        "Referee Tracker — Pipeline Halted",
        f"{agent_name} returned BLOCK: {detail}"
    )


def notify_complete(fouls_written, warnings):
    msg = f"{fouls_written} foul events written."
    if warnings:
        msg += f" {len(warnings)} warning(s) — check last_orchestrator_run.json."
    notify("Referee Tracker — Pipeline Complete", msg)

# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

def run_agent(label, cmd):
    """
    Run an agent subprocess. Streams output live.
    Returns exit_code.
    """
    print(f"\n{'─' * 60}")
    print(f"  Running: {label}")
    print(f"{'─' * 60}\n")

    result = subprocess.run(cmd, capture_output=False, text=True)
    return result.returncode

# ---------------------------------------------------------------------------
# Run summary
# ---------------------------------------------------------------------------

def write_run_summary(run_id, mode, steps, halted_at, warnings):
    summary = {
        "run_id":     run_id,
        "mode":       mode,
        "halted_at":  halted_at,
        "completed":  halted_at is None,
        "warnings":   warnings,
        "steps":      steps,
    }
    with open(LAST_ORCH_RUN, "w") as f:
        json.dump(summary, f, indent=2)


def print_summary(run_id, mode, steps, halted_at, warnings):
    print(f"\n{'=' * 60}")
    print(f"  ORCHESTRATOR RUN SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Run ID   : {run_id}")
    print(f"  Mode     : {mode}")
    print(f"  Status   : {'HALTED at ' + halted_at if halted_at else 'COMPLETED'}")
    print()
    for step in steps:
        icon = {"skipped": "─", "pass": "✓", "warn": "!", "block": "✗", "ok": "✓"}.get(step["result"], "?")
        print(f"  [{step['result'].upper():<7}] {icon}  {step['agent']}")
    if warnings:
        print(f"\n  Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"    ! {w}")
    print(f"\n  Summary written to: {LAST_ORCH_RUN}")
    print(f"{'=' * 60}\n")

# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(mode="daily", game_id=None, season=None):
    run_id    = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    steps     = []
    warnings  = []
    halted_at = None

    print(f"\n{'=' * 60}")
    print(f"  REFEREE TRACKER — PIPELINE START")
    print(f"  Mode: {mode.upper()}")
    print(f"  {run_id}")
    print(f"{'=' * 60}")

    health_agent = os.path.join(AGENTS_DIR, "health_agent/health_agent.py")
    data_agent   = os.path.join(AGENTS_DIR, "data_agent/agent.py")

    # ------------------------------------------------------------------
    # Step 1: Health Agent — pre-run
    # ------------------------------------------------------------------
    exit_code = run_agent(
        "Health Agent (pre-run)",
        [PYTHON, health_agent, "--mode", "pre"]
    )
    if exit_code == 1:
        steps.append({"agent": "Health Agent (pre)", "result": "block"})
        halted_at = "Health Agent (pre-run)"
        notify_block("Health Agent (pre-run)", "Pre-run checks failed — pipeline cannot start safely.")
        write_run_summary(run_id, mode, steps, halted_at, warnings)
        print_summary(run_id, mode, steps, halted_at, warnings)
        return 1
    steps.append({"agent": "Health Agent (pre)", "result": "pass"})

    # ------------------------------------------------------------------
    # Step 2: Data Agent
    # ------------------------------------------------------------------
    data_cmd = [PYTHON, data_agent]
    if game_id:
        data_cmd += ["--game", game_id]
    elif mode == "historical" and season:
        data_cmd += ["--season", season]
    elif mode == "daily":
        data_cmd += ["--mode", "daily"]

    exit_code = run_agent("Data Agent", data_cmd)
    if exit_code != 0:
        steps.append({"agent": "Data Agent", "result": "block"})
        halted_at = "Data Agent"
        notify_block("Data Agent", "Data Agent exited with an error — check output above.")
        write_run_summary(run_id, mode, steps, halted_at, warnings)
        print_summary(run_id, mode, steps, halted_at, warnings)
        return 1
    steps.append({"agent": "Data Agent", "result": "ok"})

    # ------------------------------------------------------------------
    # Step 3: Health Agent — post-run
    # ------------------------------------------------------------------
    exit_code = run_agent(
        "Health Agent (post-run)",
        [PYTHON, health_agent, "--mode", "post"]
    )
    if exit_code == 1:
        steps.append({"agent": "Health Agent (post)", "result": "block"})
        halted_at = "Health Agent (post-run)"
        notify_block("Health Agent (post-run)", "Data quality checks failed — check health_agent output.")
        write_run_summary(run_id, mode, steps, halted_at, warnings)
        print_summary(run_id, mode, steps, halted_at, warnings)
        return 1

    if exit_code == 2:
        steps.append({"agent": "Health Agent (post)", "result": "warn"})
        warnings.append("Health Agent post-run returned WARN — review last_run.json and error_log.jsonl.")
    else:
        steps.append({"agent": "Health Agent (post)", "result": "pass"})

    # ------------------------------------------------------------------
    # Done
    # ------------------------------------------------------------------
    fouls_written = 0
    try:
        with open(os.path.join(DATA_DIR, "last_run.json")) as f:
            fouls_written = json.load(f).get("total_fouls", 0)
    except Exception:
        pass

    write_run_summary(run_id, mode, steps, halted_at, warnings)
    print_summary(run_id, mode, steps, halted_at, warnings)
    notify_complete(fouls_written, warnings)
    return 0

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NBA Referee Tracker — Orchestrator")
    parser.add_argument("--mode", choices=["daily", "historical"], default="daily",
                        help="daily: yesterday's Final games. historical: full season backfill.")
    parser.add_argument("--season", help="Season to backfill (e.g. 2023-24). Used with --mode historical.")
    parser.add_argument("--game", help="Single game ID to process.")
    args = parser.parse_args()

    exit_code = run(mode=args.mode, game_id=args.game, season=args.season)
    exit(exit_code)
