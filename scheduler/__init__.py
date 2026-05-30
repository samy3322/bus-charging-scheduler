"""Bus charging scheduler — greedy discrete-event simulation with a pluggable,
weighted decision policy.

Public surface:
    load_scenario(path) -> Scenario
    schedule(scenario)  -> ScheduleResult   (per-bus timeline + per-station order)
    validate(result, scenario) -> list[str]  (hard-rule violations; empty == valid)
"""

from .domain import Bus, PhysicalConstants, Route, Scenario, Station
from .loader import load_scenario
from .engine import schedule
from .timeline import ScheduleResult, validate

__all__ = [
    "Bus",
    "PhysicalConstants",
    "Route",
    "Scenario",
    "Station",
    "load_scenario",
    "schedule",
    "ScheduleResult",
    "validate",
]
