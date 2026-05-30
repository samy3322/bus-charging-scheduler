"""Charging-plan selection (Layer 1 of the scheduler).

Plan feasibility is *pure geometry*: because charging always refills to full and
waiting costs no range, whether a plan is valid depends only on distances, never
on timing or contention. That decouples this layer cleanly from the simulation.

A "plan" is the ordered tuple of stations a bus charges at (a subset of the
chargeable stations on its traversal).
"""

from __future__ import annotations

from itertools import combinations

from .domain import Bus, Route, Scenario
from .geometry import chargeable_on_route


def feasible_plans(bus: Bus, scenario: Scenario) -> list[tuple[str, ...]]:
    """All charging plans whose every leg is within the bus's range.

    Legs checked: origin -> first charge, between consecutive charges, last
    charge -> destination. (For M stations this enumerates 2^M subsets; M is small.
    For a large M this would switch to a DP/greedy enumeration — see ARCHITECTURE.)
    """
    route = scenario.route
    rng = scenario.effective_range(bus)
    options = chargeable_on_route(route, bus)
    plans: list[tuple[str, ...]] = []

    for k in range(0, len(options) + 1):
        for combo in combinations(options, k):  # combinations preserve traversal order
            if _legs_within_range(bus, route, combo, rng):
                plans.append(combo)
    return plans


def _legs_within_range(
    bus: Bus, route: Route, plan: tuple[str, ...], rng: float
) -> bool:
    stops = [bus.origin, *plan, bus.destination]
    for a, b in zip(stops, stops[1:]):
        if route.distance(a, b) > rng + 1e-9:
            return False
    return True


def choose_plans(scenario: Scenario) -> dict[str, tuple[str, ...]]:
    """Plan policy: pick one feasible plan per bus.

    Default = **fewest charges, then spread load**:
      1. fewest charges (a Bengaluru<->Kochi bus needs >= 2; never charge more
         than necessary),
      2. least-used plan so far (rotate across the feasible options so buses
         don't all dogpile the same charging stations),
      3. least summed station load, then lexicographic — for a deterministic,
         reproducible result.

    This is the tunable "which stations" knob, isolated behind one function. A
    future policy could run a predictive look-ahead over estimated queue times,
    or read the scenario weights — without touching the engine. (See ARCHITECTURE
    "what's next".)
    """
    chosen: dict[str, tuple[str, ...]] = {}
    load: dict[str, int] = {s: 0 for s in scenario.route.chargeable}
    used: dict[tuple[str, ...], int] = {}

    # assign in departure order (then id) so the spread is stable and reproducible
    for bus in sorted(scenario.buses, key=lambda b: (b.departure_min, b.id)):
        options = feasible_plans(bus, scenario)
        if not options:
            raise ValueError(
                f"bus {bus.id}: no feasible charging plan within "
                f"{scenario.effective_range(bus)} km range"
            )
        fewest = min(len(p) for p in options)
        candidates = [p for p in options if len(p) == fewest]
        best = min(
            candidates,
            key=lambda p: (used.get(p, 0), sum(load[s] for s in p), p),
        )
        chosen[bus.id] = best
        used[best] = used.get(best, 0) + 1
        for s in best:
            load[s] += 1
    return chosen
