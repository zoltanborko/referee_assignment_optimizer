"""SQLite persistence and one-time import of the existing JSON data."""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from werkzeug.security import generate_password_hash


BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
DATABASE_PATH = Path(
    os.environ.get("REFEREE_DATABASE_PATH", DATA_DIR / "assignment.sqlite3")
)
_initialization_lock = Lock()
_initialized = False


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_key TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS referees (
    referee_id TEXT PRIMARY KEY,
    profile_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('referee', 'sender', 'admin')),
    must_change_password INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    referee_id TEXT UNIQUE REFERENCES referees(referee_id)
);

CREATE TABLE IF NOT EXISTS ref_pool (
    referee_id TEXT PRIMARY KEY REFERENCES referees(referee_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS uploads (
    upload_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_by INTEGER REFERENCES users(user_id),
    source_filename TEXT,
    source_file BLOB,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'finalized')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS upload_dates (
    upload_id INTEGER NOT NULL REFERENCES uploads(upload_id) ON DELETE CASCADE,
    match_date TEXT NOT NULL,
    PRIMARY KEY (upload_id, match_date),
    UNIQUE (match_date)
);

CREATE TABLE IF NOT EXISTS matches (
    match_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER NOT NULL REFERENCES uploads(upload_id) ON DELETE CASCADE,
    match_date TEXT NOT NULL,
    position INTEGER NOT NULL,
    external_id_json TEXT,
    match_json TEXT NOT NULL,
    unassigned INTEGER NOT NULL DEFAULT 0,
    UNIQUE (upload_id, position)
);

CREATE INDEX IF NOT EXISTS matches_upload_date_idx
    ON matches(upload_id, match_date, position);
CREATE INDEX IF NOT EXISTS matches_date_idx ON matches(match_date);

CREATE TABLE IF NOT EXISTS assignment_versions (
    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER NOT NULL REFERENCES uploads(upload_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'superseded')),
    created_at TEXT NOT NULL,
    success INTEGER NOT NULL,
    partial INTEGER NOT NULL,
    capacity_sufficient INTEGER NOT NULL,
    total_travel_distance REAL NOT NULL,
    assigned_count INTEGER NOT NULL,
    unassigned_count INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_draft_per_upload_idx
    ON assignment_versions(upload_id) WHERE status = 'draft';
CREATE UNIQUE INDEX IF NOT EXISTS one_published_per_upload_idx
    ON assignment_versions(upload_id) WHERE status = 'published';

CREATE TABLE IF NOT EXISTS version_matches (
    version_match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL REFERENCES assignment_versions(version_id) ON DELETE CASCADE,
    match_date TEXT NOT NULL,
    position INTEGER NOT NULL,
    match_json TEXT NOT NULL,
    unassigned INTEGER NOT NULL DEFAULT 0,
    UNIQUE(version_id, match_date, position)
);
CREATE INDEX IF NOT EXISTS version_matches_date_idx
    ON version_matches(version_id, match_date, position);

CREATE TABLE IF NOT EXISTS assignment_unused_referees (
    version_id INTEGER NOT NULL REFERENCES assignment_versions(version_id) ON DELETE CASCADE,
    match_date TEXT NOT NULL,
    referee_id TEXT NOT NULL,
    referee_name TEXT NOT NULL,
    PRIMARY KEY (version_id, match_date, referee_id)
);

CREATE TABLE IF NOT EXISTS upload_referee_exclusions (
    upload_id INTEGER NOT NULL REFERENCES uploads(upload_id) ON DELETE CASCADE,
    match_date TEXT NOT NULL,
    referee_id TEXT NOT NULL REFERENCES referees(referee_id) ON DELETE CASCADE,
    PRIMARY KEY (upload_id, match_date, referee_id)
);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER NOT NULL REFERENCES uploads(upload_id) ON DELETE CASCADE,
    notification_type TEXT NOT NULL,
    referee_id TEXT NOT NULL,
    match_date TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT,
    UNIQUE(upload_id, notification_type, referee_id, match_date)
);
CREATE INDEX IF NOT EXISTS notifications_upload_idx
    ON notifications(upload_id, read_at, created_at);
"""


def _connect():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def _read_json(path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _legacy_match_pools():
    pool_files = sorted(DATA_DIR.glob("match_pool_*.json"))
    if not pool_files:
        legacy_path = DATA_DIR / "match_pool.json"
        pool_files = [legacy_path] if legacy_path.exists() else []

    pools = []
    if pool_files:
        for path in pool_files:
            data = _read_json(path, {})
            matches = data.get("match_pool", data.get("matchpool", []))
            unassigned_ids = {str(value) for value in data.get("unassigned_match_ids", [])}
            grouped = {}
            for match in matches:
                match_date = str(match.get("date") or "")
                if match_date:
                    grouped.setdefault(match_date, []).append(match)
            for match_date, date_matches in grouped.items():
                pools.append((match_date, date_matches, unassigned_ids))
        return pools

    raw_matches = _read_json(DATA_DIR / "matches.json", {}).get("matches", [])
    grouped = {}
    for match in raw_matches:
        match_date = str(match.get("date") or "")
        if match_date:
            grouped.setdefault(match_date, []).append(match)
    return [(match_date, date_matches, set()) for match_date, date_matches in grouped.items()]


def _insert_legacy_upload(connection, match_date, matches, unassigned_ids, admin_id):
    cursor = connection.execute(
        "INSERT INTO uploads(created_by, source_filename, status, created_at) VALUES (?, ?, ?, ?)",
        (admin_id, "JSON migráció", "draft", datetime.now(timezone.utc).isoformat()),
    )
    upload_id = cursor.lastrowid
    connection.execute(
        "INSERT INTO upload_dates(upload_id, match_date) VALUES (?, ?)",
        (upload_id, match_date),
    )
    for position, match in enumerate(matches):
        match_id = match.get("id")
        connection.execute(
            """INSERT INTO matches(
                upload_id, match_date, position, external_id_json, match_json, unassigned
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                upload_id,
                match_date,
                position,
                _json(match_id) if match_id is not None else None,
                _json(match),
                int(str(match_id) in unassigned_ids),
            ),
        )


