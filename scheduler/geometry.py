"""Pure geometry — traversal order, distances, travel time.

All travel-time math flows through ``travel_minutes`` so a future change (variable
speed, per-segment limits, traffic factors) touches one helper, not the engine.
"""

from __future__ import annotations

from .domain import Bus, Route


def traversal(route: Route, bus: Bus) -> list[str]:
    """The ordered list of stations this bus passes, origin..destination inclusive.

    Direction falls out of the index comparison — no BK/KB branching.
    """
    oi, di = route.index(bus.origin), route.index(bus.destination)
    if oi <= di:
        return list(route.stations[oi : di + 1])
    return list(reversed(route.stations[di : oi + 1]))


def chargeable_on_route(route: Route, bus: Bus) -> list[str]:
    """Chargeable stations along this bus's traversal, in the order it meets them."""
    return [s for s in traversal(route, bus) if s in route.chargeable]


def travel_minutes(route: Route, a: str, b: str, speed_kmph: float) -> int:
    """Whole minutes to drive a->b. With 60 km/h, 1 km == 1 min."""
    return round(route.distance(a, b) / speed_kmph * 60.0)
