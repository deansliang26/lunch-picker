import sqlite3
import os
from datetime import datetime, date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "lunch.db")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with _conn() as conn:
        conn.executescript("""

            CREATE TABLE IF NOT EXISTS restaurants_cache (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                address     TEXT,
                cuisine     TEXT,
                rating      REAL,
                price       TEXT,
                lat         REAL,
                lng         REAL,
                yelp_url    TEXT,
                image_url   TEXT,
                fetched_on  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_suggestions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                place_id    TEXT NOT NULL,
                UNIQUE(date, place_id)
            );

            CREATE TABLE IF NOT EXISTS daily_votes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                voter       TEXT NOT NULL,
                place_id    TEXT NOT NULL,
                voted_at    TEXT NOT NULL,
                UNIQUE(date, voter)
            );

            CREATE TABLE IF NOT EXISTS history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT NOT NULL UNIQUE,
                winner_place_id TEXT NOT NULL,
                vote_count      INTEGER NOT NULL,
                total_voters    INTEGER NOT NULL,
                decided_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                person      TEXT NOT NULL,
                order_text  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                UNIQUE(date, person)
            );
        """)
    _migrate()
    _seed_if_empty()


def _seed_if_empty():
    """Keep the canonical restaurant list populated on an ephemeral cloud
    filesystem. (Re)seed whenever any seed restaurant is missing — covers both a
    fresh DB and a DB seeded by an older build before a restaurant was added —
    then make the baked photos/coords authoritative on the seed rows."""
    try:
        import seed
    except Exception:
        return
    with _conn() as conn:
        seeded = conn.execute(
            "SELECT COUNT(*) FROM restaurants_cache WHERE id LIKE 'seed-%'"
        ).fetchone()[0]
    # seed() is idempotent (INSERT OR REPLACE); only run it when rows are missing.
    if seeded < len(seed.RESTAURANTS):
        seed.seed()
    # Make baked enrichment authoritative for seed photos/coords. image_url is set
    # outright (so a dead/removed URL recorded by an earlier build is cleared);
    # lat/lng only fill when missing so real coords aren't clobbered.
    with _conn() as conn:
        for sid, e in seed._ENRICHMENT.items():
            conn.execute(
                """UPDATE restaurants_cache
                   SET image_url = ?,
                       lat = COALESCE(lat, ?),
                       lng = COALESCE(lng, ?)
                   WHERE id = ?""",
                (e.get("image_url", ""), e.get("lat"), e.get("lng"), sid),
            )


def _migrate():
    with _conn() as conn:
        try:
            conn.execute("ALTER TABLE restaurants_cache ADD COLUMN image_url TEXT")
        except Exception:
            pass


def add_custom_restaurant(name: str, cuisine: str, address: str = "", price: str = "", yelp_url: str = ""):
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    place_id = f"custom-{slug}"
    with _conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO restaurants_cache
               (id, name, address, cuisine, rating, price, lat, lng, yelp_url, fetched_on)
               VALUES (?, ?, ?, ?, NULL, ?, NULL, NULL, ?, ?)""",
            (place_id, name, address, cuisine, price, yelp_url, date.today().isoformat()),
        )
    return place_id


def today() -> str:
    return date.today().isoformat()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- restaurants_cache ---

def upsert_restaurants(restaurants: list[dict]):
    with _conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO restaurants_cache
               (id, name, address, cuisine, rating, price, lat, lng, yelp_url, image_url, fetched_on)
               VALUES (:id, :name, :address, :cuisine, :rating, :price, :lat, :lng, :yelp_url, :image_url, :fetched_on)""",
            restaurants,
        )


def get_cached_restaurants(max_age_days: int = 7) -> list[dict]:
    cutoff = (date.today() - timedelta(days=max_age_days)).isoformat()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM restaurants_cache WHERE fetched_on >= ?", (cutoff,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_restaurant(place_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM restaurants_cache WHERE id = ?", (place_id,)
        ).fetchone()
    return dict(row) if row else None


# --- daily_suggestions ---

def set_daily_suggestions(place_ids: list[str]):
    d = today()
    with _conn() as conn:
        conn.execute("DELETE FROM daily_suggestions WHERE date = ?", (d,))
        conn.executemany(
            "INSERT OR IGNORE INTO daily_suggestions (date, place_id) VALUES (?, ?)",
            [(d, pid) for pid in place_ids],
        )


def get_daily_suggestions() -> list[dict]:
    d = today()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT rc.* FROM restaurants_cache rc
               JOIN daily_suggestions ds ON rc.id = ds.place_id
               WHERE ds.date = ?""",
            (d,),
        ).fetchall()
    return [dict(r) for r in rows]


# --- daily_votes ---

def cast_vote(voter: str, place_id: str):
    d = today()
    with _conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO daily_votes (date, voter, place_id, voted_at)
               VALUES (?, ?, ?, ?)""",
            (d, voter, place_id, now()),
        )


def get_todays_votes() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_votes WHERE date = ?", (today(),)
        ).fetchall()
    return [dict(r) for r in rows]


def withdraw_vote(voter: str):
    with _conn() as conn:
        conn.execute(
            "DELETE FROM daily_votes WHERE date = ? AND voter = ?",
            (today(), voter),
        )


def tally_votes() -> dict[str, int]:
    votes = get_todays_votes()
    tally: dict[str, int] = {}
    for v in votes:
        tally[v["place_id"]] = tally.get(v["place_id"], 0) + 1
    return tally


# --- history ---

def get_todays_winner() -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM history WHERE date = ?", (today(),)
        ).fetchone()
    return dict(row) if row else None


def record_winner(place_id: str, vote_count: int, total_voters: int):
    with _conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO history
               (date, winner_place_id, vote_count, total_voters, decided_at)
               VALUES (?, ?, ?, ?, ?)""",
            (today(), place_id, vote_count, total_voters, now()),
        )


def get_history(limit: int = 30) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT h.*, rc.name, rc.cuisine, rc.rating, rc.price, rc.yelp_url
               FROM history h
               JOIN restaurants_cache rc ON h.winner_place_id = rc.id
               ORDER BY h.date DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_history_orders(hist_date: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE date = ? ORDER BY updated_at",
            (hist_date,),
        ).fetchall()
    return [dict(r) for r in rows]


# --- orders ---

def upsert_order(person: str, order_text: str):
    with _conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO orders (date, person, order_text, updated_at)
               VALUES (?, ?, ?, ?)""",
            (today(), person, order_text, now()),
        )


def clear_order(person: str):
    with _conn() as conn:
        conn.execute(
            "DELETE FROM orders WHERE date = ? AND person = ?",
            (today(), person),
        )


def get_todays_orders() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE date = ? ORDER BY updated_at",
            (today(),),
        ).fetchall()
    return [dict(r) for r in rows]


def orders_count_for_date(hist_date: str) -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM orders WHERE date = ?", (hist_date,)
        ).fetchone()
    return row["cnt"] if row else 0
