# Orchestrator

## Role
Coordinate all agents in the correct sequence, manage error handling, and surface failures to the user. Acts as the single point of control for the pipeline.

## Pipeline Modes

| Mode | Trigger | Data Agent invocation |
|---|---|---|
| `daily` | Automation Agent (cron 11am ET) | `--mode daily` (fetches yesterday's Final games) |
| `historical` | Manual | `--season 2023-24` (full season backfill) |
| single game | Manual | `--game 0042500164` |

## Run Sequence

```
Health Agent (pre-run) → if BLOCK: halt, notify
Data Agent             → if exit 1: halt, notify
Health Agent (post-run)→ WARN: continue + flag; BLOCK: halt, notify
Notify complete
```

## Outputs
- Per-agent status (PASS / WARN / BLOCK / OK)
- macOS native notification on completion or halt
- `data/last_orchestrator_run.json` — run summary with all step results and warnings

## Error Behavior
- On BLOCK from any agent: halt immediately, send notification, write summary, exit 1
- On WARN from Health Agent post-run: continue, include in warnings, send completion notification
- Never silently absorb an error
