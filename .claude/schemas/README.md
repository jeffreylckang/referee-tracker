# Schema Contracts

These files are the **primary source of truth** for all data shapes in this project.

## Rule
Before writing any code that reads or writes data, check the relevant schema here first. If a field is not in the schema, it does not exist as far as the system is concerned.

## Entities

| Schema | Description |
|---|---|
| `foul_event.schema.json` | One record per foul call — the central entity |
| `referee.schema.json` | One record per unique referee |
| `player.schema.json` | One record per unique player |
| `game.schema.json` | One record per game — context for foul events |

## Key Relationships

```
Referee ──called foul on──> Player (fouled / fouls drawn)
Referee ──called foul by──> Player (fouler / fouls committed)
FoulEvent ──occurred in──> Game
```

## Data Source

All foul event fields come directly from the NBA CDN — no text parsing required:

- `official_id` — direct field on each foul event; resolved to `official_name` via the game's boxscore officials list
- `fouled_player_id` / `fouled_player_name` — direct fields (`foulDrawnPersonId`, `foulDrawnPlayerName`)
- CDN endpoints: `cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json` and `cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json`
- Note: `stats.nba.com` blocks programmatic access; use CDN endpoints only

## Nullable Fields

Fields marked `nullable: true` may be `null` in the data. This applies to `fouled_player_id` and `fouled_player_name` for technical fouls (no specific player fouled). Downstream code must handle this gracefully.
