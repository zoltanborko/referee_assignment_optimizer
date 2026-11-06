"""Persistence and workflow operations for uploaded match pools."""

import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone

from services.database import connect


AGE_GROUP_MAPPING = {
    "U-12": 1,
    "U-13": 1,
    "U-14": 1,
    "U-15": 1,
    "U-16": 1,
    "U-17": 1,
    "U-18": 1,
    "U-19": 2,
    "U-21": 2,
    "felnőtt": 2,
}


def get_upload(upload_id, owner_id=None):
    """Return upload metadata and its current draft/published summaries.

    Passing ``owner_id`` limits the lookup to uploads created by that user;
    leaving it unset allows callers such as admins to view any upload.
    """
    query = """SELECT uploads.upload_id, uploads.created_by, uploads.source_filename,
    uploads.status, uploads.created_at,
    (uploads.source_file IS NOT NULL) AS has_source_file,
    users.username AS created_by_username
    FROM uploads LEFT JOIN users ON users.user_id = uploads.created_by
    WHERE uploads.upload_id = ?"""
    parameters = [upload_id]
    if owner_id is not None:
        query += " AND uploads.created_by = ?"
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
        version_ids = [version["version_id"] for version in versions]
        unused_by_version = {version_id: {} for version_id in version_ids}
        if version_ids:
            placeholders = ",".join("?" for _ in version_ids)
            unused_rows = connection.execute(
                f"""SELECT version_id, match_date, referee_id, referee_name
                FROM assignment_unused_referees
                WHERE version_id IN ({placeholders})
                ORDER BY match_date, referee_name""",
                version_ids,
            ).fetchall()
            for unused in unused_rows:
                unused_by_version[unused["version_id"]].setdefault(
                    unused["match_date"], []
                ).append({"id": unused["referee_id"], "name": unused["referee_name"]})
    info = dict(row)
    info["has_source_file"] = bool(info["has_source_file"])
    info["dates"] = [date_row["match_date"] for date_row in dates]
    version_data = []
    for version in versions:
        item = dict(version)
        item["unused_referees_by_date"] = unused_by_version[version["version_id"]]
        version_data.append(item)
    info["draft"] = next((version for version in version_data if version["status"] == "draft"), None)
    info["published"] = next((version for version in version_data if version["status"] == "published"), None)
    return info


def get_upload_source_file(upload_id):
    """Return the originally uploaded workbook bytes, or ``None`` if absent."""
    with connect() as connection:
        row = connection.execute(
            "SELECT source_file FROM uploads WHERE upload_id = ?", (upload_id,)
        ).fetchone()
    return row["source_file"] if row else None


def get_upload_referee_exclusions(upload_id):
    """Return excluded referee IDs grouped by match date."""
    with connect() as connection:
        rows = connection.execute(
            """SELECT match_date, referee_id FROM upload_referee_exclusions
            WHERE upload_id = ? ORDER BY match_date, referee_id""",
            (upload_id,),
        ).fetchall()
    exclusions = {}
    for row in rows:
        exclusions.setdefault(row["match_date"], []).append(row["referee_id"])
    return exclusions


def set_upload_referee_exclusions(upload_id, match_date, referee_ids):
    """Replace all exclusions for one upload date in a single transaction."""
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM upload_referee_exclusions WHERE upload_id = ? AND match_date = ?",
            (upload_id, match_date),
        )
        connection.executemany(
            """INSERT INTO upload_referee_exclusions(upload_id, match_date, referee_id)
            VALUES (?, ?, ?)""",
            [(upload_id, match_date, str(referee_id)) for referee_id in referee_ids],
        )
    return True


def list_uploads(owner_id=None):
    """List uploads newest first, optionally filtering to one owner."""
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
    """Load matches from the current draft, published version, or base upload.

    A draft takes precedence so senders can inspect proposed changes before
    publication; uploads without an assignment version show their imported data.
    """
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
    matches = [json.loads(row["match_json"]) for row in rows]
    for match in matches:
        location = match.get("location")
        if isinstance(location, float) and math.isnan(location):
            # Repair rows imported before unknown Hajdú-Bihar locations fell back to Debrecen.
            match["location"] = "Debrecen"
    return matches


