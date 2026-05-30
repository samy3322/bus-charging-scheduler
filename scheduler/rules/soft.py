"""Soft rules — weighted scoring (the three things to optimize for).

Each returns an *urgency* in comparable units (minutes) so weights compose
sensibly. The engine multiplies each by its weight from the scenario and serves
the highest total. Add a rule here, give it a weight in the scenario file, done —
the engine never changes.
"""

from __future__ import annotations

from ..domain import Bus
from . import DecisionContext, soft_rule


@soft_rule
class IndividualWait:
    """No single bus should wait too long → the longer it has waited, the more
    urgent it is to serve now."""

    name = "individual"

    def urgency(self, bus: Bus, ctx: DecisionContext) -> float:
        return float(ctx.waited(bus))


@soft_rule
class OperatorFairness:
    """Each operator's fleet should run smoothly as a group → favour buses whose
    operator has accumulated the most waiting, balancing pain across operators."""

    name = "operator"

    def urgency(self, bus: Bus, ctx: DecisionContext) -> float:
        return float(ctx.operator_wait_total.get(bus.operator, 0))


@soft_rule
class OverallImpact:
    """Total network time should stay low → favour the bus with the most trip
    remaining, since delaying it propagates furthest downstream."""

    name = "overall"

    def urgency(self, bus: Bus, ctx: DecisionContext) -> float:
        return float(ctx.remaining_min.get(bus.id, 0))
