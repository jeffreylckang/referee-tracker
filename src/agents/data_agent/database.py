"""
Data Agent - Database: PostgreSQL setup and write operations.

Connection: reads DATABASE_URL environment variable.
Schema reference: .claude/schemas/
"""

import os
import psycopg2
from psycopg2.extras import execute_values


def get_connection():
    """Open and return a PostgreSQL connection using DATABASE_URL."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    # Render provides URLs starting with postgres:// — psycopg2 needs postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url)


def init_db(db_path=None):
    """
    Create tables and indexes if they don't exist.
    Returns a connection. db_path is ignored (kept for call-site compatibility).
    """
    conn = get_connection()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS games (
            game_id           TEXT PRIMARY KEY,
            away_team_tricode TEXT NOT NULL,
            home_team_tricode TEXT NOT NULL,
            game_date         TEXT,
            season            TEXT,
            playoff_round     TEXT,
            winner_tricode    TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_officials (
            game_id     TEXT    NOT NULL,
            official_id INTEGER NOT NULL,
            assignment  TEXT    NOT NULL,
            PRIMARY KEY (game_id, official_id),
            FOREIGN KEY (game_id) REFERENCES games(game_id)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_game_officials_official_id
            ON game_officials(official_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_game_officials_assignment
            ON game_officials(assignment)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS referees (
            official_id   INTEGER PRIMARY KEY,
            official_name TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS players (
            player_id    INTEGER PRIMARY KEY,
            player_name  TEXT NOT NULL,
            team_id      INTEGER,
            team_tricode TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS foul_events (
            game_id             TEXT    NOT NULL,
            action_number       INTEGER NOT NULL,
            period              INTEGER,
            clock               TEXT,
            foul_type           TEXT,
            foul_subtype        TEXT,
            fouler_player_id    INTEGER,
            fouler_player_name  TEXT,
            fouler_team_id      INTEGER,
            fouler_team_tricode TEXT,
            fouled_player_id    INTEGER,
            fouled_player_name  TEXT,
            official_id         INTEGER,
            official_name       TEXT,
            foul_detail         TEXT,
            foul_personal_total INTEGER,
            description         TEXT,
            PRIMARY KEY (game_id, action_number),
            FOREIGN KEY (game_id) REFERENCES games(game_id)
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_foul_events_official_id
            ON foul_events(official_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_foul_events_fouler_player_id
            ON foul_events(fouler_player_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_foul_events_fouled_player_id
            ON foul_events(fouled_player_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_foul_events_game_id
            ON foul_events(game_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_foul_events_fouler_team_tricode
            ON foul_events(fouler_team_tricode)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_foul_events_foul_detail
            ON foul_events(foul_detail)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_games_season
            ON games(season)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_games_playoff_round
            ON games(playoff_round)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_foul_events_player_game
            ON foul_events(fouler_player_id, game_id DESC)
    """)

    conn.commit()
    cur.close()
    return conn


def insert_game(conn, game):
    """Insert a game record. Updates winner_tricode if the row already exists."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO games
            (game_id, away_team_tricode, home_team_tricode, game_date, season, playoff_round, winner_tricode)
        VALUES
            (%(game_id)s, %(away_team_tricode)s, %(home_team_tricode)s,
             %(game_date)s, %(season)s, %(playoff_round)s, %(winner_tricode)s)
        ON CONFLICT (game_id) DO UPDATE SET winner_tricode = EXCLUDED.winner_tricode
    """, game)
    cur.close()


def insert_game_officials(conn, game_id, officials):
    """Insert game_officials records. Skips duplicates."""
    if not officials:
        return
    cur = conn.cursor()
    execute_values(cur, """
        INSERT INTO game_officials (game_id, official_id, assignment)
        VALUES %s
        ON CONFLICT (game_id, official_id) DO NOTHING
    """, [(game_id, o["official_id"], o["assignment"]) for o in officials])
    cur.close()


def insert_referees(conn, referees):
    """Insert referee records. Skips duplicates."""
    if not referees:
        return
    cur = conn.cursor()
    execute_values(cur, """
        INSERT INTO referees (official_id, official_name)
        VALUES %s
        ON CONFLICT (official_id) DO NOTHING
    """, [(r["official_id"], r["official_name"]) for r in referees])
    cur.close()


def insert_players(conn, players):
    """
    Insert player records. Skips duplicates.
    Fouler data (abbreviated name + team) takes priority over
    fouled-player data (last name only, no team), so ON CONFLICT DO NOTHING
    preserves the first (richer) record seen.
    """
    if not players:
        return
    cur = conn.cursor()
    execute_values(cur, """
        INSERT INTO players (player_id, player_name, team_id, team_tricode)
        VALUES %s
        ON CONFLICT (player_id) DO NOTHING
    """, [(p["player_id"], p["player_name"], p["team_id"], p["team_tricode"]) for p in players])
    cur.close()


def insert_foul_events(conn, records):
    """Insert foul_event records. Skips duplicates (same game + action_number)."""
    if not records:
        return
    cur = conn.cursor()
    execute_values(cur, """
        INSERT INTO foul_events (
            game_id, action_number, period, clock,
            foul_type, foul_subtype, foul_detail,
            fouler_player_id, fouler_player_name, fouler_team_id, fouler_team_tricode,
            fouled_player_id, fouled_player_name,
            official_id, official_name,
            foul_personal_total, description
        ) VALUES %s
        ON CONFLICT (game_id, action_number) DO NOTHING
    """, [(
        r["game_id"], r["action_number"], r["period"], r["clock"],
        r["foul_type"], r["foul_subtype"], r["foul_detail"],
        r["fouler_player_id"], r["fouler_player_name"], r["fouler_team_id"], r["fouler_team_tricode"],
        r["fouled_player_id"], r["fouled_player_name"],
        r["official_id"], r["official_name"],
        r["foul_personal_total"], r["description"],
    ) for r in records])
    cur.close()
