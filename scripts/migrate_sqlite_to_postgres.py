"""
One-time migration: copy all data from local SQLite to PostgreSQL.

Usage:
    DATABASE_URL=postgresql://... python scripts/migrate_sqlite_to_postgres.py

Run this once after setting up Render PostgreSQL.
"""

import os
import sqlite3
import sys

import psycopg2
from psycopg2.extras import execute_values

SQLITE_PATH = os.path.join(os.path.dirname(__file__), "../data/referee_tracker.db")

# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------

def get_pg():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("ERROR: DATABASE_URL is not set.")
        sys.exit(1)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url)


def get_sqlite():
    if not os.path.exists(SQLITE_PATH):
        print(f"ERROR: SQLite file not found at {SQLITE_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def create_schema(pg):
    cur = pg.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS games (
            game_id           TEXT PRIMARY KEY,
            away_team_tricode TEXT NOT NULL,
            home_team_tricode TEXT NOT NULL,
            game_date         TEXT,
            season            TEXT,
            playoff_round     TEXT
        )
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_foul_events_official_id ON foul_events(official_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_foul_events_fouler_player_id ON foul_events(fouler_player_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_foul_events_fouled_player_id ON foul_events(fouled_player_id)")
    pg.commit()
    cur.close()
    print("  Schema ready.")

# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------

BATCH = 5000

def migrate_table(sqlite, pg, table, columns, transform=None):
    rows = sqlite.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
    if not rows:
        print(f"  {table}: 0 rows — skipping.")
        return

    data = [transform(r) for r in rows] if transform else [tuple(r) for r in rows]
    placeholders = ", ".join(["%s"] * len(columns))

    cur = pg.cursor()
    for i in range(0, len(data), BATCH):
        batch = data[i:i + BATCH]
        execute_values(cur, f"""
            INSERT INTO {table} ({', '.join(columns)})
            VALUES %s
            ON CONFLICT DO NOTHING
        """, batch)
        pg.commit()
        print(f"  {table}: {min(i + BATCH, len(data))}/{len(data)} rows inserted", end="\r")

    cur.close()
    print(f"  {table}: {len(data)} rows migrated.          ")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    print("\n=== SQLite → PostgreSQL Migration ===\n")

    sqlite = get_sqlite()
    pg     = get_pg()

    print("Connections established.\n")
    print("Creating schema...")
    create_schema(pg)
    print()

    print("Migrating games...")
    migrate_table(sqlite, pg, "games",
        ["game_id", "away_team_tricode", "home_team_tricode", "game_date", "season", "playoff_round"])

    print("Migrating referees...")
    migrate_table(sqlite, pg, "referees",
        ["official_id", "official_name"])

    print("Migrating players...")
    migrate_table(sqlite, pg, "players",
        ["player_id", "player_name", "team_id", "team_tricode"])

    print("Migrating foul_events (this may take a moment)...")
    migrate_table(sqlite, pg, "foul_events", [
        "game_id", "action_number", "period", "clock",
        "foul_type", "foul_subtype", "foul_detail",
        "fouler_player_id", "fouler_player_name", "fouler_team_id", "fouler_team_tricode",
        "fouled_player_id", "fouled_player_name",
        "official_id", "official_name",
        "foul_personal_total", "description",
    ])

    # Verify
    cur = pg.cursor()
    print("\n=== Verification ===")
    for table in ["games", "referees", "players", "foul_events"]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"  {table}: {cur.fetchone()[0]:,} rows")
    cur.close()

    sqlite.close()
    pg.close()
    print("\nMigration complete.\n")


if __name__ == "__main__":
    run()
