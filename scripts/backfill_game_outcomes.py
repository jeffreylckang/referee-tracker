"""
Backfill winner_tricode and game_officials for all existing games.

Fetches boxscore from NBA CDN for every game_id in the DB that is missing
winner_tricode or has no rows in game_officials, then updates both.

Run once after the DB migration:
    DATABASE_URL=... python3 scripts/backfill_game_outcomes.py
"""

import os
import sys
import requests
import psycopg2
from psycopg2.extras import execute_values
from concurrent.futures import ThreadPoolExecutor, as_completed

CDN_BASE     = "https://cdn.nba.com/static/json/liveData"
FETCH_WORKERS = 20


def get_conn():
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url)


def fetch_boxscore(game_id):
    try:
        r = requests.get(f"{CDN_BASE}/boxscore/boxscore_{game_id}.json", timeout=15)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def process_boxscore(game_id, boxscore):
    game = boxscore["game"]

    home       = game["homeTeam"]
    away       = game["awayTeam"]
    home_score = home.get("score")
    away_score = away.get("score")
    if home_score is not None and away_score is not None and home_score != away_score:
        winner_tricode = home["teamTricode"] if home_score > away_score else away["teamTricode"]
    else:
        winner_tricode = None

    officials = game.get("officials", [])
    game_officials = [
        (game_id, o["personId"], o.get("assignment", ""))
        for o in officials
    ]

    return winner_tricode, game_officials


def main():
    conn = get_conn()
    cur  = conn.cursor()

    # Get all game_ids that need backfill (missing winner or no officials recorded)
    cur.execute("""
        SELECT g.game_id
        FROM games g
        LEFT JOIN game_officials go ON go.game_id = g.game_id
        WHERE g.winner_tricode IS NULL OR go.game_id IS NULL
        GROUP BY g.game_id
    """)
    game_ids = [r[0] for r in cur.fetchall()]
    cur.close()

    print(f"Games to backfill: {len(game_ids)}")
    if not game_ids:
        print("Nothing to backfill.")
        conn.close()
        return

    results   = []
    not_found = 0

    def fetch_one(gid):
        box = fetch_boxscore(gid)
        return gid, box

    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
        futures = {executor.submit(fetch_one, gid): gid for gid in game_ids}
        for i, future in enumerate(as_completed(futures), 1):
            gid, box = future.result()
            if box:
                results.append((gid, box))
            else:
                not_found += 1
            if i % 100 == 0:
                print(f"  {i}/{len(game_ids)} fetched, {len(results)} found...")

    print(f"\nFetched: {len(results)}  Not found: {not_found}")

    cur = conn.cursor()
    winners_updated  = 0
    officials_inserted = 0

    for game_id, boxscore in results:
        winner_tricode, game_officials = process_boxscore(game_id, boxscore)

        cur.execute(
            "UPDATE games SET winner_tricode = %s WHERE game_id = %s",
            (winner_tricode, game_id)
        )
        if cur.rowcount:
            winners_updated += 1

        if game_officials:
            execute_values(cur, """
                INSERT INTO game_officials (game_id, official_id, assignment)
                VALUES %s
                ON CONFLICT (game_id, official_id) DO NOTHING
            """, game_officials)
            officials_inserted += len(game_officials)

    conn.commit()
    cur.close()
    conn.close()

    print(f"winners_tricode updated : {winners_updated}")
    print(f"game_officials inserted : {officials_inserted}")
    print("Done.")


if __name__ == "__main__":
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set.")
        sys.exit(1)
    main()
