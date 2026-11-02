import json
import sqlite3
from datetime import datetime, timedelta, timezone

from services.database import connect


age_group_mapping = {
    "U-12": 1,
    "U-13": 1,
    "U-14": 1,
    "U-15": 1,
    "U-16": 1,
    "U-19": 2,
    "U-21": 2,
    "felnőtt": 2,
}


def save_matchpool(matchlist, unassigned_match_ids=None, match_date=None):
    """Update one date's matches in the upload that owns that date."""
    if match_date is None:
        dates = sorted({str(match.get("date") or "") for match in matchlist} - {""})
        if len(dates) > 1:
            unassigned = set(unassigned_match_ids or [])
            for date in dates:
                save_matchpool(
                    [match for match in matchlist if str(match.get("date") or "") == date],
                    [match.get("id") for match in matchlist
                     if str(match.get("date") or "") == date and match.get("id") in unassigned]
                    if unassigned_match_ids is not None else None,
                    date,
                )
            return
        if dates:
            match_date = dates[0]
    if not match_date:
        raise ValueError("A mérkőzések dátuma kötelező.")

    with connect() as connection:
        upload = connection.execute(
            "SELECT upload_id FROM upload_dates WHERE match_date = ?", (match_date,)
        ).fetchone()
        if upload is None:
            raise ValueError(f"Nincs feltöltés ehhez a dátumhoz: {match_date}.")
        upload_id = upload["upload_id"]
        if unassigned_match_ids is None:
            prior = connection.execute(
                "SELECT match_json, unassigned FROM matches WHERE upload_id = ? AND match_date = ?",
                (upload_id, match_date),
            ).fetchall()
            unassigned_keys = {
                json.loads(row["match_json"]).get("id")
                for row in prior if row["unassigned"]
            }
        else:
            unassigned_keys = set(unassigned_match_ids)
        connection.execute(
            "DELETE FROM matches WHERE upload_id = ? AND match_date = ?",
            (upload_id, match_date),
        )
        connection.executemany(
            """INSERT INTO matches(
                upload_id, match_date, position, external_id_json, match_json, unassigned
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    upload_id,
                    match_date,
                    position,
                    json.dumps(match.get("id"), ensure_ascii=False)
                    if match.get("id") is not None else None,
                    json.dumps(match, ensure_ascii=False),
                    int(match.get("id") in unassigned_keys),
                )
                for position, match in enumerate(matchlist)
            ],
        )


def get_match_dates():
    with connect() as connection:
        rows = connection.execute(
            "SELECT match_date FROM upload_dates ORDER BY match_date"
        ).fetchall()
    return [row["match_date"] for row in rows]


def get_upload(upload_id, owner_id=None):
    query = "SELECT * FROM uploads WHERE upload_id = ?"
    parameters = [upload_id]
    if owner_id is not None:
        query += " AND created_by = ?"
        parameters.append(owner_id)
    with connect() as connection:
        row = connection.execute(query, parameters).fetchone()
        if row is None:
            return None
        dates = connection.execute(
            "SELECT match_date FROM upload_dates WHERE upload_id = ? ORDER BY match_date",
            (upload_id,),
        ).fetchall()
        versions = connection.execute(
            """SELECT version_id, status, created_at, success, partial,
                capacity_sufficient, total_travel_distance, assigned_count,
                unassigned_count
            FROM assignment_versions WHERE upload_id = ?
            AND status IN ('draft', 'published')
            ORDER BY version_id DESC""",
            (upload_id,),
        ).fetchall()
    info = dict(row)
    info["dates"] = [date_row["match_date"] for date_row in dates]
    info["draft"] = next((dict(version) for version in versions if version["status"] == "draft"), None)
    info["published"] = next((dict(version) for version in versions if version["status"] == "published"), None)
    return info


def list_uploads(owner_id=None):
    with connect() as connection:
        if owner_id is None:
            rows = connection.execute(
                "SELECT upload_id FROM uploads ORDER BY created_at DESC, upload_id DESC"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT upload_id FROM uploads WHERE created_by = ? ORDER BY created_at DESC, upload_id DESC",
                (owner_id,),
            ).fetchall()
    return [get_upload(row["upload_id"]) for row in rows]


def load_upload_matches(upload_id, match_date=None):
    with connect() as connection:
        version = connection.execute(
            """SELECT version_id FROM assignment_versions
            WHERE upload_id = ? AND status IN ('draft', 'published')
            ORDER BY CASE status WHEN 'draft' THEN 0 ELSE 1 END LIMIT 1""",
            (upload_id,),
        ).fetchone()
        if version:
            query = "SELECT match_json FROM version_matches WHERE version_id = ?"
            parameters = [version["version_id"]]
        else:
            query = "SELECT match_json FROM matches WHERE upload_id = ?"
            parameters = [upload_id]
        if match_date is not None:
            query += " AND match_date = ?"
            parameters.append(match_date)
        query += " ORDER BY match_date, position"
        rows = connection.execute(query, parameters).fetchall()
    return [json.loads(row["match_json"]) for row in rows]


def create_assignment_draft(upload_id, date_matches, result):
    assigned_count = sum(
        isinstance(match.get("referee"), dict)
        for matches in date_matches.values()
        for match in matches
    )
    unassigned_count = sum(
        not isinstance(match.get("referee"), dict)
        for matches in date_matches.values()
        for match in matches
    )
    created_at = datetime.now(timezone.utc).isoformat()
    with connect() as connection:
        upload = connection.execute(
            "SELECT upload_id FROM uploads WHERE upload_id = ?", (upload_id,)
        ).fetchone()
        if upload is None:
            return None
        valid_dates = {
            row["match_date"] for row in connection.execute(
                "SELECT match_date FROM upload_dates WHERE upload_id = ?", (upload_id,)
            ).fetchall()
        }
        if set(date_matches) != valid_dates:
            raise ValueError("A kiosztás nem tartalmazza a feltöltés összes dátumát.")
        connection.execute(
            "UPDATE assignment_versions SET status = 'superseded' WHERE upload_id = ? AND status = 'draft'",
            (upload_id,),
        )
        cursor = connection.execute(
            """INSERT INTO assignment_versions(
                upload_id, status, created_at, success, partial,
                capacity_sufficient, total_travel_distance,
                assigned_count, unassigned_count
            ) VALUES (?, 'draft', ?, ?, ?, ?, ?, ?, ?)""",
            (
                upload_id,
                created_at,
                int(result["success"]),
                int(result["partial"]),
                int(result["capacity_sufficient"]),
                float(result["total_travel_distance"]),
                assigned_count,
                unassigned_count,
            ),
        )
        version_id = cursor.lastrowid
        for match_date, matches in date_matches.items():
            connection.executemany(
                """INSERT INTO version_matches(
                    version_id, match_date, position, match_json, unassigned
                ) VALUES (?, ?, ?, ?, ?)""",
                [
                    (
                        version_id,
                        match_date,
                        position,
                        json.dumps(match, ensure_ascii=False),
                        int(not isinstance(match.get("referee"), dict)),
                    )
                    for position, match in enumerate(matches)
                ],
            )
    return version_id


def finalize_upload(upload_id, owner_id=None):
    with connect() as connection:
        upload_query = "SELECT upload_id FROM uploads WHERE upload_id = ?"
        parameters = [upload_id]
        if owner_id is not None:
            upload_query += " AND created_by = ?"
            parameters.append(owner_id)
        upload = connection.execute(upload_query, parameters).fetchone()
        if upload is None:
            return None, "not_found"
        draft = connection.execute(
            """SELECT version_id, assigned_count FROM assignment_versions
            WHERE upload_id = ? AND status = 'draft' ORDER BY version_id DESC LIMIT 1""",
            (upload_id,),
        ).fetchone()
        if draft is None:
            return None, "no_draft"
        if draft["assigned_count"] == 0:
            return None, "no_assignments"
        connection.execute(
            "UPDATE assignment_versions SET status = 'superseded' WHERE upload_id = ? AND status = 'published'",
            (upload_id,),
        )
        connection.execute(
            "UPDATE assignment_versions SET status = 'published' WHERE version_id = ?",
            (draft["version_id"],),
        )
        connection.execute(
            "UPDATE uploads SET status = 'finalized' WHERE upload_id = ?", (upload_id,)
        )
        connection.execute(
            """UPDATE notifications SET read_at = ? WHERE upload_id = ?
            AND notification_type = 'reassignment_required' AND read_at IS NULL""",
            (datetime.now(timezone.utc).isoformat(), upload_id),
        )
    return get_upload(upload_id, owner_id), None


def delete_upload(upload_id, owner_id=None):
    with connect() as connection:
        query = "DELETE FROM uploads WHERE upload_id = ?"
        parameters = [upload_id]
        if owner_id is not None:
            query += " AND created_by = ?"
            parameters.append(owner_id)
        cursor = connection.execute(query, parameters)
    return cursor.rowcount > 0


def load_matches(match_date=None, owner_id=None):
    loaded_matches = []
    with connect() as connection:
        query = "SELECT upload_id FROM uploads"
        parameters = []
        if owner_id is not None:
            query += " WHERE created_by = ?"
            parameters.append(owner_id)
        query += " ORDER BY upload_id"
        uploads = connection.execute(query, parameters).fetchall()
        for upload in uploads:
            upload_id = upload["upload_id"]
            version = connection.execute(
                """SELECT version_id FROM assignment_versions
                WHERE upload_id = ? AND status IN ('draft', 'published')
                ORDER BY CASE status WHEN 'draft' THEN 0 ELSE 1 END
                LIMIT 1""",
                (upload_id,),
            ).fetchone()
            table = "version_matches" if version else "matches"
            id_column = "version_id" if version else "upload_id"
            match_parameters = [version["version_id"] if version else upload_id]
            condition = f"{id_column} = ?"
            if match_date is not None:
                condition += " AND match_date = ?"
                match_parameters.append(match_date)
            rows = connection.execute(
                f"SELECT match_json FROM {table} WHERE {condition} ORDER BY match_date, position",
                match_parameters,
            ).fetchall()
            loaded_matches.extend(json.loads(row["match_json"]) for row in rows)
    return loaded_matches


def load_referee_matches(referee_id):
    assigned_matches = []
    with connect() as connection:
        rows = connection.execute(
            """SELECT vm.match_json FROM version_matches vm
            JOIN assignment_versions av ON av.version_id = vm.version_id
            WHERE av.status = 'published'
            ORDER BY vm.match_date, av.upload_id, vm.position"""
        ).fetchall()
    for row in rows:
        match = json.loads(row["match_json"])
        crew = [match.get("referee"), *(match.get("assistant") or [])]
        if any(
            isinstance(referee, dict)
            and str(referee.get("id")) == str(referee_id)
            for referee in crew
        ):
            assigned_matches.append(match)
    return assigned_matches


def list_notifications(owner_id=None):
    with connect() as connection:
        if owner_id is None:
            rows = connection.execute(
                """SELECT n.*, u.created_by FROM notifications n
                JOIN uploads u ON u.upload_id = n.upload_id
                ORDER BY n.created_at DESC, n.notification_id DESC"""
            ).fetchall()
        else:
            rows = connection.execute(
                """SELECT n.*, u.created_by FROM notifications n
                JOIN uploads u ON u.upload_id = n.upload_id
                WHERE u.created_by = ?
                ORDER BY n.created_at DESC, n.notification_id DESC""",
                (owner_id,),
            ).fetchall()
    return [dict(row) for row in rows]


def mark_notification_read(notification_id, owner_id=None):
    with connect() as connection:
        if owner_id is None:
            cursor = connection.execute(
                "UPDATE notifications SET read_at = ? WHERE notification_id = ?",
                (datetime.now(timezone.utc).isoformat(), notification_id),
            )
        else:
            cursor = connection.execute(
                """UPDATE notifications SET read_at = ? WHERE notification_id = ?
                AND upload_id IN (SELECT upload_id FROM uploads WHERE created_by = ?)""",
                (datetime.now(timezone.utc).isoformat(), notification_id, owner_id),
            )
    return cursor.rowcount > 0


def create_unavailability_notifications(referee_id, referee_name, unavailable_dates):
    if not unavailable_dates:
        return 0
    created_at = datetime.now(timezone.utc).isoformat()
    inserted = 0
    placeholders = ",".join("?" for _ in unavailable_dates)
    with connect() as connection:
        rows = connection.execute(
            f"""SELECT av.upload_id, vm.match_date, vm.match_json
            FROM assignment_versions av
            JOIN version_matches vm ON vm.version_id = av.version_id
            WHERE av.status = 'published' AND vm.match_date IN ({placeholders})""",
            tuple(unavailable_dates),
        ).fetchall()
        for row in rows:
            match = json.loads(row["match_json"])
            crew = [match.get("referee"), *(match.get("assistant") or [])]
            if not any(
                isinstance(referee, dict)
                and str(referee.get("id")) == str(referee_id)
                for referee in crew
            ):
                continue
            cursor = connection.execute(
                """INSERT OR IGNORE INTO notifications(
                    upload_id, notification_type, referee_id, match_date,
                    message, created_at
                ) VALUES (?, 'reassignment_required', ?, ?, ?, ?)""",
                (
                    row["upload_id"],
                    str(referee_id),
                    row["match_date"],
                    f"{referee_name} lemondta a {row['match_date']} dátumot; a kiosztás újraküldést igényel.",
                    created_at,
                ),
            )
            inserted += cursor.rowcount
    return inserted


def migrate_legacy_matchpool():
    """Kept for compatibility; JSON pools import during database initialization."""
    return None


def add_ref_field(matchlist):
    for match in matchlist:
        match["referee"] = None


def add_assist_field(matchlist):
    for match in matchlist:
        match["assistant"] = []


def add_paired_match_field(matchlist):
    for match in matchlist:
        match["paired_match_id"] = None


def add_done_field(matchlist):
    for match in matchlist:
        match["done"] = False


def add_has_car_field(matchlist):
    for match in matchlist:
        match["has_car"] = False


def starting_diff(match1, match2):
    time1 = datetime.strptime(match1["time"], "%H:%M")
    time2 = datetime.strptime(match2["time"], "%H:%M")
    return abs(time1 - time2)


def find_paired_match(match, matchlist):
    for other_match in matchlist:
        if (
            other_match["id"] != match["id"]
            and other_match["date"] == match["date"]
            and starting_diff(match, other_match) <= timedelta(hours=3)
            and age_group_mapping[match["age_group"]] == age_group_mapping[other_match["age_group"]]
            and match["location"] == other_match["location"]
            and match["home_team"] == other_match["home_team"]
        ):
            return other_match
    return None


def create_match_pool(matchlist, created_by=None, source_filename=None):
    add_ref_field(matchlist)
    add_assist_field(matchlist)
    add_paired_match_field(matchlist)
    add_done_field(matchlist)
    add_has_car_field(matchlist)

    for match in matchlist:
        paired_match = find_paired_match(match, matchlist)
        if paired_match:
            match["paired_match_id"] = paired_match["id"]

    matches_by_date = {}
    for match in matchlist:
        match_date = str(match.get("date") or "")
        if not match_date:
            raise ValueError("Minden mérkőzéshez dátum szükséges.")
        try:
            datetime.strptime(match_date, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError("A dátum formátuma YYYY-MM-DD legyen.") from error
        matches_by_date.setdefault(match_date, []).append(match)
    if not matches_by_date:
        raise ValueError("A feltöltés nem tartalmaz mérkőzést.")

    try:
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT match_date FROM upload_dates WHERE match_date IN ({})".format(
                    ",".join("?" for _ in matches_by_date)
                ),
                tuple(matches_by_date),
            ).fetchall()
            if existing:
                occupied_dates = ", ".join(row["match_date"] for row in existing)
                raise ValueError(
                    f"Már van feltöltés erre a dátumra: {occupied_dates}. "
                    "A teljes Excel-fájlt nem mentettük el."
                )
            cursor = connection.execute(
                "INSERT INTO uploads(created_by, source_filename, status, created_at) VALUES (?, ?, 'draft', ?)",
                (created_by, source_filename, datetime.now(timezone.utc).isoformat()),
            )
            upload_id = cursor.lastrowid
            for match_date, date_matches in matches_by_date.items():
                connection.execute(
                    "INSERT INTO upload_dates(upload_id, match_date) VALUES (?, ?)",
                    (upload_id, match_date),
                )
                connection.executemany(
                    """INSERT INTO matches(
                        upload_id, match_date, position, external_id_json, match_json, unassigned
                    ) VALUES (?, ?, ?, ?, ?, 0)""",
                    [
                        (
                            upload_id,
                            match_date,
                            position,
                            json.dumps(match.get("id"), ensure_ascii=False)
                            if match.get("id") is not None else None,
                            json.dumps(match, ensure_ascii=False),
                        )
                        for position, match in enumerate(date_matches)
                    ],
                )
    except sqlite3.IntegrityError as error:
        raise ValueError(
            "Már van feltöltés az Excel egyik dátumára. A teljes fájlt nem mentettük el."
        ) from error
    return upload_id
