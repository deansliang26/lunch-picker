"""
Run once to seed 35 budget-friendly restaurants near StartX (3165 Porter Dr, Palo Alto).
"""
import sqlite3, re, os
from datetime import date

DB_PATH = os.path.join(os.path.dirname(__file__), "lunch.db")

RESTAURANTS = [
    # Fast food / very budget ($)
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
    {"name": "Square Pie Guys",         "cuisine": "Pizza",          "address": "369 California Ave, Palo Alto",            "price": "$$",  "rating": 4.4, "ordering_url": "https://www.yelp.com/biz/square-pie-guys-palo-alto-4"},

    # Have full scraped menus + auto-fill support and are pinned; need a row to appear.
    {"name": "MJ Sushi",                "cuisine": "Japanese",       "address": "2305 El Camino Real, Palo Alto",           "price": "$$",  "rating": 4.1, "ordering_url": "https://www.mjsushipaloalto.com/"},
    {"name": "Starbird",                "cuisine": "Chicken",        "address": "1241 W El Camino Real, Sunnyvale",         "price": "$$",  "rating": 3.8, "ordering_url": "https://order.starbirdchicken.com/venue/?id=3223&order-type=6"},
    {"name": "Coupa Cafe (Research Park)", "cuisine": "Cafe",        "address": "3215 Porter Dr, Palo Alto",                "price": "$$",  "rating": 3.7, "ordering_url": "https://coupacafe.alohaorderonline.com/Engage.aspx?#/engage/ordering/menu/"},
]

