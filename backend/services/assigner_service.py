import json
import random
from functools import lru_cache
from itertools import combinations, permutations
import sys
from pathlib import Path

# Allow running this file directly from the repository root as well as importing
# it as a module from the backend package.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.match_pool_service import (
    create_assignment_draft,
    get_upload,
    get_match_dates,
    load_matches,
    migrate_legacy_matchpool,
    save_matchpool,
)
from services.ref_pool_service import load_ref_pool, load_ref_pool_for_date


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
referees_by_id = {str(referee.get("id")): referee for referee in referees}
matches = load_matches()


def get_assigned_by_date(match_list):
    """Collect all assigned crew members in date-keyed ID sets."""
    assigned_by_date = {}
    for match in match_list:
        date = str(match.get("date") or "")
        assigned_by_date.setdefault(date, set())
        assigned = [match.get("referee"), *(match.get("assistant") or [])]
        assigned_by_date[date].update(
            str(referee.get("id"))
            for referee in assigned
            if isinstance(referee, dict) and referee.get("id") is not None
        )
    return assigned_by_date


already_assigned = get_assigned_by_date(matches)

@lru_cache(maxsize=None)
def get_distance_between_towns(origin, destination):
    """Return the road distance in km between two towns."""
    distance = DISTANCES.get(origin, {}).get(destination)
    if distance is None:
        distance = DISTANCES.get(destination, {}).get(origin)
    if distance is None:
        raise ValueError(f"Nincs távolságadat: {origin} – {destination}.")
    return float(distance)


@lru_cache(maxsize=None)
def _cached_travel_distance(match_location, participants):
    """Cache route totals by destination and residence/car combinations."""
    possible_distances = []
    for route_order in permutations(participants):
        if not route_order[0][1]:
            continue
        locations = [participant[0] for participant in route_order] + [match_location]
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


def calculate_travel_distance(match_location, *referee_ids, referee_index=None):
    """Return the shortest shared-car route distance for one to three referees."""
    if not 1 <= len(referee_ids) <= 3:
        raise ValueError("1–3 játékvezető-azonosítót kell megadni.")

    requested_ids = [str(referee_id) for referee_id in referee_ids]
    if len(set(requested_ids)) != len(requested_ids):
        raise ValueError("A játékvezető-azonosítók különbözőek legyenek.")

    referee_index = referees_by_id if referee_index is None else referee_index
    missing_ids = [ref_id for ref_id in requested_ids if ref_id not in referee_index]
    if missing_ids:
        raise ValueError(f"Nem található játékvezető-azonosító: {', '.join(missing_ids)}")

    trio = [referee_index[ref_id] for ref_id in requested_ids]
    if not any(referee.get("has_car") is True for referee in trio):
        raise ValueError("A stábban nincs autóval rendelkező játékvezető.")

    participants = tuple(sorted(
        (
            (referee.get("residence", ""), referee.get("has_car") is True)
            for referee in trio
        ),
        key=lambda participant: (str(participant[0]), participant[1]),
    ))
    return _cached_travel_distance(match_location, participants)


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


def get_unit_dates(unit):
    return {str(match.get("date") or "") for match in unit}


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


def get_match_referee_indices(matches_in_unit):
    """Return each match's referee index in an ordered crew, without building roles."""
    if len(matches_in_unit) < 2:
        return [(matches_in_unit[0], 0)]

    ordered_matches = sorted(
        matches_in_unit,
        key=lambda match: match.get("age_group") != "felnőtt",
    )
    larger_match = max(
        ordered_matches,
        key=lambda match: int(match.get("required_referees", 0)),
    )
    smaller_match = next(match for match in ordered_matches if match is not larger_match)
    larger_count = int(larger_match.get("required_referees", 0))
    smaller_count = int(smaller_match.get("required_referees", 0))

    if larger_count == smaller_count:
        first_match, second_match = ordered_matches
        first_referee_index = 0
        second_referee_index = (
            1 if int(first_match.get("required_referees", 0)) > 1 else 0
        )
        if first_match is larger_match:
            larger_index, smaller_index = first_referee_index, second_referee_index
        else:
            larger_index, smaller_index = second_referee_index, first_referee_index
    else:
        larger_index = 0
        smaller_index = 1 if smaller_count > 0 else 0

    return [
        (larger_match, larger_index),
        (smaller_match, smaller_index),
    ]


