import json
from datetime import datetime, timedelta
from pathlib import Path


DATA_DIR = Path(__file__).parent.parent / "data"
MATCH_POOL_FILE = DATA_DIR / "match_pool.json"

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


def _match_pool_path(match_date):
    try:
        parsed_date = datetime.strptime(match_date, "%Y-%m-%d")
    except (TypeError, ValueError) as error:
        raise ValueError("A dátum formátuma YYYY-MM-DD legyen.") from error
    return DATA_DIR / f"match_pool_{parsed_date:%Y%m%d}.json"


def _read_pool(path):
    if not path.exists():
        return {"match_pool": [], "unassigned_match_ids": []}
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    return {
        "match_pool": data.get("match_pool", data.get("matchpool", [])),
        "unassigned_match_ids": data.get("unassigned_match_ids", []),
    }


def _write_pool(path, matchlist, unassigned_match_ids):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary_file = path.with_suffix(".json.tmp")
    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(
            {
                "match_pool": matchlist,
                "unassigned_match_ids": unassigned_match_ids or [],
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")
    temporary_file.replace(path)


def save_matchpool(matchlist, unassigned_match_ids=None, match_date=None):
    """Save one date pool, or split a multi-date list into separate files."""
    if match_date is None:
        dates = sorted({str(match.get("date") or "") for match in matchlist} - {""})
        if len(dates) > 1:
            unassigned_ids = set(unassigned_match_ids or [])
            for date in dates:
                date_matches = [match for match in matchlist if str(match.get("date") or "") == date]
                date_unassigned = (
                    [match.get("id") for match in date_matches if match.get("id") in unassigned_ids]
                    if unassigned_match_ids is not None
                    else None
                )
                save_matchpool(date_matches, date_unassigned, date)
            return
        if dates:
            match_date = dates[0]

    path = _match_pool_path(match_date) if match_date else MATCH_POOL_FILE
    if unassigned_match_ids is None:
        unassigned_match_ids = _read_pool(path)["unassigned_match_ids"]
    _write_pool(path, matchlist, unassigned_match_ids)


def get_match_dates():
    """Return the dates currently present in the date pools or legacy pool."""
    pool_files = sorted(DATA_DIR.glob("match_pool_*.json"))
    if pool_files:
        matches = [match for path in pool_files for match in _read_pool(path)["match_pool"]]
    else:
        matches = _read_pool(MATCH_POOL_FILE)["match_pool"]
    return sorted({str(match.get("date")) for match in matches if match.get("date")})


def load_matches(match_date=None):
    if match_date is not None:
        path = _match_pool_path(match_date)
        if path.exists():
            return _read_pool(path)["match_pool"]
        return [
            match for match in _read_pool(MATCH_POOL_FILE)["match_pool"]
            if str(match.get("date") or "") == match_date
        ]

    pool_files = sorted(DATA_DIR.glob("match_pool_*.json"))
    if pool_files:
        return [match for path in pool_files for match in _read_pool(path)["match_pool"]]
    return _read_pool(MATCH_POOL_FILE)["match_pool"]


def migrate_legacy_matchpool():
    """Split the old all-dates file once, preserving unassigned IDs per date."""
    if not MATCH_POOL_FILE.exists():
        return

    legacy_pool = _read_pool(MATCH_POOL_FILE)
    matches = legacy_pool["match_pool"]
    dates = sorted({str(match.get("date") or "") for match in matches} - {""})
    if not dates:
        return

    unassigned_ids = set(legacy_pool["unassigned_match_ids"])
    for date in dates:
        path = _match_pool_path(date)
        if path.exists():
            continue
        date_matches = [match for match in matches if str(match.get("date") or "") == date]
        date_unassigned = [
            match.get("id") for match in date_matches
            if match.get("id") in unassigned_ids
        ]
        save_matchpool(date_matches, date_unassigned, date)
    MATCH_POOL_FILE.unlink()


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


def create_match_pool(matchlist):
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
        matches_by_date.setdefault(str(match.get("date") or ""), []).append(match)

    new_paths = set()
    for match_date, date_matches in matches_by_date.items():
        if match_date:
            path = _match_pool_path(match_date)
            new_paths.add(path)
            save_matchpool(date_matches, [], match_date)
        else:
            save_matchpool(date_matches, [])

    for old_path in DATA_DIR.glob("match_pool_*.json"):
        if old_path not in new_paths:
            old_path.unlink()
    if MATCH_POOL_FILE.exists():
        MATCH_POOL_FILE.unlink()
