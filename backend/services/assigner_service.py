import json
from itertools import permutations
import random
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

CADRE_RANKS = {
    MEGYE_1: 1,
    MEGYE_2: 2,
    MEGYE_3: 3,
}
REFEREE_CADRE_RANKS = {
    "megye1": 1,
    "megye2": 2,
    "megye3": 3,
}
RANDOM_DISTANCE_SLACK_KM = 10.0

referees = load_ref_pool()
matches = load_matches()
already_assigned = [
    str(match["referee"].get("id"))
    for match in matches
    if isinstance(match.get("referee"), dict) and match["referee"].get("id") is not None
]

def get_towns_by_distance(town):
    if town not in DISTANCES:
        raise ValueError(f"Ismeretlen település: {town}")

    town_distances = DISTANCES[town]
    return sorted(
        (
            (other_town, distance)
            for other_town, distance in town_distances.items()
            if other_town != town
        ),
        key=lambda item: (item[1], item[0].casefold()),
    )


def get_distance_between_towns(origin, destination):
    """Return the road distance in km between two towns."""
    distance = DISTANCES.get(origin, {}).get(destination)
    if distance is None:
        distance = DISTANCES.get(destination, {}).get(origin)
    if distance is None:
        raise ValueError(f"Nincs távolságadat: {origin} – {destination}.")
    return float(distance)


def get_referees_in_town(town, cadre=None):
    normalized_town = str(town).strip().casefold()
    required_rank = CADRE_RANKS.get(cadre, 0)

    return [
        referee
        for referee in referees
        if str(referee.get("residence", "")).strip().casefold() == normalized_town
        and (
            cadre is None
            or REFEREE_CADRE_RANKS.get(str(referee.get("cadre", "")).casefold(), 99)
            <= required_rank
        )
    ]


def calculate_travel_distance(match_location, referee_id, assistant1_id, assistant2_id):
    """Return the shortest shared-car route distance in km for a referee trio."""
    requested_ids = [str(referee_id), str(assistant1_id), str(assistant2_id)]
    if len(set(requested_ids)) != 3:
        raise ValueError("A játékvezető és a két asszisztens azonosítója különböző legyen.")

    referees_by_id = {
        str(referee.get("id")): referee
        for referee in referees
    }
    missing_ids = [ref_id for ref_id in requested_ids if ref_id not in referees_by_id]
    if missing_ids:
        raise ValueError(f"Nem található játékvezető-azonosító: {', '.join(missing_ids)}")

    trio = [referees_by_id[ref_id] for ref_id in requested_ids]
    if not any(referee.get("has_car") is True for referee in trio):
        raise ValueError("A hármasban nincs autóval rendelkező játékvezető.")

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


def get_matches_by_cadre(required_cadre):
    return [
        match
        for match in matches
        if match.get("required_cadre") == required_cadre
    ]


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


def assign_adult_referees():
    """Assign one eligible, nearest referee to each unassigned adult match."""
    global already_assigned
    results = []

    for cadre in (MEGYE_1, MEGYE_2, MEGYE_3):
        for match in get_matches_by_cadre(cadre):
            if str(match.get("age_group", "")).strip().casefold() != "felnőtt":
                continue
            if match.get("referee"):
                continue

            match_town = str(match.get("location", "")).strip()
            towns = get_towns_by_distance(match_town)
            if match_town.casefold() == "debrecen":
                towns.insert(0, (match_town, 0.0))

            candidates = []
            for town, distance in towns:
                if town.strip().casefold() == match_town.casefold() and match_town.casefold() != "debrecen":
                    continue
                for referee in get_referees_in_town(town, cadre):
                    if str(referee.get("id")) in already_assigned:
                        continue
                    if any(
                        str(team).strip().casefold() in {
                            str(match.get("home_team", "")).strip().casefold(),
                            str(match.get("away_team", "")).strip().casefold(),
                        }
                        for team in referee.get("banned_teams", [])
                    ):
                        continue
                    candidates.append((referee, distance))

            selected = None
            selected_distance = None
            if candidates:
                closest_distance = min(distance for _, distance in candidates)
                nearby_candidates = [
                    (referee, distance)
                    for referee, distance in candidates
                    if distance <= closest_distance + RANDOM_DISTANCE_SLACK_KM
                ]
                selected, selected_distance = random.choice(nearby_candidates)

            if selected is None:
                results.append({"match_id": match.get("id"), "referee": None})
                continue

            match["referee"] = selected
            already_assigned.append(str(selected.get("id")))
            results.append({
                "match_id": match.get("id"),
                "referee": selected,
                "distance_km": selected_distance,
            })

    save_matchpool(matches)
    return results


if __name__ == "__main__":
    assignments = assign_adult_referees()
    for assignment in assignments:
        referee = assignment["referee"]
        if referee is None:
            print(f"Meccs {assignment['match_id']}: nincs megfelelő játékvezető")
        else:
            print(
                f"Meccs {assignment['match_id']}: {referee['name']} "
                f"({referee['residence']}, {assignment['distance_km']} km)"
            )

    cleared_count = clear_all_assignments()
    print(f"\nÖsszesen {cleared_count} meccs játékvezető- és asszisztens-hozzárendelése törölve.")