def find_possible_crews(matches_in_unit, refpool, already_assigned, referee_index=None):
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
    match_referee_indices = get_match_referee_indices(matches_in_unit)
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
    already_assigned_ids = set()
    if isinstance(already_assigned, dict):
        for date in get_unit_dates(matches_in_unit):
            already_assigned_ids.update(already_assigned.get(date, set()))
    else:
        already_assigned_ids.update(already_assigned)
    available = [
        referee
        for referee in refpool
        if str(referee.get("id")) not in already_assigned_ids
        and str(referee.get("residence", "")).strip().casefold()
        not in forbidden_residences
    ]

    random.shuffle(available)
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

        valid_crews = []
        for ordered_crew in permutations(crew_members):
            crew = {"referee": ordered_crew[0], "assistants": list(ordered_crew[1:])}
            if any(
                (cadre_rank := REFEREE_CADRE_RANKS.get(
                    str(ordered_crew[referee_index].get("cadre", "")).casefold()
                )) is None
                or cadre_rank > required_ranks[match.get("id")]
                for match, referee_index in match_referee_indices
            ):
                continue

            valid_crews.append(crew)

        if not valid_crews:
            continue

        try:
            crew_travel_distance = calculate_travel_distance(
                matches_in_unit[0].get("location", ""),
                *(referee.get("id") for referee in crew_members),
                referee_index=referee_index,
            )
        except ValueError:
            continue

        possible_crews.extend({
            **crew,
            "travel_distance": crew_travel_distance,
        } for crew in valid_crews)

    return possible_crews


def _assign_matches_for_date(match_date, save=True):
    """Find an assignment using only one date's matches and available referees."""
    match_list = load_matches(match_date)
    referees = load_ref_pool_for_date(match_date)
    referee_index = {str(referee.get("id")): referee for referee in referees}
    units = get_assignment_units(match_list)

    # This assignment run starts with an unassigned pool. The search tracks
    # reservations locally while backtracking.
    used_ids = set()
    unit_options = []
    candidates_by_unit = {}
    for index, unit in enumerate(units):
        possible_crews = find_possible_crews(unit, referees, used_ids, referee_index)
        candidates_by_distance = {}
        for crew in possible_crews:
            candidates_by_distance.setdefault(crew["travel_distance"], []).append(crew)
        randomized_candidates = []
        for distance in sorted(candidates_by_distance):
            tied_crews = candidates_by_distance[distance]
            random.shuffle(tied_crews)
            randomized_candidates.extend(tied_crews)
        candidates_by_unit[index] = randomized_candidates
        unit_options.append((len(possible_crews), index))

    unit_order = [index for _, index in sorted(unit_options)]
    chosen_crews = {}

    unit_dates = [get_unit_dates(unit) for unit in units]

    def search(position, reserved_by_date):
        if position == len(unit_order):
            return True

        unit_index = unit_order[position]
        for crew in candidates_by_unit[unit_index]:
            crew_ids = {
                str(crew["referee"].get("id")),
                *(str(referee.get("id")) for referee in crew["assistants"]),
            }
            dates = unit_dates[unit_index]
            if any(crew_ids & reserved_by_date.get(date, set()) for date in dates):
                continue

            chosen_crews[unit_index] = crew
            next_reserved = dict(reserved_by_date)
            for date in dates:
                next_reserved[date] = reserved_by_date.get(date, set()) | crew_ids
            if search(position + 1, next_reserved):
                return True
            del chosen_crews[unit_index]

        return False

    capacity_sufficient = can_assign_all_matches(match_list, referees)
    complete = (
        capacity_sufficient
        and all(count for count, _ in unit_options)
        and search(0, {})
    )
    search = None  # Break its self-reference cycle before returning.

    if not complete:
        chosen_crews.clear()
        reserved_by_date = {}
        for unit_index in unit_order:
            dates = unit_dates[unit_index]
            for crew in candidates_by_unit[unit_index]:
                crew_ids = {
                    str(crew["referee"].get("id")),
                    *(str(referee.get("id")) for referee in crew["assistants"]),
                }
                if all(
                    crew_ids.isdisjoint(reserved_by_date.get(date, set()))
                    for date in dates
                ):
                    chosen_crews[unit_index] = crew
                    for date in dates:
                        reserved_by_date.setdefault(date, set()).update(crew_ids)
                    break

    assignments = []
    for match in match_list:
        match["referee"] = None
        match["assistant"] = []

    for unit_index, unit in enumerate(units):
        if unit_index not in chosen_crews:
            continue
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
            "date": match_date,
            "match_ids": [match.get("id") for match in unit],
            "match_assignments": match_assignments,
            "travel_distance": crew["travel_distance"],
        })

    missing_matches = [
        match
        for unit_index, unit in enumerate(units)
        if unit_index not in chosen_crews
        for match in unit
    ]
    missing_match_ids = [match.get("id") for match in missing_matches]
    result = {
        "success": complete,
        "partial": bool(assignments) and not complete,
        "capacity_sufficient": capacity_sufficient,
        "date": match_date,
        "assignments": assignments,
        "missing_matches": missing_matches,
        "missing_match_ids": missing_match_ids,
        "matches": match_list,
        "total_travel_distance": round(
            sum(assignment["travel_distance"] for assignment in assignments),
            2,
        ),
    }

    if save:
        save_matchpool(match_list, missing_match_ids, match_date)

    return result


