"""SQLite persistence and database schema initialization."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

from werkzeug.security import generate_password_hash


BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
DATABASE_PATH = Path(
    os.environ.get("REFEREE_DATABASE_PATH", DATA_DIR / "assignment.sqlite3")
)
# Initialization is cached per process and serialized between request threads.
_initialization_lock = Lock()
_initialized = False


SCHEMA = """
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
    """Open a configured SQLite connection without managing its transaction."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def initialize_database():
    """Create the schema, upgrade older tables, and seed a fresh database."""
    global _initialized
    if _initialized:
        return
    with _initialization_lock:
        if _initialized:
            return
        connection = _connect()
        try:
            connection.executescript(SCHEMA)
            # These additions keep databases created by earlier product versions
            # usable without rebuilding their contents.
            upload_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(uploads)")
            }
            if "source_file" not in upload_columns:
                connection.execute("ALTER TABLE uploads ADD COLUMN source_file BLOB")
                connection.commit()
            notification_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(notifications)")
            }
            for column in ("referee_id", "match_date"):
                if column not in notification_columns:
                    connection.execute(
                        f"ALTER TABLE notifications ADD COLUMN {column} TEXT"
                    )
            connection.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS notifications_referee_date_idx
                ON notifications(upload_id, notification_type, referee_id, match_date)
                WHERE referee_id IS NOT NULL AND match_date IS NOT NULL"""
            )
            connection.commit()
            # WAL allows readers to continue while a writer commits changes.
            connection.execute("PRAGMA journal_mode = WAL")
            with connection:
                # Seed entry accounts only when the database has no users. Existing
                # accounts and passwords are left untouched on later startups.
                has_users = connection.execute(
                    "SELECT 1 FROM users LIMIT 1"
                ).fetchone()
                if has_users is None:
                    for username, role in (("admin", "admin"), ("kuldo", "sender")):
                        connection.execute(
                            """INSERT INTO users(
                                username, password_hash, role, must_change_password, active
                            ) VALUES (?, ?, ?, 1, 1)""",
                            (username, generate_password_hash(username), role),
                        )
            _initialized = True
        finally:
            connection.close()


@contextmanager
def connect():
    """Yield one connection and commit it, rolling back if work raises."""
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
