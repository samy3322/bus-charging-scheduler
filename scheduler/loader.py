"""Load a scenario file (JSON) into the domain model.

A scenario file fully describes one situation: physics, route, charger counts,
operators, weights, and the bus departure list. Growing the world (more stations,
chargers, operators, buses) is editing this file — never the code.
"""

from __future__ import annotations

import json
from pathlib import Path

from .domain import Bus, PhysicalConstants, Route, Scenario, Station


def parse_time(value: str | int) -> int:
    """'HH:MM' (or an int already in minutes) -> minutes from midnight."""
    if isinstance(value, int):
        return value
    h, m = value.strip().split(":")
    return int(h) * 60 + int(m)


def load_scenario(path: str | Path) -> Scenario:
    data = json.loads(Path(path).read_text())

    phys = data.get("physical", {})
    physical = PhysicalConstants(
        battery_range_km=float(phys.get("battery_range_km", 240.0)),
        charge_minutes=int(phys.get("charge_minutes", 25)),
        speed_kmph=float(phys.get("speed_kmph", 60.0)),
    )

    r = data["route"]
    route = Route(
        name=r.get("name", "route"),
        stations=tuple(r["stations"]),
        segments_km=tuple(float(x) for x in r["segments_km"]),
        chargeable=frozenset(r["chargeable"]),
    )

    stations = {
        sid: Station(id=sid, chargers=int(cfg.get("chargers", 1)))
        for sid, cfg in data["stations"].items()
    }

    buses = [
        Bus(
            id=b["id"],
            operator=b["operator"],
            origin=b["origin"],
            destination=b["destination"],
            departure_min=parse_time(b["departure"]),
            priority=int(b.get("priority", 1)),
            range_override_km=(
                float(b["range_override_km"]) if b.get("range_override_km") else None
            ),
        )
        for b in data["buses"]
    ]

    scenario = Scenario(
        name=data.get("name", Path(path).stem),
        physical=physical,
        route=route,
        stations=stations,
        operators=tuple(data.get("operators", [])),
        weights={k: float(v) for k, v in data.get("weights", {}).items()},
        buses=buses,
    )
    _validate(scenario, path)
    return scenario


def _validate(scenario: Scenario, path: str | Path) -> None:
    route = scenario.route
    missing = route.chargeable - set(route.stations)
    if missing:
        raise ValueError(f"{path}: chargeable stations not on route: {sorted(missing)}")
    no_station = route.chargeable - set(scenario.stations)
    if no_station:
        raise ValueError(f"{path}: chargeable stations missing charger config: {sorted(no_station)}")
    for b in scenario.buses:
        for node in (b.origin, b.destination):
            if node not in route.stations:
                raise ValueError(f"{path}: bus {b.id} references unknown station '{node}'")