def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# Baked Yelp enrichment (photo + coords) so the hosted/ephemeral DB shows
# photos and drive-times instantly without a runtime Yelp call.
# Regenerate by running enrich.py locally then re-exporting.
_ENRICHMENT = {
    "seed-amber-india": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/J8EuksrqpbzGbTN5DeDpcw/o.jpg", "lat": 37.39711803787208, "lng": -122.10773457274875},
    "seed-asian-box": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/c0TbggU10jOvQiCtZKvJIQ/o.jpg", "lat": 37.4387251, "lng": -122.1598525},
    "seed-baja-fresh": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/Q3H3RTMY8INtTnOkqJv-Mw/o.jpg", "lat": 37.41561, "lng": -122.12883},
    "seed-cafe-borrone": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/jj-kcvEYUxHcNnXyEekglg/o.jpg", "lat": 37.453665, "lng": -122.18202},
    "seed-cascal": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/EN8Vc0KckfWjyB5vtqffpQ/o.jpg", "lat": 37.39112501038679, "lng": -122.08105817116392},
    "seed-chaat-bhavan": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/pu6rK3o3d58BkwNRtZvY9A/o.jpg", "lat": 37.37850104833282, "lng": -122.07105866990588},
    "seed-chipotle-mexican-grill": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/456Ae4jR4HB2BrizOZGNnA/o.jpg", "lat": 37.423881, "lng": -122.143060014095},
    "seed-coupa-cafe": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/TvMPNQWPLSJPTBxVAuTOww/o.jpg", "lat": 37.444682, "lng": -122.161533},
    "seed-doppio-zero-pizza": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/VDEbFKbD9pRZIqv9P7NU1Q/o.jpg", "lat": 37.3943853, "lng": -122.0787964},
    "seed-five-guys": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/OZ_1zK9OVJUsR1AMyY3vMQ/o.jpg", "lat": 37.396018966518525, "lng": -122.10150728282072},
    "seed-fuki-sushi": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/XSWqCSbjJHp4Wr2KhjFHwA/o.jpg", "lat": 37.4138844, "lng": -122.125805},
    "seed-ike-s-love-sandwiches": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/nnJPn9qSIa-3xiyaa68JXQ/o.jpg", "lat": 37.419941, "lng": -122.096053},
    "seed-jersey-mike-s-subs": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/xk5qT9dVWeygRHBZObQLtg/o.jpg", "lat": 37.37357, "lng": -122.0541651},
    "seed-la-bodeguita-del-medio": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/a2WwuexMytQzCWVlDF3TRg/o.jpg", "lat": 37.4254329, "lng": -122.1451937073576},
    "seed-la-viga-seafood": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/yS15Wvs6OdF9wIOHReTXgg/o.jpg", "lat": 37.486981969862065, "lng": -122.222848},
    "seed-lee-s-sandwiches": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/itDOGtOKLtbpMIpySqZQdw/o.jpg", "lat": 37.323542551526, "lng": -122.02986670876},
    "seed-mendocino-farms": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/29AnZLokOYFCRxbLQPEyaA/o.jpg", "lat": 37.44366249, "lng": -122.16207180325536},
    "seed-mod-pizza": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/6WFgUwni6Ro4xnQ_2AJkvw/o.jpg", "lat": 37.38246925256315, "lng": -121.8970118205723},
    "seed-oren-s-hummus-shop": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/JJ2p55Nw3lvwqfDlAe6Vjg/o.jpg", "lat": 37.445717, "lng": -122.162173},
    "seed-panda-express": {"image_url": "", "lat": 37.4252908, "lng": -122.1468323},
    "seed-pizza-my-heart": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/rRp4AGHSqwfiQFLFWMrxlA/o.jpg", "lat": 37.44485, "lng": -122.16227},
    "seed-poke-house": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/NykOCjL6s7qiD4aZYKpbNQ/o.jpg", "lat": 37.438605, "lng": -122.160441},
    "seed-rangoon-ruby": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/DfkufSmD1QyodmAum3-3DA/o.jpg", "lat": 37.44514, "lng": -122.16305},
    "seed-roost-roast": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/rSuF4OjrD184J7a6YmNkUA/o.jpg", "lat": 37.43944437943251, "lng": -122.1583573900819},
    "seed-sajj-mediterranean": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/xykBzIv-uLQQ6GXwzhFhRA/o.jpg", "lat": 37.40099309253801, "lng": -122.11226246645442},
    "seed-sweetgreen": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/lRzjLP6o1YCfoaslkQ_QNA/o.jpg", "lat": 37.44473396475442, "lng": -122.16109207054912},
    "seed-zareen-s": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/T7t7eyLiLIntkiH61HhI3Q/o.jpg", "lat": 37.426757, "lng": -122.144093},
    "seed-square-pie-guys": {"image_url": "", "lat": 37.42679, "lng": -122.14418},
    "seed-mj-sushi": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/dPBu4lv73PDA8R3opf4FoA/o.jpg", "lat": 37.425727, "lng": -122.146453},
    "seed-starbird": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/b0pexR0TIQchr0FZF6gMiA/o.jpg", "lat": 37.374678, "lng": -122.057094},
    "seed-coupa-cafe-research-park": {"image_url": "https://s3-media0.fl.yelpcdn.com/bphoto/bEQ6lif6pXFvGqt4x-ukRg/o.jpg", "lat": 37.4092, "lng": -122.14797},
}


def seed():
    """Populate restaurants_cache with the canonical seed list. Idempotent
    (INSERT OR REPLACE), safe to call on startup when the DB is empty."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM restaurants_cache WHERE id NOT LIKE 'custom-%'")
    conn.execute("DELETE FROM daily_suggestions")
    conn.commit()

    today = date.today().isoformat()
    for r in RESTAURANTS:
        sid = f"seed-{slug(r['name'])}"
        e = _ENRICHMENT.get(sid, {})
        conn.execute(
            """INSERT OR REPLACE INTO restaurants_cache
               (id, name, address, cuisine, rating, price, lat, lng, yelp_url, image_url, fetched_on)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sid, r["name"], r["address"], r["cuisine"], r["rating"], r["price"],
             e.get("lat"), e.get("lng"), r.get("ordering_url", ""), e.get("image_url", ""), today),
        )
    conn.commit()
    conn.close()
    return len(RESTAURANTS)


if __name__ == "__main__":
    n = seed()
    print(f"Seeded {n} restaurants.")
