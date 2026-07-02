"""Seed an ISOLATED demo database (lunch.demo.db) with a ready-to-show scenario,
so you can demo restaurant selection + autofill without touching today's real
pick (Zareen's stays untouched in the normal lunch.db).

Scenario it creates for *today*:
  • the usual restaurant slate
  • a live-looking vote board — MJ Sushi leading 2–1, NO winner yet
  • pre-placed MJ Sushi orders (so autofill has something to fill)

Demo flow: open the Vote page → cast one more vote for MJ Sushi as a 3rd person
(Parth/Aaron) → instant majority → MJ Sushi wins → Order Station → "Auto-fill cart".

MJ Sushi is autofill-supported (and the one that fully verifies in-cart), so the
Auto-fill button appears and the browser fills the real MJ Sushi cart.

Run:  ./.venv/bin/python demo_setup.py     (run_demo.sh does this for you)
"""
import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO_DB = os.environ.get("LUNCH_DB_PATH") or os.path.join(HERE, "lunch.demo.db")
os.environ["LUNCH_DB_PATH"] = DEMO_DB  # must be set before importing db

# Fresh start every run so the demo is reproducible.
for ext in ("", "-wal", "-shm"):
    try:
        os.remove(DEMO_DB + ext)
    except FileNotFoundError:
        pass

import db        # noqa: E402  (import after LUNCH_DB_PATH is set)
import yelp      # noqa: E402
from roster import TEAM  # noqa: E402

PRE_VOTES = [("Dean", "seed-mj-sushi"), ("Evan", "seed-mj-sushi"), ("Cooper", "seed-sweetgreen")]
PRE_ORDERS = {
    "Dean":   [{"item": "Edamame",             "qty": 1, "notes": "",               "price": 4.99}],
    "Evan":   [{"item": "Dragon Roll",         "qty": 1, "notes": "no unagi sauce", "price": 15.49}],
    "Cooper": [{"item": "Salmon Avocado Roll", "qty": 1, "notes": "",               "price": 7.49}],
}


def main():
    db.init_db()            # create schema + seed restaurants into the demo DB
    yelp.get_suggestions()  # write today's slate (pinned restaurants; uses seeded cache)

    for voter, pid in PRE_VOTES:
        db.cast_vote(voter, pid)
    for person, items in PRE_ORDERS.items():
        db.upsert_order(person, json.dumps(items))

    print(f"✅ Demo DB ready: {db.DB_PATH}")
    print("   Board: MJ Sushi 2 · Sweetgreen 1  (no winner yet — show the decision live)")
    print("   Orders pre-placed: Edamame · Dragon Roll (no unagi sauce) · Salmon Avocado Roll")
    print("   → In the demo: vote MJ Sushi as a 3rd person (Parth/Aaron) for an instant majority,")
    print("     then go to Order Station → Auto-fill cart.")


if __name__ == "__main__":
    main()
