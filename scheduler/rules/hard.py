"""Hard rules — feasibility, inviolable. Each validates a finished schedule and
returns a list of human-readable violations (empty == satisfied). The same list
doubles as the engine's invariant check and the UI's "schedule valid" badge.

Rules read attributes of a ``ScheduleResult`` (annotated loosely to avoid an
import cycle): ``plans``, ``charges``, ``station_order``, ``bus_by_id``.
"""

from __future__ import annotations

from ..domain import Scenario
from . import hard_rule

_EPS = 1e-9


@hard_rule
class Range:
    """A bus never exceeds its range between consecutive charges (and on the
    origin->first and last->destination legs)."""

    name = "range"

    def violations(self, result, scenario: Scenario) -> list[str]:
        out: list[str] = []
        route = scenario.route
        for bus_id, plan in result.plans.items():
            bus = result.bus_by_id[bus_id]
            rng = scenario.effective_range(bus)
            stops = [bus.origin, *plan, bus.destination]
            for a, b in zip(stops, stops[1:]):
                d = route.distance(a, b)
                if d > rng + _EPS:
                    out.append(
                        f"{bus_id}: leg {a}->{b} is {d:.0f} km > {rng:.0f} km range"
                    )
        return out


@hard_rule
class ChargerCapacity:
    """No station ever has more than its ``chargers`` buses charging at once."""

    name = "charger_capacity"

    def violations(self, result, scenario: Scenario) -> list[str]:
        out: list[str] = []
        for station, slots in result.station_order.items():
            cap = scenario.chargers_at(station)
            # sweep: a charge that ends at t frees the charger for one starting at t
            events: list[tuple[int, int]] = []
            for c in slots:
                events.append((c.start, +1))
                events.append((c.end, -1))
            events.sort(key=lambda e: (e[0], e[1]))  # -1 (free) before +1 (occupy)
            running = 0
            for _, delta in events:
                running += delta
                if running > cap:
                    out.append(
                        f"station {station}: {running} buses charging at once "
                        f"(capacity {cap})"
                    )
                    break
        return out


@hard_rule
class ChargeDuration:
    """Every charge lasts exactly ``charge_minutes``."""

    name = "charge_duration"

    def violations(self, result, scenario: Scenario) -> list[str]:
        out: list[str] = []
        want = scenario.physical.charge_minutes
        for c in result.charges:
            if c.end - c.start != want:
                out.append(
                    f"{c.bus_id} at {c.station}: charge {c.end - c.start} min "
                    f"(expected {want})"
                )
        return out


@hard_rule
class RouteOrder:
    """A bus charges at its stations in route order — no backtracking."""

    name = "route_order"

    def violations(self, result, scenario: Scenario) -> list[str]:
        out: list[str] = []
        for bus_id, plan in result.plans.items():
            charged = [c for c in result.charges if c.bus_id == bus_id]
            charged.sort(key=lambda c: c.start)
            got = tuple(c.station for c in charged)
            if got != tuple(plan):
                out.append(
                    f"{bus_id}: charged {got} but plan (route order) was {tuple(plan)}"
                )
        return out
