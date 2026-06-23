# 🍜 PA Lunch Picker

A small Streamlit app for the team to vote on and order lunch. Vote on the day's
restaurant, browse menus, place orders, and track history — themed to the Pareto
Agent design system.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
echo "YELP_API_KEY=your_key_here" > .env   # optional; Yelp suggestions degrade gracefully without it
streamlit run app.py
```

## Hosted (Streamlit Community Cloud)

Deployed from this repo: main module `app.py`.

Set under **App settings → Secrets**:

```toml
YELP_API_KEY = "your_yelp_fusion_key"
# CLOUD = "1"   # optional flag; hides the local-only browser auto-fill button
```

Notes for the hosted build:

- **Storage is ephemeral.** Votes / orders / history live in a local SQLite file
  (`lunch.db`) that resets when the app sleeps or redeploys. On a fresh start the
  restaurant list re-seeds automatically (`db.init_db()` → `seed.seed()`).
- **Auto-fill cart** (browser automation in `autoorder.py`) only works on a machine
  with a real browser, so it is hidden on the hosted build. Voting, ordering, menus,
  and history all work.
