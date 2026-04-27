"""
Data Agent - Transform: Map raw NBA CDN foul events to foul_event schema records.

Schema reference: .claude/schemas/foul_event.schema.json
"""


def extract_foul_detail(description, subtype):
    """
    Parse the granular foul category from a play description.

    Categories (mutually exclusive, checked in priority order):
      technical  — any technical foul
      flagrant_2 — flagrant foul type 2
      flagrant_1 — flagrant foul type 1
      offensive  — offensive foul
      loose_ball — loose ball foul
      shooting   — shooting foul
      personal   — all other personal fouls

    Note: 'total non-technical fouls' = any record where foul_detail != 'technical'.
    This is a derived count — not a stored field.
    """
    if subtype == "technical":
        return "technical"
    desc = (description or "").lower()
    if "flagrant-type-2" in desc:
        return "flagrant_2"
    if "flagrant-type-1" in desc:
        return "flagrant_1"
    if "offensive" in desc:
        return "offensive"
    if "loose ball" in desc:
        return "loose_ball"
    if "shooting" in desc:
        return "shooting"
    return "personal"


def build_officials_lookup(boxscore_data):
    """
    Build a lookup of officialId -> official_name from boxscore data.
    Returns dict: {personId (int): name (str)}
    """
    officials = boxscore_data["game"]["officials"]
    return {o["personId"]: o["name"] for o in officials}


def transform_foul_event(action, game_id, officials_lookup):
    """
    Map a single raw CDN foul action to a foul_event schema record.

    Returns a dict conforming to foul_event.schema.json.
    Returns None if the action is not a foul event.
    """
    if action.get("actionType") != "foul":
        return None

    official_id = action.get("officialId")
    subtype     = action.get("subType")
    description = action.get("description")

    return {
        "game_id":             game_id,
        "action_number":       action.get("actionNumber"),
        "period":              action.get("period"),
        "clock":               action.get("clock"),
        "foul_type":           action.get("actionType"),           # always "foul"
        "foul_subtype":        subtype,                            # "personal" or "technical"
        "foul_detail":         extract_foul_detail(description, subtype),
        "fouler_player_id":    action.get("personId"),
        "fouler_player_name":  action.get("playerNameI"),
        "fouler_team_id":      action.get("teamId"),
        "fouler_team_tricode": action.get("teamTricode"),
        "fouled_player_id":    action.get("foulDrawnPersonId"),    # null for technicals
        "fouled_player_name":  action.get("foulDrawnPlayerName"),  # null for technicals
        "official_id":         official_id,
        "official_name":       officials_lookup.get(official_id),
        "foul_personal_total": action.get("foulPersonalTotal"),
        "description":         description,
    }


def is_team_foul(action):
    """
    Team fouls (coach/bench technicals) have no individual player attributed.
    Detected by 'TEAM foul' in the description. These are excluded from
    foul_events — they don't contribute to referee-player relationships.
    """
    return "team foul" in (action.get("description") or "").lower()


def transform_game(actions, game_id, officials_lookup):
    """
    Transform all foul events from a game into schema-conforming records.

    Returns:
        records (list[dict]):    foul_event records
        errors (list[dict]):     actions that failed transformation with reason
        team_foul_count (int):   team fouls skipped (known category, not errors)
    """
    records         = []
    errors          = []
    team_foul_count = 0

    for action in actions:
        if action.get("actionType") != "foul":
            continue

        # Team fouls have no player — excluded from foul_events, not logged as errors
        if is_team_foul(action):
            team_foul_count += 1
            continue

        record = transform_foul_event(action, game_id, officials_lookup)

        # Check that required fields are present
        missing = [
            field for field in (
                "game_id", "action_number", "period", "clock",
                "foul_type", "foul_subtype",
                "fouler_player_id", "fouler_player_name",
                "fouler_team_id", "fouler_team_tricode",
                "official_id", "official_name", "description",
            )
            if record.get(field) is None
        ]

        if missing:
            errors.append({
                "action_number": action.get("actionNumber"),
                "reason": f"Missing required fields: {missing}",
                "raw": action,
            })
        else:
            records.append(record)

    return records, errors, team_foul_count