def assign_all_matches(save=True, match_date=None):
    """Assign one date, or independently process every date pool."""
    if save:
        migrate_legacy_matchpool()
    if match_date is not None:
        return _assign_matches_for_date(match_date, save)

    dates = get_match_dates()
    date_results = {
        date: _assign_matches_for_date(date, save)
        for date in dates
    }
    results = list(date_results.values())
    assignments = [
        assignment
        for result in results
        for assignment in result["assignments"]
    ]
    missing_matches = [
        match
        for result in results
        for match in result["missing_matches"]
    ]
    missing_match_ids = [
        match_id
        for result in results
        for match_id in result["missing_match_ids"]
    ]
    return {
        "success": all(result["success"] for result in results),
        "partial": any(result["partial"] for result in results),
        "capacity_sufficient": all(result["capacity_sufficient"] for result in results),
        "date_results": date_results,
        "assignments": assignments,
        "missing_matches": missing_matches,
        "missing_match_ids": missing_match_ids,
        "total_travel_distance": round(
            sum(result["total_travel_distance"] for result in results),
            2,
        ),
    }


def assign_upload(upload_id, owner_id=None):
    """Create a new draft assignment version for one uploaded workbook."""
    upload = get_upload(upload_id, owner_id)
    if upload is None:
        return None

    date_results = {}
    date_matches = {}
    for match_date in upload["dates"]:
        result = _assign_matches_for_date(match_date, save=False)
        date_results[match_date] = result
        date_matches[match_date] = result["matches"]

    results = list(date_results.values())
    summary = {
        "success": all(result["success"] for result in results),
        "partial": any(result["partial"] for result in results),
        "capacity_sufficient": all(
            result["capacity_sufficient"] for result in results
        ),
        "assignments": [
            assignment
            for result in results
            for assignment in result["assignments"]
        ],
        "missing_match_ids": [
            match_id
            for result in results
            for match_id in result["missing_match_ids"]
        ],
        "total_travel_distance": round(
            sum(result["total_travel_distance"] for result in results), 2
        ),
    }
    summary["assigned_count"] = sum(
        isinstance(match.get("referee"), dict)
        for matches_for_date in date_matches.values()
        for match in matches_for_date
    )
    summary["unassigned_count"] = sum(
        not isinstance(match.get("referee"), dict)
        for matches_for_date in date_matches.values()
        for match in matches_for_date
    )
    version_id = create_assignment_draft(upload_id, date_matches, summary)
    summary["upload_id"] = upload_id
    summary["version_id"] = version_id
    summary["date_results"] = {
        match_date: {
            key: value for key, value in result.items() if key != "matches"
        }
        for match_date, result in date_results.items()
    }
    return summary


def can_assign_all_matches(match_list=None, refpool=None):
    """Check referee and car capacity independently for every match date."""
    match_list = matches if match_list is None else match_list
    refpool = referees if refpool is None else refpool
    required_by_date = {}
    cars_by_date = {}
    ref_cars = sum(referee.get("has_car") is True for referee in refpool)

    for unit in get_assignment_units(match_list):
        required = max(int(match.get("required_referees", 0)) for match in unit)
        for date in get_unit_dates(unit):
            required_by_date[date] = required_by_date.get(date, 0) + required
            cars_by_date[date] = cars_by_date.get(date, 0) + 1

    return all(
        required <= len(refpool) and cars_by_date[date] <= ref_cars
        for date, required in required_by_date.items()
    )


def clear_all_assignments():
    """Remove assignments from every date pool."""
    migrate_legacy_matchpool()
    cleared_count = 0
    for match_date in get_match_dates():
        matches_for_date = load_matches(match_date)
        for match in matches_for_date:
            if match.get("referee") or match.get("assistant"):
                cleared_count += 1
            match["referee"] = None
            match["assistant"] = []
        save_matchpool(matches_for_date, [], match_date)
    return cleared_count


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Csak a megadott YYYY-MM-DD dátum kiosztása")
    args = parser.parse_args()

    result = assign_all_matches(match_date=args.date)
    state = "Sikeres" if result["success"] else "Részleges" if result["partial"] else "Sikertelen"
    if args.date:
        print(f"{args.date}: {state.lower()} hozzárendelés.")
    else:
        print(f"{state} hozzárendelés {len(result['date_results'])} dátumra.")
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
    if result["missing_match_ids"]:
        print("Kiosztatlan meccsek: " + ", ".join(map(str, result["missing_match_ids"])))
    if not result["capacity_sufficient"]:
        print("A teljes kiosztás a játékvezetői létszám vagy az autók száma miatt nem lehetséges.")
    print(f"Összesített utazási távolság: {result['total_travel_distance']} km")
    print("Az eredmények dátumonkénti matchpool fájlokba mentve.")


