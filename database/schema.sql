-- EcoGrid: Community Solar Planner
-- SQLite schema — applied automatically on first run via app.py
-- ---------------------------------------------------------------

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------
-- Table: locations
-- Stores user-submitted map coordinates with display metadata.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS locations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL,
    latitude            REAL    NOT NULL,
    longitude           REAL    NOT NULL,
    system_capacity_kw  REAL    NOT NULL DEFAULT 4.0,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------
-- Table: solar_estimates
-- Caches the 12-month simulated output for each location.
-- Deleted automatically when parent location is removed.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS solar_estimates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id     INTEGER NOT NULL
                        REFERENCES locations(id) ON DELETE CASCADE,
    annual_kwh      REAL    NOT NULL,
    monthly_kwh     TEXT    NOT NULL,   -- JSON array: [jan, feb, ..., dec]
    ac_annual       REAL    NOT NULL,
    solrad_annual   REAL    NOT NULL,
    computed_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_estimates_location
    ON solar_estimates(location_id);
