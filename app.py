"""
EcoGrid: Community Solar Planner
Flask application entry point.

Responsibilities:
  - Load secrets from .env via python-dotenv
  - Connect to SQLite and apply schema on first run
  - Register the `api` Blueprint (which calls real NREL PVWatts v8 API)
  - Serve index.html via a catch-all route (SPA pattern)
  - Run on port 5000 in debug mode during development
"""

import os
import sqlite3

from dotenv import load_dotenv  # reads .env into os.environ
from flask import Flask, render_template
from flask_cors import CORS

from api.routes import api_bp

# ---------------------------------------------------------------------------
# Load environment variables — .env for local dev, real env vars on Render
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))  # no-op on Render (env vars set in dashboard)

# On Render, SQLite lives in /tmp (ephemeral but fine for a demo).
# Locally it stays in database/ecogrid.db as before.
_db_dir     = os.environ.get("DB_DIR", os.path.join(BASE_DIR, "database"))
DB_PATH     = os.path.join(_db_dir, "ecogrid.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "database", "schema.sql")


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)  # Allow same-origin JS fetch during local dev

    # Store runtime config so blueprints can read it via current_app.config
    app.config["DB_PATH"]      = DB_PATH
    app.config["NREL_API_KEY"] = os.environ.get("NREL_API_KEY", "")

    nrel_key = app.config["NREL_API_KEY"]
    if nrel_key:
        print(f"  [config] NREL API key loaded ({nrel_key[:6]}...)")
    else:
        print("  [config] WARNING: NREL_API_KEY not found — falling back to mock data")

    # ------------------------------------------------------------------
    # Initialise the database (idempotent — uses CREATE TABLE IF NOT EXISTS)
    # ------------------------------------------------------------------
    _init_db()

    # ------------------------------------------------------------------
    # Register blueprints
    # ------------------------------------------------------------------
    app.register_blueprint(api_bp)

    # ------------------------------------------------------------------
    # SPA catch-all — every non-API route serves index.html so the
    # front-end router can handle its own paths if extended later.
    # ------------------------------------------------------------------
    @app.route("/", defaults={"_path": ""})
    @app.route("/<path:_path>")
    def serve_spa(_path: str):
        return render_template("index.html")

    return app


def _init_db() -> None:
    """Create the database directory and apply schema.sql if needed."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = create_app()
    print("  EcoGrid dev server -> http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
