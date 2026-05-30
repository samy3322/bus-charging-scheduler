from scheduler.domain import Bus, Route
from scheduler.geometry import chargeable_on_route, traversal, travel_minutes

ROUTE = Route(
    name="t",
    stations=("Bengaluru", "A", "B", "C", "D", "Kochi"),
    segments_km=(100, 120, 100, 120, 100),
    chargeable=frozenset({"A", "B", "C", "D"}),
)
BK = Bus("bk", "kpn", "Bengaluru", "Kochi", 0)
KB = Bus("kb", "kpn", "Kochi", "Bengaluru", 0)


def test_positions_and_distance():
    assert ROUTE.position("Bengaluru") == 0
    assert ROUTE.position("C") == 320
    assert ROUTE.position("Kochi") == 540
    assert ROUTE.distance("A", "C") == 220
    assert ROUTE.distance("C", "A") == 220  # direction-agnostic


def test_traversal_direction():
    assert traversal(ROUTE, BK) == ["Bengaluru", "A", "B", "C", "D", "Kochi"]
    assert traversal(ROUTE, KB) == ["Kochi", "D", "C", "B", "A", "Bengaluru"]
    assert chargeable_on_route(ROUTE, BK) == ["A", "B", "C", "D"]
    assert chargeable_on_route(ROUTE, KB) == ["D", "C", "B", "A"]


def test_travel_minutes_60kmph():
    assert travel_minutes(ROUTE, "Bengaluru", "A", 60) == 100
    assert travel_minutes(ROUTE, "A", "C", 60) == 220
