"""Proves the grading criterion: *different weights -> different (defensible)
schedules*. Changing only a weight must change what the scheduler decides."""

import os

from scheduler import load_scenario, schedule, validate

CONVERGENCE = os.path.join(
    os.path.dirname(__file__), "..", "scenarios", "scenario_5_convergence.json"
)


def _station_orders(scenario):
    res = schedule(scenario)
    return {s: tuple(c.bus_id for c in res.station_order[s]) for s in res.station_order}


def test_operator_weight_changes_order():
    sc = load_scenario(CONVERGENCE)

    sc.weights = {"individual": 1.0, "operator": 0.0, "overall": 0.0}
    base = _station_orders(sc)

    sc.weights = {"individual": 1.0, "operator": 5.0, "overall": 0.0}
    heavy_operator = _station_orders(sc)

    # at least one charger's serving order must differ
    assert base != heavy_operator


def test_both_remain_valid():
    sc = load_scenario(CONVERGENCE)
    for w in ({"individual": 1.0}, {"operator": 5.0}, {"overall": 3.0}):
        sc.weights = w
        res = schedule(sc)
        assert validate(res, sc) == []
