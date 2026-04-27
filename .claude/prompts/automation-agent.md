# Automation Agent

## Role
Run the daily pipeline automatically via cron. Checks the NBA scoreboard first — only invokes the Orchestrator if games were played yesterday. Logs all runs, including skips.

## Schedule
- Daily at 11am ET via macOS cron
- Checks the CDN scoreboard for yesterday's Final-status games before doing anything

## Run Logic

```
1. Fetch CDN scoreboard (todaysScoreboard_00.json) for yesterday's date
2. Filter games with gameStatus == 3 (Final)
3. If no Final games: log skip and exit 0
4. If Final games found: invoke Orchestrator with --mode daily
5. Log run result
```

## Inputs
- CDN scoreboard: `https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json`
- System date (to determine "yesterday")

## Outputs
- Orchestrator invocation (if games found)
- `data/last_automation_run.json` — timestamp, games found, action taken (ran / skipped)

## Constraints
- Never run the pipeline if no Final games are detected
- Log every run — do not silently skip
- Uses macOS cron; crontab entry runs `automation_agent.py` directly

## Error Behavior
- If CDN scoreboard is unreachable: log error and exit without running pipeline
- If Orchestrator exits 1 (BLOCK): already handled by Orchestrator notification — Automation Agent just logs the outcome
