import os
import requests
from datetime import date
from dotenv import load_dotenv
import db

load_dotenv()


def _secret(key, default=""):
    """Resolve config from env (.env / local) first, then Streamlit Cloud
    secrets (st.secrets), since hosted secrets are not exposed as env vars
    and each page runs as its own script."""
    v = os.getenv(key)
    if v:
        return v
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default


YELP_API_KEY = _secret("YELP_API_KEY", "")
YELP_SEARCH_URL = "https://api.yelp.com/v3/businesses/search"

OFFICE_LAT = 37.4076
OFFICE_LNG = -122.1459
RADIUS_M = 8000
SUGGESTIONS_PER_DAY = 35

# These restaurants always appear in daily suggestions regardless of the random rotation.
# When a cuisine filter is active, only pinned restaurants matching the filter are kept.
PINNED_IDS = {
    "seed-chipotle-mexican-grill",
    "seed-panda-express",
    "seed-pizza-my-heart",
    "seed-mendocino-farms",
    "seed-ike-s-love-sandwiches",
    "seed-starbird",
    "seed-mj-sushi",
    "seed-oren-s-hummus-shop",
    "seed-sweetgreen",
    "seed-roost-roast",
    "seed-asian-box",
    "seed-poke-house",
    "seed-zareen-s",
    "seed-coupa-cafe-research-park",
    "seed-square-pie-guys",
    "seed-the-melt",
    "seed-shake-shack",
    "seed-mediterranean-wraps",
    "seed-state-of-mind-slice-house",
    "seed-lotus-thai-bistro",
}

CUISINES = {
    "All": None,
    "Japanese": "japanese",
    "Mexican": "mexican",
    "Italian": "italian",
    "Chinese": "chinese",
    "Thai": "thai",
    "Indian": "indpak",
    "Korean": "korean",
    "Vietnamese": "vietnamese",
    "Pizza": "pizza",
    "Burgers": "burgers",
    "Mediterranean": "mediterranean",
    "Sandwiches": "sandwiches",
}


def _fetch_from_yelp(category: str | None = None) -> list[dict]:
    if not YELP_API_KEY:
        return []

    params = {
        "latitude": OFFICE_LAT,
        "longitude": OFFICE_LNG,
        "radius": RADIUS_M,
        "sort_by": "rating",
        "limit": 50,
        "open_now": False,
    }
    if category:
        params["categories"] = category

    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
    resp = requests.get(YELP_SEARCH_URL, params=params, headers=headers, timeout=10)
    resp.raise_for_status()

    businesses = resp.json().get("businesses", [])
    today_str = date.today().isoformat()
    results = []
    for b in businesses:
        cats = b.get("categories", [])
        cuisine_label = cats[0]["title"] if cats else "Restaurant"
        loc = b.get("location", {})
        address_parts = [loc.get("address1", ""), loc.get("city", ""), loc.get("state", "")]
        address = ", ".join(p for p in address_parts if p)
        coord = b.get("coordinates", {})
        price = b.get("price", "")
        results.append({
            "id": b["id"],
            "name": b["name"],
            "address": address,
            "cuisine": cuisine_label,
            "rating": b.get("rating"),
            "price": price,
            "lat": coord.get("latitude"),
            "lng": coord.get("longitude"),
            "yelp_url": b.get("url", ""),
            "image_url": b.get("image_url", ""),
            "fetched_on": today_str,
        })
    return results


def get_suggestions(cuisine_filter: str | None = None) -> list[dict]:
    """
    Return today's 5 restaurant suggestions.
    - Fetches from Yelp exactly once (when cache is empty); never auto-refreshes
    - Applies cuisine filter after cache read so we don't re-fetch per cuisine
    - Daily picks are deterministic (same for all users on the same day)
    """
    cached = db.get_cached_restaurants(max_age_days=36500)  # fetch once, keep forever

    if not cached:
        fetched = _fetch_from_yelp()
        if fetched:
            db.upsert_restaurants(fetched)
            cached = fetched

    # Apply cuisine filter in Python (avoids extra API calls per cuisine change)
    if cuisine_filter:
        filtered = [r for r in cached if cuisine_filter.lower() in r.get("cuisine", "").lower()]
        # Fall back to all if filter returns nothing
        if not filtered:
            filtered = cached
    else:
        filtered = cached

    # Only show the fixed list of pinned restaurants — no random rotation
    picks = [r for r in filtered if r["id"] in PINNED_IDS]

    db.set_daily_suggestions([p["id"] for p in picks])
    return picks


def refresh_cache() -> list[dict]:
    """Force a fresh fetch from Yelp, ignoring cache age."""
    fetched = _fetch_from_yelp()
    if fetched:
        db.upsert_restaurants(fetched)
    return fetched
