"""User authentication and account operations."""

import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

from services.database import connect


def _user_dict(row):
    """Convert a SQLite user row to the public, password-free shape."""
    if row is None:
        return None
    return {
        "user_id": row["user_id"],
        "username": row["username"],
        "role": row["role"],
        "must_change_password": bool(row["must_change_password"]),
        "active": bool(row["active"]),
        "referee_id": row["referee_id"],
    }


def get_user(user_id):
    """Fetch one account for session validation."""
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    return _user_dict(row)


def authenticate(username, password):
    """Verify credentials and refuse disabled accounts."""
    if not isinstance(username, str) or not isinstance(password, str):
        return None
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
    if row is None or not row["active"]:
        return None
    if not check_password_hash(row["password_hash"], password):
        return None
    return _user_dict(row)


def change_password(user_id, current_password, new_password):
    """Verify the current password, enforce minimum length, and replace it."""
    if not isinstance(current_password, str) or not isinstance(new_password, str):
        raise ValueError("A jelenlegi és az új jelszó megadása kötelező.")
    if len(new_password) < 8:
        raise ValueError("Az új jelszónak legalább 8 karakteresnek kell lennie.")
    with connect() as connection:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE user_id = ? AND active = 1",
            (user_id,),
        ).fetchone()
        if row is None or not check_password_hash(row["password_hash"], current_password):
            raise ValueError("A jelenlegi jelszó hibás.")
        connection.execute(
            """UPDATE users SET password_hash = ?, must_change_password = 0
            WHERE user_id = ?""",
            (generate_password_hash(new_password), user_id),
        )
    return get_user(user_id)


def list_users():
    """Return account metadata without exposing password hashes."""
    with connect() as connection:
        rows = connection.execute(
            """SELECT user_id, username, role, must_change_password, active, referee_id
            FROM users ORDER BY role, username"""
        ).fetchall()
    return [_user_dict(row) for row in rows]


def create_user(username, role):
    """Create an admin or sender account with a username-based temporary password."""
    if not isinstance(username, str) or not username.strip():
        raise ValueError("A felhasználónév megadása kötelező.")
    username = username.strip()
    if len(username) > 64:
        raise ValueError("A felhasználónév legfeljebb 64 karakter lehet.")
    if role not in {"admin", "sender"}:
        raise ValueError("Csak admin- vagy küldőfiók hozható létre ezen a végponton.")
    try:
        with connect() as connection:
            cursor = connection.execute(
                """INSERT INTO users(
                    username, password_hash, role, must_change_password, active
                ) VALUES (?, ?, ?, 1, 1)""",
                (username, generate_password_hash(username), role),
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError as error:
        raise ValueError("Már létezik fiók ezzel a felhasználónévvel.") from error
    return get_user(user_id)


def set_user_active(user_id, active):
    """Enable or disable a non-referee account without disabling the last admin."""
    if not isinstance(active, bool):
        raise ValueError("Az aktív állapot értéke true vagy false lehet.")
    with connect() as connection:
        current = connection.execute(
            "SELECT role, active FROM users WHERE user_id = ? AND referee_id IS NULL",
            (user_id,),
        ).fetchone()
        if current is None:
            return None
        if not active and current["role"] == "admin" and current["active"]:
            active_admins = connection.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1"
            ).fetchone()[0]
            if active_admins <= 1:
                raise ValueError("Az utolsó aktív adminfiók nem inaktiválható.")
        cursor = connection.execute(
            "UPDATE users SET active = ? WHERE user_id = ? AND referee_id IS NULL",
            (int(active), user_id),
        )
    return get_user(user_id) if cursor.rowcount else None


def reset_user_password(user_id, temporary_password):
    """Set a temporary password and require it to be changed at next login."""
    if not isinstance(temporary_password, str) or len(temporary_password) < 8:
        raise ValueError("Az ideiglenes jelszónak legalább 8 karakteresnek kell lennie.")
    with connect() as connection:
        cursor = connection.execute(
            """UPDATE users SET password_hash = ?, must_change_password = 1
            WHERE user_id = ? AND (role != 'referee' OR referee_id IS NOT NULL)""",
            (generate_password_hash(temporary_password), user_id),
        )
    return get_user(user_id) if cursor.rowcount else None
