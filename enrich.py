"""
Looks up each restaurant in the DB on Yelp by name, updates lat/lng and image_url.
Safe to re-run — only updates rows that are missing coordinates or photos.
"""
import sqlite3, os, math, time
import requests
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "lunch.db")
YELP_API_KEY = os.getenv("YELP_API_KEY", "")
OFFICE_LAT, OFFICE_LNG = 37.4076, -122.1459


def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def yelp_lookup(name):
    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
    params = {
        "term": name,
        "latitude": OFFICE_LAT,
        "longitude": OFFICE_LNG,
        "limit": 1,
        "radius": 12000,
    }
    resp = requests.get(
        "https://api.yelp.com/v3/businesses/search",
        headers=headers,
        params=params,
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    businesses = resp.json().get("businesses", [])
    if not businesses:
        return None
    b = businesses[0]
    # Only accept if the name is a rough match
    if name.lower().split()[0] not in b["name"].lower():
        return None
    coord = b.get("coordinates", {})
    return {
        "lat": coord.get("latitude"),
        "lng": coord.get("longitude"),
        "image_url": b.get("image_url", ""),
        "yelp_url": b.get("url", ""),
        "rating": b.get("rating"),
        "price": b.get("price", ""),
    }


conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT id, name FROM restaurants_cache WHERE lat IS NULL OR image_url IS NULL OR image_url = ''"
).fetchall()

print(f"Enriching {len(rows)} restaurants...")
found, missing = 0, []

for row in rows:
    result = yelp_lookup(row["name"])
    if result:
        conn.execute(
            """UPDATE restaurants_cache
               SET lat=?, lng=?, image_url=?, yelp_url=?, rating=COALESCE(rating,?), price=COALESCE(NULLIF(price,''),?)
               WHERE id=?""",
            (result["lat"], result["lng"], result["image_url"], result["yelp_url"],
             result["rating"], result["price"], row["id"]),
        )
        miles = haversine_miles(OFFICE_LAT, OFFICE_LNG, result["lat"], result["lng"])
        print(f"  ✓ {row['name']} — {miles:.1f} mi")
        found += 1
    else:
        print(f"  ✗ {row['name']} — not found on Yelp")
        missing.append(row["name"])
    time.sleep(0.3)  # stay well within Yelp rate limits

conn.commit()
conn.close()

print(f"\nDone. {found} enriched, {len(missing)} not found on Yelp:")
for m in missing:
    print(f"  - {m}")
