from scheduler.domain import Bus, PhysicalConstants, Route, Scenario, Station
from scheduler.planner import feasible_plans

ROUTE = Route(
    name="t",
    stations=("Bengaluru", "A", "B", "C", "D", "Kochi"),
    segments_km=(100, 120, 100, 120, 100),
    chargeable=frozenset({"A", "B", "C", "D"}),
)


def _scenario(bus: Bus) -> Scenario:
    return Scenario(
        name="t",
        physical=PhysicalConstants(240, 25, 60),
        route=ROUTE,
        stations={s: Station(s, 1) for s in "ABCD"},
        operators=("kpn",),
        weights={},
        buses=[bus],
    )


def _two_charge(bus: Bus) -> set:
    plans = feasible_plans(bus, _scenario(bus))
    return {p for p in plans if len(p) == 2}


def test_bk_two_charge_plans():
    bk = Bus("bk", "kpn", "Bengaluru", "Kochi", 0)
    assert _two_charge(bk) == {("A", "C"), ("B", "C"), ("B", "D")}


def test_kb_two_charge_plans_symmetric():
    kb = Bus("kb", "kpn", "Kochi", "Bengaluru", 0)
    assert _two_charge(kb) == {("D", "B"), ("C", "B"), ("C", "A")}


def test_infeasible_pairs_rejected():
    bk = Bus("bk", "kpn", "Bengaluru", "Kochi", 0)
    plans = set(feasible_plans(bk, _scenario(bk)))
    assert ("C", "D") not in plans  # 0->C is 320 km > 240
    assert ("A", "D") not in plans  # A->D is 340 km > 240


def test_minimum_two_charges():
    # 540 km trip on 240 km range cannot be done with 0 or 1 charge
    bk = Bus("bk", "kpn", "Bengaluru", "Kochi", 0)
    plans = feasible_plans(bk, _scenario(bk))
    assert all(len(p) >= 2 for p in plans)


def test_range_override_changes_feasibility():
    # a longer-range bus can do it in a single charge (the C-split needs >= 320 km)
    bk = Bus("bk", "kpn", "Bengaluru", "Kochi", 0, range_override_km=350)
    plans = feasible_plans(bk, _scenario(bk))
    assert any(len(p) == 1 for p in plans)
