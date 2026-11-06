from services.database import connect
from services.referee_service import load_referees


def load_ref_pool():
    """Return selected referees that are currently active."""
    with connect() as connection:
        selected_ids = {
            row["referee_id"]
            for row in connection.execute("SELECT referee_id FROM ref_pool").fetchall()
        }

    return [
        referee for referee in load_referees()
        if referee.get("active") is True and str(referee.get("id")) in selected_ids
    ]


def load_ref_pool_for_date(match_date):
    """Return selected active referees who have not declined this date."""
    return [
        referee for referee in load_ref_pool()
        if match_date not in (referee.get("unavailable_dates") or [])
    ]


def set_ref_pool(referee_ids):
    """Replace the selected pool, ignoring IDs without active profiles."""
    if not isinstance(referee_ids, list) or not all(
        isinstance(referee_id, (str, int)) for referee_id in referee_ids
    ):
        raise ValueError("A játékvezető-azonosítókat listaként kell megadni.")

    requested_ids = {str(referee_id) for referee_id in referee_ids}
    active_referees = [
        referee for referee in load_referees()
        if referee.get("active") is True and str(referee.get("id")) in requested_ids
    ]
    with connect() as connection:
        connection.execute("DELETE FROM ref_pool")
        connection.executemany(
            "INSERT INTO ref_pool(referee_id) VALUES (?)",
            [(str(referee["id"]),) for referee in active_referees],
        )
    return active_referees
