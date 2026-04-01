import sqlite3
import os
import threading

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "hunt.db")

_lock = threading.Lock()
_conn = None


def get_db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS stations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            lat REAL,
            lng REAL,
            code TEXT NOT NULL UNIQUE,
            points INTEGER DEFAULT 10,
            sort_order INTEGER DEFAULT 0,
            question_type TEXT DEFAULT 'qr_only',
            question_text TEXT DEFAULT '',
            choices TEXT DEFAULT '',
            correct_answer TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            pin TEXT NOT NULL,
            login_token TEXT UNIQUE,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            station_id INTEGER NOT NULL,
            answer TEXT DEFAULT '',
            photo_path TEXT DEFAULT '',
            status TEXT DEFAULT 'approved',
            scanned_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (station_id) REFERENCES stations(id),
            UNIQUE(team_id, station_id)
        );

        CREATE TABLE IF NOT EXISTS admin_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_user TEXT NOT NULL,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id INTEGER,
            details TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    # Migrate existing tables: add new columns if missing
    cols_stations = {r["name"] for r in conn.execute("PRAGMA table_info(stations)").fetchall()}
    for col, default in [("question_type", "'qr_only'"), ("question_text", "''"), ("choices", "''"), ("correct_answer", "''")]:
        if col not in cols_stations:
            conn.execute(f"ALTER TABLE stations ADD COLUMN {col} TEXT DEFAULT {default}")
    cols_scans = {r["name"] for r in conn.execute("PRAGMA table_info(scans)").fetchall()}
    for col, default in [("answer", "''"), ("photo_path", "''"), ("status", "'approved'")]:
        if col not in cols_scans:
            conn.execute(f"ALTER TABLE scans ADD COLUMN {col} TEXT DEFAULT {default}")
    # Migrate teams table: add login_token if missing
    cols_teams = {r["name"] for r in conn.execute("PRAGMA table_info(teams)").fetchall()}
    if "login_token" not in cols_teams:
        conn.execute("ALTER TABLE teams ADD COLUMN login_token TEXT UNIQUE")
    conn.commit()


def close_db():
    global _conn
    if _conn:
        _conn.close()
        _conn = None
