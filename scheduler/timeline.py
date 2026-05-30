"""Output model + schedule validation.

The simulation emits one ``ScheduleResult``. Both UI views (per-bus timetable,
per-station order) are built from the *same* charge records, so they can never
disagree. ``validate`` runs the hard-rule registry over a finished schedule.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .domain import Bus, Scenario
from .rules import HARD_RULES


@dataclass(frozen=True)
class ChargeSlot:
    bus_id: str
    station: str
    start: int  # minutes from epoch
    end: int


@dataclass(frozen=True)
class BusStop:
    """One charging stop in a bus's journey, for the per-bus timetable."""

    station: str
    arrive: int
    wait: int
    charge_start: int
    charge_end: int  # == leave


@dataclass
class ScheduleResult:
    scenario: Scenario
    plans: dict[str, tuple[str, ...]]
    charges: list[ChargeSlot]
    station_order: dict[str, list[ChargeSlot]]
    final_arrival: dict[str, int]
    bus_stops: dict[str, list[BusStop]]
    bus_by_id: dict[str, Bus] = field(default_factory=dict)

    def total_wait(self, bus_id: str) -> int:
        return sum(s.wait for s in self.bus_stops.get(bus_id, []))

    def network_total_wait(self) -> int:
        return sum(c.start - self._arrival_for(c) for c in self.charges)

    def _arrival_for(self, c: ChargeSlot) -> int:
        for s in self.bus_stops.get(c.bus_id, []):
            if s.station == c.station and s.charge_start == c.start:
                return s.arrive
        return c.start


def validate(result: ScheduleResult, scenario: Scenario | None = None) -> list[str]:
    """Run every hard rule. Empty list == schedule is valid."""
    sc = scenario or result.scenario
    violations: list[str] = []
    for rule in HARD_RULES:
        violations.extend(rule.violations(result, sc))
    return violations


def fmt_time(minutes: int) -> str:
    """Minutes-from-midnight -> 'HH:MM' (with '+Nd' when the trip crosses days)."""
    days, rem = divmod(int(minutes), 1440)
    h, m = divmod(rem, 60)
    s = f"{h:02d}:{m:02d}"
    return f"{s} +{days}d" if days else s
