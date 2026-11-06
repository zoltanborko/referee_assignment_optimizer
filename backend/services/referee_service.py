import json
from datetime import date
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from werkzeug.security import generate_password_hash

from services.database import connect
from services.match_pool_service import create_unavailability_notifications


CADRES = {"megye1", "megye2", "megye3", "megye_egyeb"}


def load_referees():
    with connect() as connection:
        rows = connection.execute(
            "SELECT profile_json FROM referees ORDER BY rowid"
        ).fetchall()
    return [json.loads(row["profile_json"]) for row in rows]


def save_referees(referees):
    with connect() as connection:
        for referee in referees:
            referee_id = str(referee["id"])
            connection.execute(
                """INSERT INTO referees(referee_id, profile_json) VALUES (?, ?)
                ON CONFLICT(referee_id) DO UPDATE SET profile_json = excluded.profile_json""",
                (referee_id, json.dumps(referee, ensure_ascii=False)),
            )
            connection.execute(
                """INSERT OR IGNORE INTO users(
                    username, password_hash, role, must_change_password, active, referee_id
                ) VALUES (?, ?, 'referee', 1, ?, ?)""",
                (
                    referee_id,
                    generate_password_hash(referee_id),
                    int(referee.get("active") is True),
                    referee_id,
                ),
            )
            connection.execute(
                """UPDATE users SET referee_id = ?, active = ?
                WHERE username = ? AND role = 'referee' AND referee_id IS NULL""",
                (referee_id, int(referee.get("active") is True), referee_id),
            )
            connection.execute(
                "UPDATE users SET active = ? WHERE referee_id = ?",
                (int(referee.get("active") is True), referee_id),
            )


def normalize_referee(data):
    if not isinstance(data, dict):
        raise ValueError("A játékvezető adatai hibásak.")

    referee_id = str(data.get("id", "")).strip()
    name = str(data.get("name", "")).strip()
    residence = str(data.get("residence", "")).strip()
    cadre = str(data.get("cadre", "")).strip()
    has_car = data.get("has_car")
    active = data.get("active")
    banned_teams = data.get("banned_teams", [])
    unavailable_dates = data.get("unavailable_dates", [])

    if not referee_id:
        raise ValueError("Az azonosító megadása kötelező.")
    if not name:
        raise ValueError("A név megadása kötelező.")
    if cadre and cadre not in CADRES:
        raise ValueError("Érvénytelen keretkategória.")
    if has_car not in (True, False, None):
        raise ValueError("Az autó mező értéke igen, nem vagy üres lehet.")
    if active not in (True, False, None):
        raise ValueError("A státusz értéke aktív vagy inaktív lehet.")
    if not isinstance(banned_teams, list) or not all(
        isinstance(team, str) for team in banned_teams
    ):
        raise ValueError("A tiltott csapatokat listaként kell megadni.")
    if not isinstance(unavailable_dates, list) or not all(
        isinstance(unavailable_date, str) for unavailable_date in unavailable_dates
    ):
        raise ValueError("A nem elérhető dátumokat YYYY-MM-DD formátumú listaként kell megadni.")

    normalized_unavailable_dates = []
    for unavailable_date in unavailable_dates:
        unavailable_date = unavailable_date.strip()
        try:
            valid_date = date.fromisoformat(unavailable_date)
        except ValueError as error:
            raise ValueError("A nem elérhető dátumokat YYYY-MM-DD formátumban kell megadni.") from error
        if valid_date.isoformat() != unavailable_date:
            raise ValueError("A nem elérhető dátumokat YYYY-MM-DD formátumban kell megadni.")
        if unavailable_date not in normalized_unavailable_dates:
            normalized_unavailable_dates.append(unavailable_date)

    return {
        "id": referee_id,
        "name": name,
        "residence": residence,
        "cadre": cadre,
        "has_car": has_car,
        "banned_teams": list(dict.fromkeys(
            team.strip() for team in banned_teams if team.strip()
        )),
        "unavailable_dates": normalized_unavailable_dates,
        "active": active,
    }


def add_referee(data):
    referees = load_referees()
    referee = normalize_referee(data)
    if any(str(item.get("id")) == referee["id"] for item in referees):
        raise ValueError("Már létezik játékvezető ezzel az azonosítóval.")
    if referee["active"] is None:
        referee["active"] = True
    referees.append(referee)
    save_referees(referees)
    return referee


def update_referee(referee_id, data):
    if not isinstance(data, dict):
        raise ValueError("A játékvezető adatai hibásak.")
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT profile_json FROM referees WHERE referee_id = ?",
            (str(referee_id),),
        ).fetchone()
        if row is None:
            return None

        current = json.loads(row["profile_json"])
        referee = normalize_referee({
            **current,
            **{key: value for key, value in data.items() if key != "unavailable_dates"},
            "id": current["id"],
            "unavailable_dates": current.get("unavailable_dates", []),
        })
        connection.execute(
            "UPDATE referees SET profile_json = ? WHERE referee_id = ?",
            (json.dumps(referee, ensure_ascii=False), str(referee_id)),
        )
        connection.execute(
            "UPDATE users SET active = ? WHERE referee_id = ?",
            (int(referee.get("active") is True), str(referee_id)),
        )
    return referee


def update_own_referee(referee_id, data):
    if not isinstance(data, dict):
        raise ValueError("A játékvezető adatai hibásak.")
    editable_fields = {"residence", "has_car", "banned_teams", "unavailable_dates"}
    if set(data) - editable_fields:
        raise ValueError("Csak a lakóhely, az autó, a tiltott csapatok és a lemondott dátumok módosíthatók.")

    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT profile_json FROM referees WHERE referee_id = ?",
            (str(referee_id),),
        ).fetchone()
        if row is None:
            return None

        current = json.loads(row["profile_json"])
        updated = normalize_referee({**current, **data})
        old_dates = set(current.get("unavailable_dates") or [])
        new_dates = set(updated.get("unavailable_dates") or [])
        added_dates = new_dates - old_dates
        earliest_allowed_date = datetime.now(ZoneInfo("Europe/Budapest")).date() + timedelta(days=5)
        for unavailable_date in added_dates:
            if date.fromisoformat(unavailable_date) < earliest_allowed_date:
                raise ValueError("Lemondást legkésőbb a mérkőzés előtt 5 nappal lehet rögzíteni.")

        connection.execute(
            "UPDATE referees SET profile_json = ? WHERE referee_id = ?",
            (json.dumps(updated, ensure_ascii=False), str(referee_id)),
        )
    # Reconcile all saved dates, so a notification missed by an older database
    # schema or a previous failed request can be created on the next profile save.
    create_unavailability_notifications(
        updated["id"], updated["name"], sorted(new_dates)
    )
    return updated


def delete_referee(referee_id):
    referee_id = str(referee_id)
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        exists = connection.execute(
            "SELECT 1 FROM referees WHERE referee_id = ?", (referee_id,)
        ).fetchone()
        if exists is None:
            return False
        connection.execute(
            "UPDATE users SET active = 0, referee_id = NULL WHERE referee_id = ?",
            (referee_id,),
        )
        connection.execute("DELETE FROM referees WHERE referee_id = ?", (referee_id,))
    return True
