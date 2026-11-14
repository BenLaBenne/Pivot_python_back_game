# PIVOT — Python backend

Python/Flask backend foundation for the PIVOT v2 project. It replaces the Node.js backend with Python, PostgreSQL, JWT authentication, bcrypt password hashing, and a server-authoritative implementation of the core board rules.

## Included now

- PostgreSQL user table initialized automatically on application startup.
- Signup, login, and authenticated profile endpoints.
- PIVOT 7×7 game state and validated actions: `glisser`, `virage`, `diagonale`, `borne`, `tp`, `tp_suite`, and the first-turn `echange` choice.
- Render Blueprint configuration (`render.yaml`) to deploy the web service and PostgreSQL database.
- Health endpoint at `/api/health`.

This is a Python backend starter, not a feature-for-feature port of all the original Node app. Ranked matchmaking/Elo, persistent match history and inventories, shop/chests, tournaments, reports/admin tools, season/pass, and the original full UI still need to be ported. Active games currently live in process memory and are lost on restart; use PostgreSQL/Redis persistence before treating it as production multiplayer. The first player can create a game and share its game ID; a second signed-in user can join by requesting that game.

## Run locally

Requires Python 3.12 and PostgreSQL.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # Set DATABASE_URL and JWT_SECRET
python app.py
```

Open `http://localhost:5000/api/health`. On local startup, `app.py` creates the user table. The Render/Gunicorn deployment also initializes it at app startup through the WSGI import hook below.

## API

- `POST /api/auth/signup` JSON `{ "pseudo": "player_1", "password": "at-least-8-chars" }`
- `POST /api/auth/login` JSON `{ "pseudo": "player_1", "password": "..." }`
- `GET /api/auth/me` with `Authorization: Bearer <token>`
- `POST /api/games` with bearer token → new game ID and role R
- `GET /api/games/<gameId>` with bearer token → joins as B if slot is free, or returns current state
- `POST /api/games/<gameId>/actions` with bearer token and action JSON
- `GET /api/health`

Action examples: `{ "type": "glisser", "to": { "x": 3, "y": 1 } }`; `{ "type": "echange", "garder": true }` after Red's first turn. Coordinates are zero-based, from 0 to 6.

## Deploy on Render

1. Push this repository to GitHub and open Render's **New → Blueprint** flow for it.
2. Render reads `render.yaml` and creates the Python web service and PostgreSQL database.
3. `DATABASE_URL` is linked from the database, and Render generates `JWT_SECRET`. Do not add a real secret to the repository.
4. After the deploy completes, open the service URL and check `/api/health`.

Render settings from the blueprint:

| Setting | Value |
|---|---|
| Runtime | Python |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn --worker-class gthread --threads 4 --bind 0.0.0.0:$PORT app:app` |
| Health check | `/api/health` |
| Environment variables | `DATABASE_URL` (from linked DB), generated `JWT_SECRET`, `PYTHON_VERSION=3.12.8` |

For local `.env`, set `DATABASE_URL` to your PostgreSQL connection string, `JWT_SECRET` to a unique random value, and optionally `PORT` (defaults to 5000). Render's free service/database availability and retention can change; confirm current plan limits in your Render dashboard.
