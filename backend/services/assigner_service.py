import json
import random
from itertools import combinations, groupby, permutations
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
        try:
            possible_distances.append(
                sum(
                    get_distance_between_towns(origin, destination)
                    for origin, destination in zip(locations, locations[1:])
                )
            )
        except ValueError:
            continue

    if not possible_distances:
        raise ValueError("A stábhoz nem található teljes útvonal a távolságadatokban.")

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


def shift_paired_crew(matches_in_unit, crew):
    """Rotate crew roles between paired matches and return roles per match."""
    if len(matches_in_unit) < 2:
        match = matches_in_unit[0]
        return {match.get("id"): {"referee": crew["referee"], "assistants": crew["assistants"]}}

    ordered_matches = sorted(
        matches_in_unit,
        key=lambda match: match.get("age_group") != "felnőtt",
    )
    larger_match = max(
        ordered_matches,
        key=lambda match: int(match.get("required_referees", 0)),
    )
    smaller_match = next(match for match in ordered_matches if match is not larger_match)
    roles = [crew["referee"], *crew["assistants"]]
    shifted_roles = roles[1:] + roles[:1]

    if int(larger_match.get("required_referees", 0)) == int(smaller_match.get("required_referees", 0)):
        first_match, second_match = ordered_matches
        first_count = int(first_match.get("required_referees", 0))
        first_roles = roles[:first_count]
        second_roles = first_roles[1:] + first_roles[:1]
        if first_match is larger_match:
            larger_roles, smaller_roles = first_roles, second_roles
        else:
            larger_roles, smaller_roles = second_roles, first_roles
    else:
        larger_roles = roles[:int(larger_match.get("required_referees", 0))]
        smaller_roles = shifted_roles[:int(smaller_match.get("required_referees", 0))]

    return {
        larger_match.get("id"): {"referee": larger_roles[0], "assistants": larger_roles[1:]},
        smaller_match.get("id"): {"referee": smaller_roles[0], "assistants": smaller_roles[1:]},
    }


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

    required_ranks = {
        match.get("id"): CADRE_RANKS.get(match.get("required_cadre"), 0)
        for match in matches_in_unit
    }
    teams = {
        str(team).strip().casefold()
        for match in matches_in_unit
        for team in (match.get("home_team"), match.get("away_team"))
        if team
    }
    forbidden_residences = {
        str(match.get("location", "")).strip().casefold()
        for match in matches_in_unit
        if str(match.get("location", "")).strip().casefold() != "debrecen"
    }
    available = [
        referee
        for referee in refpool
        if str(referee.get("id")) not in already_assigned
        and str(referee.get("residence", "")).strip().casefold()
        not in forbidden_residences
    ]

    possible_crews = []
    for crew_members in combinations(available, required_count):
        if not any(referee.get("has_car") is True for referee in crew_members):
            continue
        if any(
            teams.intersection(
                str(team).strip().casefold()
                for team in referee.get("banned_teams", [])
            )
            for referee in crew_members
        ):
            continue

        try:
            crew_travel_distance = calculate_travel_distance(
                matches_in_unit[0].get("location", ""),
                *(referee.get("id") for referee in crew_members)
            )
        except ValueError:
            continue

        for ordered_crew in permutations(crew_members):
            crew = {"referee": ordered_crew[0], "assistants": list(ordered_crew[1:])}
            match_roles = shift_paired_crew(matches_in_unit, crew)
            if any(
                (cadre_rank := REFEREE_CADRE_RANKS.get(
                    str(match_roles[match.get("id")]["referee"].get("cadre", "")).casefold()
                )) is None
                or cadre_rank > required_ranks[match.get("id")]
                for match in matches_in_unit
            ):
                continue

            possible_crews.append({
                "referee": crew["referee"],
                "assistants": crew["assistants"],
                "travel_distance": crew_travel_distance,
            })

    return possible_crews