def create_assignment_draft(upload_id, date_matches, result, unused_referees_by_date=None):
    """Save a complete date-by-date solver result as a new draft snapshot.

    Older drafts are marked superseded. Published data remains unchanged until
    ``finalize_upload`` promotes the new draft.
    """
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
        for match_date, referees in (unused_referees_by_date or {}).items():
            connection.executemany(
                """INSERT INTO assignment_unused_referees(
                    version_id, match_date, referee_id, referee_name
                ) VALUES (?, ?, ?, ?)""",
                [
                    (version_id, match_date, str(referee["id"]), referee["name"])
                    for referee in referees
                ],
            )
    return version_id


def finalize_upload(upload_id, owner_id=None):
    """Publish a draft with at least one assignment and supersede the old one."""
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
    """Delete an upload if it exists and, when supplied, belongs to the owner."""
    with connect() as connection:
        query = "DELETE FROM uploads WHERE upload_id = ?"
        parameters = [upload_id]
        if owner_id is not None:
            query += " AND created_by = ?"
            parameters.append(owner_id)
        cursor = connection.execute(query, parameters)
    return cursor.rowcount > 0


def load_matches(match_date=None, owner_id=None):
    """Load current matches across uploads, preferring each upload's draft.

    With no draft, published assignments are returned; otherwise the original
    imported match rows are used. ``match_date`` and ``owner_id`` are optional
    filters used by the assignment workflow and sender dashboard.
    """
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
    """Return only published matches whose crew contains this referee."""
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
    """List reassignment notifications, optionally limited to one sender."""
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
    """Mark a notification read, respecting an optional upload owner filter."""
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
    """Notify upload owners when a referee declines an already-published date.

    ``INSERT OR IGNORE`` plus the database uniqueness rule makes retries safe:
    saving the same unavailability again will not create duplicate notices.
    """
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


def add_ref_field(matchlist):
    for match in matchlist:
        match["referee"] = None


def add_assist_field(matchlist):
    for match in matchlist:
        match["assistant"] = []


def add_paired_match_field(matchlist):
    for match in matchlist:
        match["paired_match_id"] = None


def starting_diff(match1, match2):
    time1 = datetime.strptime(match1["time"], "%H:%M")
    time2 = datetime.strptime(match2["time"], "%H:%M")
    return abs(time1 - time2)


def find_paired_match(match, matchlist):
    """Find a same-day, same-venue game suitable for sharing a referee crew."""
    for other_match in matchlist:
        if (
            other_match["id"] != match["id"]
            and other_match["time"] != match["time"]
            and other_match["date"] == match["date"]
            and starting_diff(match, other_match) <= timedelta(hours=3)
            and AGE_GROUP_MAPPING[match["age_group"]] == AGE_GROUP_MAPPING[other_match["age_group"]]
            and match["location"] == other_match["location"]
            and match["home_team"] == other_match["home_team"]
        ):
            return other_match
    return None


def create_match_pool(matchlist, created_by=None, source_filename=None, source_file=None):
    """Validate and persist one uploaded workbook as date-separated match pools.

    A date is unique across uploads, so a workbook that overlaps any existing
    date is rejected as a whole rather than partially saved.
    """
    add_ref_field(matchlist)
    add_assist_field(matchlist)
    add_paired_match_field(matchlist)

    for match in matchlist:
        paired_match = find_paired_match(match, matchlist)
        if paired_match:
            match["paired_match_id"] = paired_match["id"]

    match_positions = {id(match): position for position, match in enumerate(matchlist)}
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
                """INSERT INTO uploads(
                    created_by, source_filename, source_file, status, created_at
                ) VALUES (?, ?, ?, 'draft', ?)""",
                (
                    created_by,
                    source_filename,
                    source_file,
                    datetime.now(timezone.utc).isoformat(),
                ),
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
                            match_positions[id(match)],
                            json.dumps(match.get("id"), ensure_ascii=False)
                            if match.get("id") is not None else None,
                            json.dumps(match, ensure_ascii=False),
                        )
                        for match in date_matches
                    ],
                )
    except sqlite3.IntegrityError as error:
        raise ValueError(
            "A feltöltés mentése adatütközés miatt nem sikerült. A teljes fájlt nem mentettük el."
        ) from error
    return upload_id
