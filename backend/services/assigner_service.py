import json
from itertools import combinations, permutations
import sys
from pathlib import Path

# Allow running this file directly from the repository root as well as importing
# it as a module from the backend package.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.match_pool_service import load_matches, save_matchpool
from services.ref_pool_service import load_ref_pool


DISTANCES_FILE = Path(__file__).parent.parent / "data" / "distances.json"
with open(DISTANCES_FILE, "r", encoding="utf-8") as file:
    DISTANCES = json.load(file)

MEGYE_1 = "Megye 1"
MEGYE_2 = "Megye 2"
MEGYE_3 = "Megye 3"
MEGYE_EGYEB = "Megye egyéb"

CADRE_RANKS = {
    MEGYE_1: 1,
    MEGYE_2: 2,
    MEGYE_3: 3,
    MEGYE_EGYEB: 4,
}
REFEREE_CADRE_RANKS = {
    "megye1": 1,
    "megye2": 2,
    "megye3": 3,
    "megye_egyeb": 4,
}
referees = load_ref_pool()
matches = load_matches()
already_assigned = [
    str(match["referee"].get("id"))
    for match in matches
    if isinstance(match.get("referee"), dict) and match["referee"].get("id") is not None
]

def get_distance_between_towns(origin, destination):
    """Return the road distance in km between two towns."""
    distance = DISTANCES.get(origin, {}).get(destination)
    if distance is None:
        distance = DISTANCES.get(destination, {}).get(origin)
    if distance is None:
        raise ValueError(f"Nincs távolságadat: {origin} – {destination}.")
    return float(distance)


def calculate_travel_distance(match_location, *referee_ids):
    """Return the shortest shared-car route distance for one to three referees."""
    if not 1 <= len(referee_ids) <= 3:
        raise ValueError("1–3 játékvezető-azonosítót kell megadni.")

    requested_ids = [str(referee_id) for referee_id in referee_ids]
    if len(set(requested_ids)) != len(requested_ids):
        raise ValueError("A játékvezető-azonosítók különbözőek legyenek.")

    referees_by_id = {
        str(referee.get("id")): referee
        for referee in referees
    }
    missing_ids = [ref_id for ref_id in requested_ids if ref_id not in referees_by_id]
    if missing_ids:
        raise ValueError(f"Nem található játékvezető-azonosító: {', '.join(missing_ids)}")

    trio = [referees_by_id[ref_id] for ref_id in requested_ids]
    if not any(referee.get("has_car") is True for referee in trio):
        raise ValueError("A stábban nincs autóval rendelkező játékvezető.")

    possible_distances = []
    for route_order in permutations(trio):
        if route_order[0].get("has_car") is not True:
            continue
        locations = [
            referee.get("residence", "")
            for referee in route_order
        ] + [match_location]
        possible_distances.append(
            sum(
                get_distance_between_towns(origin, destination)
                for origin, destination in zip(locations, locations[1:])
            )
        )

    return round(min(possible_distances), 2)


def get_assignment_units(match_list):
    """Group each paired match with its partner; leave unpaired matches alone."""
    matches_by_id = {match.get("id"): match for match in match_list}
    seen_match_ids = set()
    units = []

    for match in match_list:
        match_id = match.get("id")
        if match_id in seen_match_ids:
            continue

        unit = [match]
        paired_match = matches_by_id.get(match.get("paired_match_id"))
        if paired_match is not None and paired_match is not match:
            unit.append(paired_match)

        seen_match_ids.update(member.get("id") for member in unit)
        units.append(unit)

    return units


def find_possible_crews(matches_in_unit, refpool, already_assigned):
    """Return all valid referee and assistant groups for one match or paired unit."""
    if not matches_in_unit:
        return []

    required_count = max(
        int(match.get("required_referees", 0))
        for match in matches_in_unit
    )
    if required_count < 1:
        return []

    required_ranks = [
        CADRE_RANKS.get(match.get("required_cadre"), 0)
        for match in matches_in_unit
    ]
    teams = {
        str(team).strip().casefold()
        for match in matches_in_unit
        for team in (match.get("home_team"), match.get("away_team"))
        if team
    }
    available = [
        referee
        for referee in refpool
        if str(referee.get("id")) not in already_assigned
    ]

    possible_crews = []
    for main_referee in available:
        main_rank = REFEREE_CADRE_RANKS.get(
            str(main_referee.get("cadre", "")).casefold()
        )
        if main_rank is None or not all(
            main_rank <= required_rank for required_rank in required_ranks
        ):
            continue

        other_referees = [
            referee
            for referee in available
            if referee.get("id") != main_referee.get("id")
        ]
        for assistants in combinations(other_referees, required_count - 1):
            crew = (main_referee, *assistants)
            if not any(referee.get("has_car") is True for referee in crew):
                continue
            if any(
                teams.intersection(
                    str(team).strip().casefold()
                    for team in referee.get("banned_teams", [])
                )
                for referee in crew
            ):
                continue

            possible_crews.append({
                "referee": main_referee,
                "assistants": list(assistants),
            })

    return possible_crews


def can_assign_all_matches():
    """Return whether the referee pool can cover all matches, counting each pair once."""
    matches_by_id = {match.get("id"): match for match in matches}
    counted_pairs = set()
    required_count = 0
    required_cars = 0
    ref_cars = 0

    for match in matches:
        paired_id = match.get("paired_match_id")
        required = int(match.get("required_referees", 0))

        if paired_id is None:
            required_count += required
            required_cars += 1
            continue

        pair = frozenset((match.get("id"), paired_id))
        if pair in counted_pairs:
            continue
        counted_pairs.add(pair)
        required_cars += 1

        paired_match = matches_by_id.get(paired_id)
        if paired_match:
            required = max(required, int(paired_match.get("required_referees", 0)))
        required_count += required

    for referee in referees:
        if referee.get("has_car") is True:
            ref_cars += 1

    return required_count <= len(referees) and required_cars <= ref_cars


def clear_all_assignments():
    """Remove the referee and all assistants from every match and save the pool."""
    global already_assigned
    matches = load_matches()
    cleared_count = 0

    for match in matches:
        if match.get("referee") or match.get("assistant"):
            cleared_count += 1
        match["referee"] = None
        match["assistant"] = []

    save_matchpool(matches)
    already_assigned.clear()
    return cleared_count


if __name__ == "__main__":
    assignment_units = get_assignment_units(matches)
    print(f"Meccsek: {len(matches)}; kiosztási egységek: {len(assignment_units)}")
    sample_unit = next(
        (
            unit
            for unit in assignment_units
            if max(int(match.get("required_referees", 0)) for match in unit) > 1
        ),
        None,
    )
    if sample_unit is None:
        print("Nincs olyan meccs, amelyhez több játékvezető szükséges.")
    else:
        crews = find_possible_crews(sample_unit, referees, already_assigned)
        match_ids = ", ".join(str(match.get("id")) for match in sample_unit)
        print(f"Tesztelt meccs(ek): {match_ids}")
        print(f"Lehetséges stábok száma: {len(crews)}")

        for crew in crews[:10]:
            assistants = ", ".join(
                referee.get("name", "Ismeretlen")
                for referee in crew["assistants"]
            )
            print(
                f"Játékvezető: {crew['referee'].get('name', 'Ismeretlen')}; "
                f"asszisztens(ek): {assistants}"
            )


