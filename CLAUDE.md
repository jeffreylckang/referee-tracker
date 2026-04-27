# Referee Tracker — Claude Instructions

## 1. Project Overview

This project tracks foul calls made by NBA referees, starting with the 2025-26 playoffs. Data comes from the NBA CDN (`cdn.nba.com`) — `stats.nba.com` blocks programmatic access. Each foul event in the play-by-play contains an `officialId` that maps directly to a referee in the game's boxscore, and `foulDrawnPersonId`/`foulDrawnPlayerName` that identify the fouled player — no parsing required. The end goal is a 3D social network visualization connecting referees, players, and foul events to surface patterns in how individual referees call fouls. CDN historical data is available from 2019-20 through 2025-26 (7 seasons). Future scope includes live game tracking and the English Premier League.

## 2. Working Style

- Always plan and outline the approach before writing any code or creating files
- Present the plan to the user and wait for explicit confirmation before executing
- Work one step at a time — complete and confirm each step before moving to the next
- Do not do everything at once, even if the full solution is clear
- Prefer editing existing files over creating new ones
- Keep solutions simple — do not add error handling, abstractions, or features beyond what was asked
- When scope is unclear or a decision could go multiple ways, ask before acting

## 3. Agent Architecture

See `docs/architecture.md` for the full diagram and data flow.

Two pipeline modes:
- **Daily automated**: Automation Agent runs at 11am ET, checks scoreboard for yesterday's Final games, runs pipeline only if games were played.
- **Historical backfill**: Manual, specify season(s). CDN available from 2019-20 onward — warns if an older season is requested.

| Agent | Role |
|---|---|
| Orchestrator | Coordinates agents, manages pipeline sequence and error handling |
| Data Agent | Fetches play-by-play + boxscore from NBA CDN, extracts foul events, resolves referee names via `officialId`. Supports daily mode (yesterday's games) and historical backfill (full season by year). |
| Health Agent | Pre-run: verifies schemas, DB, and CDN. Post-run: checks data quality and error rates. Returns PASS/WARN/BLOCK. |
| Automation Agent | Runs daily at 11am ET via cron. Checks scoreboard for Final games before invoking the Orchestrator. |

## 4. Key References

| What | Where |
|---|---|
| Schema contracts (source of truth for all data shapes) | `.claude/schemas/` |
| Agent prompt templates | `.claude/prompts/` |
| Architecture diagram & data flow | `docs/architecture.md` |
| Project setup template (reusable for future projects) | `Setup_Structure.md` |

> Before writing any code that reads or writes data, check the relevant schema in `.claude/schemas/` first.