def assign_all_matches(save=True):
    """Find a complete, distance-preferred assignment and save it if requested."""
    global already_assigned, matches, referees

    match_list = load_matches()
    referees = load_ref_pool()
    units = get_assignment_units(match_list)

    # This assignment run starts with an unassigned pool, as required by the
    # current workflow. The search tracks reservations locally while backtracking.
    used_ids = set()
    unit_options = []
    for index, unit in enumerate(units):
        possible_crews = find_possible_crews(unit, referees, used_ids)
        if not possible_crews:
            match_ids = ", ".join(str(match.get("id")) for match in unit)
            return {
                "success": False,
                "message": f"A(z) {match_ids} meccsegységhez nincs érvényes stáb.",
            }
        unit_options.append((len(possible_crews), index))

    unit_order = [index for _, index in sorted(unit_options)]
    chosen_crews = {}

    def search(position, reserved_ids):
        if position == len(unit_order):
            return True

        unit_index = unit_order[position]
        unit = units[unit_index]
        candidates = find_possible_crews(unit, referees, reserved_ids)
        candidates.sort(
            key=lambda crew: (
                crew["travel_distance"],
                str(crew["referee"].get("id")),
                tuple(str(referee.get("id")) for referee in crew["assistants"]),
            )
        )
        randomized_candidates = []
        for _, tied_crews in groupby(
            candidates,
            key=lambda crew: crew["travel_distance"],
        ):
            tied_crews = list(tied_crews)
            random.shuffle(tied_crews)
            randomized_candidates.extend(tied_crews)
        candidates = randomized_candidates

        for crew in candidates:
            crew_ids = {
                str(crew["referee"].get("id")),
                *(str(referee.get("id")) for referee in crew["assistants"]),
            }
            if crew_ids & reserved_ids:
                continue

            chosen_crews[unit_index] = crew
            if search(position + 1, reserved_ids | crew_ids):
                return True
            del chosen_crews[unit_index]

        return False

    if not search(0, used_ids):
        return {
            "success": False,
            "message": "Nem található teljes, ütközésmentes játékvezetői kiosztás.",
        }

    assignments = []
    for unit_index, unit in enumerate(units):
        crew = chosen_crews[unit_index]
        match_roles = shift_paired_crew(unit, crew)
        match_assignments = []
        for match in unit:
            roles = match_roles[match.get("id")]
            match["referee"] = roles["referee"]
            match["assistant"] = roles["assistants"]
            match_assignments.append({
                "match_id": match.get("id"),
                "referee": roles["referee"],
                "assistants": roles["assistants"],
            })

        assignments.append({
            "match_ids": [match.get("id") for match in unit],
            "match_assignments": match_assignments,
            "travel_distance": crew["travel_distance"],
        })

    assigned_ids = [
        str(referee.get("id"))
        for crew in chosen_crews.values()
        for referee in (crew["referee"], *crew["assistants"])
    ]
    result = {
        "success": True,
        "assignments": assignments,
        "total_travel_distance": round(
            sum(assignment["travel_distance"] for assignment in assignments),
            2,
        ),
    }

    if save:
        save_matchpool(match_list)
        matches = match_list
        already_assigned.clear()
        already_assigned.extend(assigned_ids)

    return result


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
    result = assign_all_matches()
    if not result["success"]:
        print(f"A hozzárendelés sikertelen: {result['message']}")
    else:
        print(f"Sikeres hozzárendelés: {len(result['assignments'])} kiosztási egység.")
        for assignment in result["assignments"]:
            for match_assignment in assignment["match_assignments"]:
                assistants = ", ".join(
                    referee.get("name", "Ismeretlen")
                    for referee in match_assignment["assistants"]
                ) or "nincs"
                print(
                    f"Meccs {match_assignment['match_id']}: "
                    f"{match_assignment['referee'].get('name', 'Ismeretlen')}; "
                    f"asszisztens(ek): {assistants}; "
                    f"egység utazása: {assignment['travel_distance']} km"
                )
        print(f"Összesített utazási távolság: {result['total_travel_distance']} km")
        print("A hozzárendelés elmentve a match_pool.json fájlba.")


