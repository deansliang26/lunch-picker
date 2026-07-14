"""Baked historical lunch ledger — real team orders + daily winners from the
first weeks of the picker, exported once from the original ``lunch.db``.

WHY THIS EXISTS: the running-tab ledger on the History page is derived live from
the ``orders`` table. On the deployed (Streamlit Cloud) instance the SQLite file
is ephemeral and ``lunch.db`` is gitignored, so every redeploy/reboot wiped all
past orders — leaving the running tab showing only whatever had been ordered
since the last reset. Restaurants were reseeded on startup; the order/history
ledger was not, so past overages vanished. These rows are seeded on init
(``db._seed_ledger``) with INSERT OR IGNORE so the full ledger ships with the
app and survives redeploys, while never clobbering orders entered live.

Regenerate (if the historical baseline ever changes) by re-exporting the
``orders`` and ``history`` tables from a DB that holds the canonical history.
Winner ids reference the seed restaurants created by ``seed.seed()``.
"""

# (date, person, order_text, updated_at)
ORDERS = [
    ('2026-06-17', 'Aaron', 'Piza', '2026-06-17T16:14:09'),
    ('2026-06-17', 'Dean', '[{"item": "Old-School Pepperoni", "qty": 1, "notes": "Yay", "price": 6}, {"item": "D\'Lex Chicken & Bacon", "qty": 1, "notes": "", "price": 6.75}]', '2026-06-17T17:39:22'),
    ('2026-06-18', 'Aaron', '[{"item": "Yellowtail Jalapeno", "qty": 1, "notes": "", "price": 17.69}]', '2026-06-18T16:15:15'),
    ('2026-06-18', 'Cooper', '[{"item": "Salmon Avocado Roll", "qty": 1, "notes": "", "price": 8.04}, {"item": "Dynamite Roll", "qty": 1, "notes": "", "price": 12.64}]', '2026-06-18T16:49:24'),
    ('2026-06-18', 'Dean', '[{"item": "Edamame", "qty": 1, "notes": "", "price": 5.89}, {"item": "California Roll", "qty": 1, "notes": "", "price": 7.46}, {"item": "Salmon Avocado Roll", "qty": 1, "notes": "", "price": 8.84}]', '2026-06-18T14:56:35'),
    ('2026-06-18', 'Evan', '[{"item": "Edamame", "qty": 1, "notes": "", "price": 5.89}]', '2026-06-18T16:14:58'),
    ('2026-06-18', 'Parth', '[{"item": "Gyoza (6 Pieces)", "qty": 1, "notes": "", "price": 8.25}]', '2026-06-18T16:15:03'),
    ('2026-06-19', 'Cooper', '[{"item": "34 The Hunter Pence", "qty": 1, "notes": "no hot sauce pls!", "price": 20.65}]', '2026-06-19T11:03:48'),
    ('2026-06-19', 'Dean', '[{"item": "18 Matt Cain", "qty": 1, "notes": "", "price": 18.75}]', '2026-06-19T11:01:57'),
    ('2026-06-19', 'Evan', '[{"item": "18 Matt Cain", "qty": 1, "notes": "", "price": 18.75}]', '2026-06-19T11:03:10'),
    ('2026-06-19', 'Parth', '[{"item": "36 Your Favorite Sesame St Character", "qty": 1, "notes": "Sourdough, Freebies: Jalapenos, no Cream Cheese, no dirty sauce, skinny bread", "price": 16.25}]', '2026-06-19T11:09:20'),
    ('2026-06-21', 'Dean', '[{"item": "Peruvian Steak", "qty": 1, "notes": "", "price": 16.25}]', '2026-06-21T16:42:32'),
    ('2026-06-22', 'Aaron', '[{"item": "Arayes", "qty": 1, "notes": "", "price": 16.0}]', '2026-06-22T10:19:22'),
    ('2026-06-22', 'Cooper', '[{"item": "Arayes", "qty": 1, "notes": "less spice if possible", "price": 16.0}]', '2026-06-22T10:21:49'),
    ('2026-06-22', 'Dean', '[{"item": "Pita Chicken", "qty": 1, "notes": "", "price": 16.0}]', '2026-06-22T10:20:26'),
    ('2026-06-22', 'Evan', '[{"item": "Pita Beef Kebab", "qty": 1, "notes": "White Pita", "price": 16.0}]', '2026-06-22T10:21:35'),
    ('2026-06-22', 'Parth', '[{"item": "Pita Green Herb Falafel", "qty": 1, "notes": "", "price": 16.0}, {"item": "Bourekas", "qty": 1, "notes": "", "price": 4.75}]', '2026-06-22T10:20:40'),
    ('2026-06-26', 'Dean', '[{"item": "Yellowtail Jalapeno", "qty": 1, "notes": "", "price": 14.99}]', '2026-06-26T16:30:38'),
    ('2026-06-26', 'Evan', '[{"item": "Unagi Avocado Hand Roll", "qty": 2, "notes": "", "price": 6.99}]', '2026-06-26T16:30:38'),
    ('2026-06-26', 'Parth', '[{"item": "Gyoza (6 Pieces)", "qty": 1, "notes": "", "price": 8.25}, {"item": "Edamame", "qty": 1, "notes": "", "price": 4.99}, {"item": "Dragon Roll", "qty": 1, "notes": "", "price": 15.49}]', '2026-06-26T16:30:38'),
]

# (date, winner_place_id, vote_count, total_voters, decided_at)
HISTORY = [
    ('2026-06-17', 'seed-pizza-my-heart', 3, 5, '2026-06-17T16:12:59'),
    ('2026-06-18', 'seed-mj-sushi', 3, 5, '2026-06-18T11:06:07'),
    ('2026-06-19', 'seed-ike-s-love-sandwiches', 3, 5, '2026-06-19T11:00:35'),
    ('2026-06-21', 'seed-mendocino-farms', 3, 5, '2026-06-21T15:37:07'),
    ('2026-06-22', 'seed-oren-s-hummus-shop', 2, 5, '2026-06-22T10:13:54'),
    ('2026-06-26', 'seed-mj-sushi', 3, 5, '2026-06-26T16:30:38'),
]
