# menus.py — Real menu data scraped from restaurant websites (June 2026).
import json as _json
import os as _os

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_DATA_PATH = _os.path.join(_HERE, "menus_data.json")


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

    # Rich option groups (choices may be plain strings or {name, price}).
    for g in (b.get("option_groups") or []):
        choices = g.get("choices") or []
        if not choices:
            continue
        opt_stems.add(g.get("name", "").lower().rstrip("s"))
        items = []
        for c in choices:
            if isinstance(c, dict):
                it = {"name": c.get("name", "")}
                if c.get("price"):
                    it["price"] = c["price"]
                items.append(it)
            else:
                items.append({"name": c})
        synth.append({"name": g.get("name", "Options"), "items": items})

    # Keep real categories not already covered by an option group (e.g. Drinks);
    # drop ones duplicated by options (e.g. a bare "Sides" == the "Side" option).
    for c in cats:
        if c.get("name", "").lower().rstrip("s") not in opt_stems:
            synth.append(c)

    return synth
