import json
from pathlib import Path
from datetime import datetime, timedelta

from services.match_service import load_matches;

MATCH_POOL_FILE = Path(__file__).parent.parent / "data" / "match_pool.json"

age_group_mapping = {
    "U-12": 1,
    "U-13": 1,
    "U-14": 1,
    "U-15": 1,
    "U-16": 1,
    "U-19": 2,
    "U-21": 2,
    "felnőtt": 2
}

def save_matchpool(matchlist):

    with open(
        MATCH_POOL_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            {
                "match_pool": matchlist
            },
            file,
            ensure_ascii=False,
            indent=2
        )


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
    for m in matchlist:
        if m["id"] != match["id"] and m["date"] == match["date"] and starting_diff(match, m) <= timedelta(hours=3) and age_group_mapping[match["age_group"]] == age_group_mapping[m["age_group"]] and match["location"] == m["location"] and match["home_team"] == m["home_team"]:
            return m
    return None

def load_matches():

    if not MATCH_POOL_FILE.exists():
        return []

    with open(
        MATCH_POOL_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    return data.get("match_pool", data.get("matchpool", []))

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
    save_matchpool(matchlist)