def initialize_database():
    """Create the schema and import JSON data once, preserving the source files."""
    global _initialized
    if _initialized:
        return
    with _initialization_lock:
        if _initialized:
            return
        connection = _connect()
        try:
            connection.executescript(SCHEMA)
            upload_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(uploads)")
            }
            if "source_file" not in upload_columns:
                connection.execute("ALTER TABLE uploads ADD COLUMN source_file BLOB")
                connection.commit()
            connection.execute("PRAGMA journal_mode = WAL")
            migration_done = connection.execute(
                "SELECT 1 FROM schema_migrations WHERE migration_key = ?",
                ("import_json_v1",),
            ).fetchone()
            if migration_done is None:
                with connection:
                    referee_data = _read_json(DATA_DIR / "referees.json", {})
                    referees = referee_data.get("referees", [])
                    for referee in referees:
                        referee_id = str(referee.get("id", ""))
                        if not referee_id:
                            continue
                        connection.execute(
                            "INSERT OR IGNORE INTO referees(referee_id, profile_json) VALUES (?, ?)",
                            (referee_id, _json(referee)),
                        )

                    connection.execute(
                        """INSERT OR IGNORE INTO users(
                            username, password_hash, role, must_change_password, active
                        ) VALUES (?, ?, 'admin', 1, 1)""",
                        ("admin", generate_password_hash("admin")),
                    )
                    admin = connection.execute(
                        "SELECT user_id FROM users WHERE username = 'admin'"
                    ).fetchone()
                    admin_id = admin["user_id"]
                    connection.execute(
                        """INSERT OR IGNORE INTO users(
                            username, password_hash, role, must_change_password, active
                        ) VALUES (?, ?, 'sender', 1, 1)""",
                        ("kuldo", generate_password_hash("kuldo")),
                    )

                    for referee in referees:
                        referee_id = str(referee.get("id", ""))
                        if not referee_id:
                            continue
                        connection.execute(
                            """INSERT OR IGNORE INTO users(
                                username, password_hash, role, must_change_password,
                                active, referee_id
                            ) VALUES (?, ?, 'referee', 1, ?, ?)""",
                            (
                                referee_id,
                                generate_password_hash(referee_id),
                                int(referee.get("active") is True),
                                referee_id,
                            ),
                        )

                    ref_pool_data = _read_json(DATA_DIR / "ref_pool.json", {})
                    selected = ref_pool_data.get("referees")
                    if selected is None:
                        selected_ids = ref_pool_data.get("referee_ids", [])
                    else:
                        selected_ids = [
                            referee.get("id") for referee in selected
                            if isinstance(referee, dict) and referee.get("id") is not None
                        ]
                    for referee_id in selected_ids:
                        connection.execute(
                            "INSERT OR IGNORE INTO ref_pool(referee_id) VALUES (?)",
                            (str(referee_id),),
                        )

                    for match_date, matches, unassigned_ids in _legacy_match_pools():
                        _insert_legacy_upload(
                            connection, match_date, matches, unassigned_ids, admin_id
                        )

                    connection.execute(
                        "INSERT INTO schema_migrations(migration_key, applied_at) VALUES (?, ?)",
                        ("import_json_v1", datetime.now(timezone.utc).isoformat()),
                    )
            _initialized = True
        finally:
            connection.close()


@contextmanager
def connect():
    initialize_database()
    connection = _connect()
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()


initialize_database()
