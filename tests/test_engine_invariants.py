import glob
import os

import pytest

from scheduler import load_scenario, schedule, validate

SCENARIOS = sorted(
    glob.glob(os.path.join(os.path.dirname(__file__), "..", "scenarios", "*.json"))
)


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: os.path.basename(p))
def test_all_buses_arrive(path):
    sc = load_scenario(path)
    res = schedule(sc)
    assert set(res.final_arrival) == {b.id for b in sc.buses}


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: os.path.basename(p))
def test_no_hard_rule_violations(path):
    sc = load_scenario(path)
    res = schedule(sc)
    assert validate(res, sc) == []


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: os.path.basename(p))
def test_deterministic(path):
    sc = load_scenario(path)
    a = schedule(sc)
    b = schedule(sc)
    order_a = {s: [c.bus_id for c in a.station_order[s]] for s in a.station_order}
    order_b = {s: [c.bus_id for c in b.station_order[s]] for s in b.station_order}
    assert order_a == order_b
    assert a.final_arrival == b.final_arrival


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: os.path.basename(p))
def test_every_bus_charges_at_least_twice(path):
    # the route is 540 km on a 240 km range -> minimum 2 charges each
    sc = load_scenario(path)
    res = schedule(sc)
    for b in sc.buses:
        assert len(res.plans[b.id]) >= 2
