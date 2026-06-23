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
