# menus.py — Real menu data scraped from restaurant websites (June 2026).
import json as _json
import os as _os
import math as _math
import datetime as _dt

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_DATA_PATH = _os.path.join(_HERE, "menus_data.json")

# A dated price verification older than this reads as "may be stale" and is
# worth re-checking against the live menu.
PRICE_STALE_DAYS = 45


def _load() -> dict:
    with open(_DATA_PATH) as _f:
        return {m["id"]: m for m in _json.load(_f)}


# Keyed by seed-id; each entry has: menu_url, success, categories[]
MENUS: dict = _load()

_mtime: float = _os.path.getmtime(_DATA_PATH)


def get_menu(restaurant_id: str) -> dict | None:
    """Return menu dict for a restaurant, reloading if menus_data.json changed."""
    global MENUS, _mtime
    current = _os.path.getmtime(_DATA_PATH)
    if current != _mtime:
        MENUS = _load()
        _mtime = current
    return MENUS.get(restaurant_id)


def verification_status(menu_data: dict | None) -> dict:
    """Freshness of a menu's price verification, for badges/warnings.

    Returns {state, date, by, age_days} where state is one of:
      - 'unverified': the prices_verified flag is off — trust nothing.
      - 'unknown':    verified, but with no date stamp (the legacy bare flag) —
                      previously checked, freshness unknown; worth re-verifying.
      - 'fresh':      verified within PRICE_STALE_DAYS.
      - 'stale':      verified, but longer ago than PRICE_STALE_DAYS.
    """
    if not menu_data or not menu_data.get("prices_verified"):
        return {"state": "unverified", "date": None, "by": None, "age_days": None}
    when = menu_data.get("prices_verified_at")
    by = menu_data.get("prices_verified_by")
    if not when:
        return {"state": "unknown", "date": None, "by": by, "age_days": None}
    try:
        age = (_dt.date.today() - _dt.date.fromisoformat(when)).days
    except (ValueError, TypeError):
        return {"state": "unknown", "date": when, "by": by, "age_days": None}
    return {"state": "stale" if age > PRICE_STALE_DAYS else "fresh",
            "date": when, "by": by, "age_days": age}


def save_verified_prices(restaurant_id: str, price_updates: dict,
                         verified_by: str, today: str) -> dict:
    """Apply human-reviewed prices to a restaurant's stored menu and stamp it
    verified (date + who).

    `price_updates` maps "<cat_idx>:<item_idx>" -> price. A value that is blank,
    None or NaN clears that item's price. Only listed keys are touched. Writes
    menus_data.json back in its exact on-disk format (indent=2, ensure_ascii,
    no trailing newline) via an atomic replace so the git diff stays minimal;
    get_menu's mtime check reloads it on the next read. Returns {'changed': n}.
    """
    with open(_DATA_PATH) as f:
        data = _json.load(f)

    changed = 0
    for m in data:
        if m.get("id") != restaurant_id:
            continue
        cats = m.get("categories") or []
        for key, raw in price_updates.items():
            try:
                ci, ii = (int(x) for x in str(key).split(":"))
                item = cats[ci]["items"][ii]
            except (ValueError, IndexError, KeyError, TypeError):
                continue
            norm = None
            if raw not in ("", None):
                try:
                    f_val = float(raw)
                    if not _math.isnan(f_val):
                        norm = round(f_val, 2)
                except (TypeError, ValueError):
                    norm = None
            if norm != item.get("price"):
                item["price"] = norm
                changed += 1
        m["prices_verified"] = True
        m["prices_verified_at"] = today
        m["prices_verified_by"] = verified_by
        break

    tmp = _DATA_PATH + ".tmp"
    with open(tmp, "w") as f:
        f.write(_json.dumps(data, indent=2, ensure_ascii=True))
    _os.replace(tmp, _DATA_PATH)
    return {"changed": changed}


def display_categories(menu_data: dict) -> list:
    """Categories to show in a read-only menu *preview*.

    For ordinary menus this is just `categories`. For build-your-meal menus
    (Panda, Chipotle) the entrees and formats live in `builder`, not in
    `categories` — so the raw categories (Sides, Drinks) read as a broken,
    half-empty menu. Here we synthesize preview categories from the builder
    (Formats → Entrées → option groups) so the preview shows the full menu.
    The Orders-page build flow keeps reading `builder` directly; this only
    affects display.
    """
    cats = list(menu_data.get("categories") or [])
    if menu_data.get("menu_type") != "build":
        return cats

    b = menu_data.get("builder") or {}
    synth = []

    fmts = b.get("formats") or []
    if fmts:
        items = []
        for f in fmts:
            n = f.get("num_entrees")
            desc = f.get("description") or (
                f"{n} entrée{'s' if (n or 1) != 1 else ''}" if n else ""
            )
            items.append({"name": f.get("name", ""), "price": f.get("base"), "description": desc})
        synth.append({"name": "Choose your format", "items": items})

    prots = b.get("proteins") or []
    if prots:
        items = []
        for p in prots:
            desc = p.get("description") or ""
            up = p.get("upcharge")
            if up:
                desc = (desc + "  " if desc else "") + f"+${up:.2f}"
            items.append({"name": p.get("name", ""), "description": desc})
        synth.append({"name": b.get("entree_label") or "Entrées", "items": items})

    opt_stems = set()
    for label, choices in (b.get("options") or {}).items():
        if not choices:
            continue
        opt_stems.add(label.lower().rstrip("s"))
        synth.append({"name": label, "items": [{"name": c} for c in choices]})

    # Keep real categories not already covered by an option group (e.g. Drinks);
    # drop ones duplicated by options (e.g. a bare "Sides" == the "Side" option).
    for c in cats:
        if c.get("name", "").lower().rstrip("s") not in opt_stems:
            synth.append(c)

    return synth
