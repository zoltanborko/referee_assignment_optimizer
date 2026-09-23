import json
from pathlib import Path


DATA_DIR = Path(__file__).parent.parent / "data"
MATCHES_FILE = DATA_DIR / "matches.json"


def save_matches(matches):

    with open(
        MATCHES_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            {
                "matches": matches
            },
            file,
            ensure_ascii=False,
            indent=2
        )


def load_matches():

    if not MATCHES_FILE.exists():
        return []

    with open(
        MATCHES_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    return data.get(
        "matches",
        []
    )