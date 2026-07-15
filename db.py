import sqlite3
import os
import random
from datetime import datetime, date, timedelta

# Override with LUNCH_DB_PATH to run an isolated instance (e.g. the demo sandbox)
# without touching the real lunch.db. Defaults to the normal DB when unset.
DB_PATH = os.environ.get("LUNCH_DB_PATH") or os.path.join(os.path.dirname(__file__), "lunch.db")


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
    _seed_ledger()


def _seed_if_empty():
    """Keep the canonical restaurant list in sync on an ephemeral cloud
    filesystem. (Re)seed whenever the SET of seed ids in the DB differs from the
    roster — covers a fresh DB, a restaurant added, one removed, OR a net-zero
    one-out/one-in swap (seed() rewrites the full list). A bare COUNT check
    misses the swap case (e.g. drop Five Guys + add Lotus keeps count at 45),
    which leaves the new restaurant permanently unseeded on a persisted DB."""
    try:
        import seed
    except Exception:
        return
    expected = {f"seed-{seed.slug(r['name'])}" for r in seed.RESTAURANTS}
    with _conn() as conn:
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT id FROM restaurants_cache WHERE id LIKE 'seed-%'"
            ).fetchall()
        }
    if existing != expected:
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


_ledger_seeded = False


def _seed_ledger():
    """Seed the baked historical orders + daily winners so the History page's
    running-tab ledger reflects the full past — not just orders placed since the
    last container reset.

    Needed because the deployed SQLite DB is ephemeral (gitignored, not
    committed): restaurants were reseeded on startup but the order/history
    ledger was not, so every redeploy wiped all past overages and the running
    tab collapsed to a single day. Uses INSERT OR IGNORE keyed on the tables'
    UNIQUE constraints (orders: date+person, history: date) so it fills only
    missing rows and never clobbers anything entered live.

    init_db() runs on every Streamlit rerun, so guard the (idempotent) seed
    behind a process flag: it runs once per process — i.e. once per fresh /
    redeployed container, exactly when the ephemeral DB needs backfilling —
    instead of re-sweeping both tables on every page interaction."""
    global _ledger_seeded
    if _ledger_seeded:
        return
    try:
        import seed_history
    except Exception:
        return
    with _conn() as conn:
        conn.executemany(
            """INSERT OR IGNORE INTO orders (date, person, order_text, updated_at)
               VALUES (?, ?, ?, ?)""",
            seed_history.ORDERS,
        )
        conn.executemany(
            """INSERT OR IGNORE INTO history
               (date, winner_place_id, vote_count, total_voters, decided_at)
               VALUES (?, ?, ?, ?, ?)""",
            seed_history.HISTORY,
        )
    _ledger_seeded = True


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


def reset_today():
    """Wipe today's vote so the team can start over: clears every vote AND the
    recorded winner for today. Leaves placed orders and the daily suggestions
    untouched. Idempotent — safe to call when nothing has been decided yet."""
    d = today()
    with _conn() as conn:
        conn.execute("DELETE FROM daily_votes WHERE date = ?", (d,))
        conn.execute("DELETE FROM history WHERE date = ?", (d,))


def tally_votes() -> dict[str, int]:
    votes = get_todays_votes()
    tally: dict[str, int] = {}
    for v in votes:
        tally[v["place_id"]] = tally.get(v["place_id"], 0) + 1
    return tally


def pick_weighted_winner() -> str | None:
    """Pick a winner from today's votes, weighted by vote count — more votes
    means better odds, but an underdog can still win (that's the fun of it).
    Returns the chosen place_id, or None if nobody has voted yet."""
    tally = tally_votes()
    if not tally:
        return None
    pids = list(tally.keys())
    weights = [tally[p] for p in pids]
    return random.choices(pids, weights=weights, k=1)[0]


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


def decide_winner_if_majority(majority: int, total_voters: int) -> str | None:
    """Deterministically lock in the winner the moment any restaurant reaches the
    majority threshold. Idempotent and safe to call on every page load/refresh —
    so a majority is ALWAYS recorded regardless of which session cast the
    deciding vote (previously only the caster's session recorded it, letting a
    majority sit unrecorded and be overridden by the weighted 'decide' pick).
    Returns the winning place_id if it (already) has a majority, else None."""
    if get_todays_winner():
        return None
    tally = tally_votes()
    if not tally:
        return None
    pid, cnt = max(tally.items(), key=lambda kv: kv[1])
    if cnt >= majority:
        record_winner(pid, cnt, total_voters)
        return pid
    return None


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


# Company covers this much per person per day; anything above it accumulates as
# a personal tab. Mirrors BUDGET in the Orders / Order Station pages.
DAILY_BUDGET = 20.00


def get_ledger(budget: float = DAILY_BUDGET) -> dict:
    """Running tab of what each person owes, accumulated across every day.

    For each day's order we take only the amount OVER the per-person daily
    budget (the company covers the first `budget`). Under-budget days contribute
    $0 — never a credit — so a person's balance only ever grows until it's
    settled. Derived live from the orders table, so it can't drift out of sync.

    Returns {person: {"owed": float, "days": [{date, total, overage}, ...]}},
    listing only the days that actually went over budget.
    """
    import json
    with _conn() as conn:
        rows = conn.execute(
            "SELECT date, person, order_text FROM orders ORDER BY date"
        ).fetchall()
    people: dict = {}
    for r in rows:
        try:
            items = json.loads(r["order_text"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(items, list):
            continue
        total = sum((it.get("price") or 0.0) * (it.get("qty") or 1)
                    for it in items if isinstance(it, dict))
        overage = round(max(0.0, total - budget), 2)
        p = people.setdefault(r["person"], {"owed": 0.0, "days": []})
        if overage > 0:
            p["owed"] = round(p["owed"] + overage, 2)
            p["days"].append(
                {"date": r["date"], "total": round(total, 2), "overage": overage}
            )
    return people
