"""Rule registries — the only place the scheduler's "brain" lives.

Two tiny registries the engine iterates over; the engine never names a specific
rule. Adding a rule == registering one class. Tuning it == one number in the
scenario's ``weights`` map.

    HARD_RULES : feasibility, inviolable. validate a finished schedule.
    SOFT_RULES : weighted scoring. rank waiting buses at a charger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..domain import Bus, Scenario


@dataclass
class DecisionContext:
    """Everything a soft rule needs to score a waiting bus at a charger, computed
    by the engine at the moment a charger frees. All times are integer minutes."""

    now: int
    station: str
    scenario: Scenario
    arrived_at: dict[str, int]            # bus_id -> when it started waiting here
    operator_wait_total: dict[str, int]   # operator -> accumulated wait so far (min)
    remaining_min: dict[str, int]         # bus_id -> travel minutes left to destination

    def waited(self, bus: Bus) -> int:
        return self.now - self.arrived_at[bus.id]


@runtime_checkable
class SoftRule(Protocol):
    name: str

    def urgency(self, bus: Bus, ctx: DecisionContext) -> float:
        """Higher == this bus should be served sooner."""
        ...


@runtime_checkable
class HardRule(Protocol):
    name: str

    def violations(self, result: "object", scenario: Scenario) -> list[str]:
        """Empty list == satisfied. (``result`` is a ScheduleResult.)"""
        ...


SOFT_RULES: list[SoftRule] = []
HARD_RULES: list[HardRule] = []


def soft_rule(cls):
    """Register a soft (scoring) rule. Usage: ``@soft_rule`` above the class."""
    SOFT_RULES.append(cls())
    return cls


def hard_rule(cls):
    """Register a hard (feasibility) rule. Usage: ``@hard_rule`` above the class."""
    HARD_RULES.append(cls())
    return cls


# importing the rule modules registers their classes via the decorators
from . import hard as _hard  # noqa: E402,F401
from . import soft as _soft  # noqa: E402,F401
