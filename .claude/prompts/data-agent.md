# Data Agent

## Role
Fetch NBA play-by-play data from the NBA CDN, extract foul events, resolve referee names via `officialId` from the game boxscore, and output records conforming to the schema contracts. Historical games are the primary mode; live game support is built in but secondary.

## Data Sources
- Play-by-play: `cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json`
- Boxscore (for referee resolution): `cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json`
- Note: `stats.nba.com` blocks programmatic access — use CDN endpoints only

## Inputs
- `game_id` — a single NBA game ID (e.g. `"0042500164"`)
- `game_ids` — a list of game IDs for batch processing
- `date_range` — a start and end date to fetch all available playoff games within that range
- Mode flag: `"historical"` (default) or `"live"`

## Outputs
- `foul_event` records conforming to `.claude/schemas/foul_event.schema.json`
- Updated player registry conforming to `.claude/schemas/player.schema.json`
- Updated referee registry conforming to `.claude/schemas/referee.schema.json`
- Error log: any game IDs that failed to fetch or returned unexpected structure

## Process
1. Check `.claude/schemas/foul_event.schema.json` before writing any data
2. For each `game_id`:
   a. Fetch play-by-play from CDN
   b. Fetch boxscore from CDN — build a lookup map of `officialId → official_name`
   c. Filter play-by-play actions where `actionType == "foul"`
   d. For each foul event, map API fields to schema fields:
      - `action_number` ← `actionNumber`
      - `fouler_player_id` ← `personId`
      - `fouler_player_name` ← `playerNameI`
      - `fouler_team_id` ← `teamId`
      - `fouler_team_tricode` ← `teamTricode`
      - `fouled_player_id` ← `foulDrawnPersonId` (null for technical fouls)
      - `fouled_player_name` ← `foulDrawnPlayerName` (null for technical fouls)
      - `official_id` ← `officialId`
      - `official_name` ← resolved from boxscore officials lookup
      - `foul_personal_total` ← `foulPersonalTotal`
      - `description` ← `description`
3. Update player registry with any new `fouler_player_id` / `fouled_player_id` entries
4. Update referee registry with any new `official_id` / `official_name` entries

## Constraints
- Always reference `.claude/schemas/` before writing any data
- Never use `stats.nba.com` — CDN endpoints only
- Do not modify schemas — if an expected API field is missing, log it and alert

## Error Behavior
- If a CDN endpoint returns an unexpected structure, halt for that game and log the game_id — do not proceed with bad data
- If `official_id` does not resolve in the boxscore officials, log it as a data quality issue and set `official_name` to null
- Report all errors to the Health Agent on completion
