import json
from pathlib import Path

from services.referee_service import load_referees


REF_POOL_FILE = Path(__file__).parent.parent / "data" / "ref_pool.json"


def load_ref_pool():
    if not REF_POOL_FILE.exists():
        return []

    with open(REF_POOL_FILE, "r", encoding="utf-8") as file:
        pool_data = json.load(file)

    # Keep selected IDs in ref_pool.json, but always use current master data.
    selected_referees = pool_data.get("referees")
    if selected_referees is None:
        selected_ids = {str(referee_id) for referee_id in pool_data.get("referee_ids", [])}
    else:
        selected_ids = {
            str(referee.get("id"))
            for referee in selected_referees
            if isinstance(referee, dict) and referee.get("id") is not None
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
    if not isinstance(referee_ids, list) or not all(
        isinstance(referee_id, (str, int)) for referee_id in referee_ids
    ):
        raise ValueError("A játékvezető-azonosítókat listaként kell megadni.")

    requested_ids = {str(referee_id) for referee_id in referee_ids}
    active_referees = [
        referee for referee in load_referees()
        if referee.get("active") is True and str(referee.get("id")) in requested_ids
    ]
    REF_POOL_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = REF_POOL_FILE.with_suffix(".json.tmp")
    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump({"referees": active_referees}, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary_file.replace(REF_POOL_FILE)
    return active_referees
