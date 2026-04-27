"""
Data Agent - Steps 1, 2 & 3: Fetch, inspect, and transform foul events from NBA CDN.

Uses NBA CDN endpoints (stats.nba.com blocks programmatic access):
  - Play-by-play: cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json
  - Boxscore:     cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json

Prints:
  - Raw field names from a foul event (Step 1)
  - Sample foul events with all schema-relevant fields (Step 2)
  - Final schema-conforming foul_event records (Step 3)
"""

import json
import requests
from transform import transform_game, build_officials_lookup

CDN_BASE = "https://cdn.nba.com/static/json/liveData"
GAME_ID = "0042500164"  # DEN vs MIN, 2024-25 playoffs — confirmed working


def fetch_json(url):
    """Fetch JSON from the NBA CDN. Raises on non-200."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_play_by_play(game_id):
    """Fetch play-by-play actions for a game. Returns list of action dicts."""
    url = f"{CDN_BASE}/playbyplay/playbyplay_{game_id}.json"
    print(f"Fetching play-by-play: {url}")
    data = fetch_json(url)
    return data["game"]["actions"]


def fetch_boxscore(game_id):
    """Fetch boxscore data for a game. Returns the full response dict."""
    url = f"{CDN_BASE}/boxscore/boxscore_{game_id}.json"
    print(f"Fetching boxscore:     {url}")
    return fetch_json(url)


def inspect_fields(actions):
    """Step 1: Print all field names on a foul event."""
    fouls = [a for a in actions if a.get("actionType") == "foul"]
    if not fouls:
        print("No foul events found.")
        return

    print("\n--- STEP 1: Foul Event Field Names ---")
    print(f"Total actions in game: {len(actions)}")
    print(f"Foul events:           {len(fouls)}")
    print(f"\nAll fields on a foul event ({len(fouls[0])} total):")
    for key, value in fouls[0].items():
        print(f"  {key}: {value!r}")


def inspect_foul_events(actions, officials):
    """Step 2: Print schema-relevant fields for sample foul events."""
    fouls = [a for a in actions if a.get("actionType") == "foul"]

    subtypes = {}
    for f in fouls:
        st = f.get("subType", "")
        subtypes[st] = subtypes.get(st, 0) + 1

    print(f"\n--- STEP 2: Foul Events (schema view) ---")
    print(f"Subtypes: {subtypes}")
    print(f"\nSample foul events (first 15) mapped to schema fields:\n")

    for i, f in enumerate(fouls[:15]):
        official_id = f.get("officialId")
        print(f"[{i+1}] action_number={f.get('actionNumber')}  "
              f"period={f.get('period')}  clock={f.get('clock')}")
        print(f"  foul_subtype:        {f.get('subType')}")
        print(f"  fouler_player_id:    {f.get('personId')}")
        print(f"  fouler_player_name:  {f.get('playerNameI')}")
        print(f"  fouler_team_tricode: {f.get('teamTricode')}")
        print(f"  fouled_player_id:    {f.get('foulDrawnPersonId')}")
        print(f"  fouled_player_name:  {f.get('foulDrawnPlayerName')}")
        print(f"  official_id:         {official_id}")
        print(f"  official_name:       {officials_lookup.get(official_id, 'NOT FOUND')}")
        print(f"  foul_personal_total: {f.get('foulPersonalTotal')}")
        print(f"  description:         {f.get('description')}")
        print()


def run_step3(actions, boxscore_data, game_id):
    """Step 3: Transform raw foul events into schema-conforming records."""
    officials_lookup = build_officials_lookup(boxscore_data)
    records, errors = transform_game(actions, game_id, officials_lookup)

    print(f"\n--- STEP 3: Schema-Conforming foul_event Records ---")
    print(f"Records produced: {len(records)}")
    print(f"Errors:           {len(errors)}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  action_number={e['action_number']}: {e['reason']}")

    print("\nSample records (first 3):")
    for record in records[:3]:
        print(json.dumps(record, indent=2, ensure_ascii=False))
        print()


if __name__ == "__main__":
    actions = fetch_play_by_play(GAME_ID)
    boxscore_data = fetch_boxscore(GAME_ID)
    officials_lookup = build_officials_lookup(boxscore_data)

    inspect_fields(actions)
    inspect_foul_events(actions, officials_lookup)
    run_step3(actions, boxscore_data, GAME_ID)
