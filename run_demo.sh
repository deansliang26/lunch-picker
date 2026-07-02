#!/usr/bin/env bash
# Launch an ISOLATED demo instance of the lunch picker for showing
# restaurant selection + autofill — without touching today's real pick.
#   • separate database:  lunch.demo.db   (real lunch.db is untouched)
#   • separate port:       8502            (so it can run alongside the real app)
# Re-run any time; it re-seeds a fresh demo scenario on each launch.
set -e
cd "$(dirname "$0")"

export LUNCH_DB_PATH="$(pwd)/lunch.demo.db"
PY="./.venv/bin/python"

echo "Seeding demo scenario…"
"$PY" demo_setup.py

echo "Starting demo on http://localhost:8502  (Ctrl-C to stop)…"
exec "$PY" -m streamlit run app.py \
    --server.port 8502 \
    --server.headless false \
    --browser.serverAddress localhost
