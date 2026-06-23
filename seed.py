"""
Run once to seed 35 budget-friendly restaurants near StartX (3165 Porter Dr, Palo Alto).
"""
import sqlite3, re, os
from datetime import date

DB_PATH = os.path.join(os.path.dirname(__file__), "lunch.db")

RESTAURANTS = [
    # Fast food / very budget ($)
    {"name": "In-N-Out Burger",         "cuisine": "Burgers",        "address": "3895 El Camino Real, Palo Alto",           "price": "$",   "rating": 4.4},
    {"name": "Chipotle Mexican Grill",  "cuisine": "Mexican",        "address": "180 El Camino Real, Mountain View",        "price": "$",   "rating": 3.7},
    {"name": "Jersey Mike's Subs",      "cuisine": "Sandwiches",     "address": "3600 El Camino Real, Palo Alto",           "price": "$",   "rating": 4.0},
    {"name": "Panda Express",           "cuisine": "Chinese",        "address": "40 Showers Dr, Mountain View",             "price": "$",   "rating": 3.5},
    {"name": "Mod Pizza",               "cuisine": "Pizza",          "address": "2520 W El Camino Real, Mountain View",     "price": "$",   "rating": 4.0},
    {"name": "Baja Fresh",              "cuisine": "Mexican",        "address": "3886 El Camino Real, Palo Alto",           "price": "$",   "rating": 3.6},
    {"name": "Lee's Sandwiches",        "cuisine": "Vietnamese Subs","address": "1136 W El Camino Real, Mountain View",     "price": "$",   "rating": 4.0},
    {"name": "Chaat Bhavan",            "cuisine": "Indian",         "address": "1621 W El Camino Real, Mountain View",     "price": "$",   "rating": 4.2},
    {"name": "Pizza My Heart",          "cuisine": "Pizza",          "address": "167 S California Ave, Palo Alto",          "price": "$",   "rating": 4.1},
    {"name": "Vung Tau Restaurant",     "cuisine": "Vietnamese",     "address": "1956 W El Camino Real, Mountain View",     "price": "$",   "rating": 4.1},

    # Fast casual ($$)
    {"name": "Mendocino Farms",         "cuisine": "Sandwiches",     "address": "540 Ramona St, Palo Alto",                 "price": "$$",  "rating": 4.3},
    {"name": "Sweetgreen",              "cuisine": "Salads",         "address": "340 University Ave, Palo Alto",            "price": "$$",  "rating": 4.1},
    {"name": "Ike's Love & Sandwiches", "cuisine": "Sandwiches",     "address": "325 Sharon Park Dr, Menlo Park",           "price": "$$",  "rating": 4.3},
    {"name": "SAJJ Mediterranean",      "cuisine": "Mediterranean",  "address": "444 Castro St, Mountain View",             "price": "$$",  "rating": 4.2},
    {"name": "Five Guys",               "cuisine": "Burgers",        "address": "201 Castro St, Mountain View",             "price": "$$",  "rating": 4.1},
    {"name": "Pokéworks",               "cuisine": "Poke",           "address": "2532 W El Camino Real, Mountain View",     "price": "$$",  "rating": 4.1},
    {"name": "Patxi's Pizza",           "cuisine": "Pizza",          "address": "441 Castro St, Mountain View",             "price": "$$",  "rating": 4.1},
    {"name": "Rangoon Ruby",            "cuisine": "Burmese",        "address": "209 Castro St, Mountain View",             "price": "$$",  "rating": 4.2},
    {"name": "Lemon Grass Thai",        "cuisine": "Thai",           "address": "145 El Camino Real, Mountain View",        "price": "$$",  "rating": 4.2},

    # Local casual ($-$$)
    {"name": "Coupa Cafe",              "cuisine": "Cafe",           "address": "538 Ramona St, Palo Alto",                 "price": "$",   "rating": 4.2},
    {"name": "Oren's Hummus Shop",      "cuisine": "Mediterranean",  "address": "261 University Ave, Palo Alto",            "price": "$$",  "rating": 4.2},
    {"name": "La Bodeguita del Medio",  "cuisine": "Cuban",          "address": "463 S California Ave, Palo Alto",          "price": "$$",  "rating": 4.2},
    {"name": "Cafe Brioche",            "cuisine": "French Cafe",    "address": "445 S California Ave, Palo Alto",          "price": "$$",  "rating": 4.0},
    {"name": "Cafe Borrone",            "cuisine": "Cafe",           "address": "1010 El Camino Real, Menlo Park",          "price": "$$",  "rating": 4.1},
    {"name": "Ephesus Restaurant",      "cuisine": "Turkish",        "address": "1496 El Camino Real, Menlo Park",          "price": "$$",  "rating": 4.1},
    {"name": "La Viga Seafood",         "cuisine": "Mexican",        "address": "1772 El Camino Real, Menlo Park",          "price": "$$",  "rating": 4.2},
    {"name": "Fuki Sushi",              "cuisine": "Japanese",       "address": "4119 El Camino Real, Palo Alto",           "price": "$$",  "rating": 4.0},
    {"name": "Mayfield Bakery & Cafe",  "cuisine": "American",       "address": "855 El Camino Real, Palo Alto",            "price": "$$",  "rating": 4.1},
    {"name": "Xanh Restaurant",         "cuisine": "Vietnamese",     "address": "110 Castro St, Mountain View",             "price": "$$",  "rating": 4.1},
    {"name": "Cascal",                  "cuisine": "Latin",          "address": "400 Castro St, Mountain View",             "price": "$$",  "rating": 4.1},
    {"name": "Doppio Zero Pizza",       "cuisine": "Italian",        "address": "160 Castro St, Mountain View",             "price": "$$",  "rating": 4.3},
    {"name": "Tied House",              "cuisine": "American",       "address": "954 Villa St, Mountain View",              "price": "$$",  "rating": 4.0},
    {"name": "Amber India",             "cuisine": "Indian",         "address": "2290 El Camino Real, Mountain View",       "price": "$$",  "rating": 4.2},
    {"name": "St. Michael's Alley",     "cuisine": "American",       "address": "140 Homer Ave, Palo Alto",                 "price": "$$",  "rating": 4.1},

    # Town & Country Village additions
    {"name": "Roost & Roast",           "cuisine": "Thai",           "address": "855 El Camino Real #157, Palo Alto",       "price": "$$",  "rating": 4.1, "ordering_url": "https://order.toasttab.com/online/roost-and-roast"},
    {"name": "Asian Box",               "cuisine": "Vietnamese",     "address": "855 El Camino Real, Palo Alto",            "price": "$$",  "rating": 4.2, "ordering_url": "https://order.spoton.com/asian-box-962/palo-alto-ca/65b13a4621728ea769f7f0b2/welcome"},
    {"name": "Poke House",              "cuisine": "Poke",           "address": "855 El Camino Real #9, Palo Alto",         "price": "$$",  "rating": 4.2, "ordering_url": "https://www.doordash.com/store/poke-house-palo-alto-458519/"},
    {"name": "Zareen's",                "cuisine": "Pakistani",      "address": "365 California Ave, Palo Alto",            "price": "$$",  "rating": 4.4, "ordering_url": "https://orderingatzareens.square.site/"},
]

def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def seed():
    """Populate restaurants_cache with the canonical seed list. Idempotent
    (INSERT OR REPLACE), safe to call on startup when the DB is empty."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM restaurants_cache WHERE id NOT LIKE 'custom-%'")
    conn.execute("DELETE FROM daily_suggestions")
    conn.commit()

    today = date.today().isoformat()
    for r in RESTAURANTS:
        conn.execute(
            """INSERT OR REPLACE INTO restaurants_cache
               (id, name, address, cuisine, rating, price, lat, lng, yelp_url, image_url, fetched_on)
               VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, '', ?)""",
            (f"seed-{slug(r['name'])}", r["name"], r["address"], r["cuisine"], r["rating"], r["price"], r.get("ordering_url", ""), today),
        )
    conn.commit()
    conn.close()
    return len(RESTAURANTS)


if __name__ == "__main__":
    n = seed()
    print(f"Seeded {n} restaurants.")
