"""Domain model — the *world is data*.

Everything that could plausibly change about the world (route, distances, charger
counts, operators, buses, weights, physical constants) is a field here, loaded
from a scenario file. No domain constant is hardcoded in the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PhysicalConstants:
    """Tunable physics. All from the scenario file; never hardcoded in logic."""

    battery_range_km: float = 240.0
    charge_minutes: int = 25
    speed_kmph: float = 60.0


@dataclass(frozen=True)
class Station:
    """A charging station. ``chargers`` is capacity N — generalises "1 charger"
    from day one, so doubling chargers is a data change, not a code change."""

    id: str
    chargers: int = 1


@dataclass(frozen=True)
class Route:
    """An ordered list of stations and the distances between them.

    ``stations`` includes the endpoints; ``segments_km[i]`` is the distance from
    ``stations[i]`` to ``stations[i+1]`` (so ``len(segments_km) == len(stations) - 1``).
    ``chargeable`` is the subset that actually has chargers (endpoints excluded).
    """

    name: str
    stations: tuple[str, ...]
    segments_km: tuple[float, ...]
    chargeable: frozenset[str]

    # cumulative distance of each station from stations[0]; derived, not stored in data
    _positions: dict[str, float] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if len(self.segments_km) != len(self.stations) - 1:
            raise ValueError(
                f"route '{self.name}': {len(self.segments_km)} segments for "
                f"{len(self.stations)} stations (expected {len(self.stations) - 1})"
            )
        pos: dict[str, float] = {self.stations[0]: 0.0}
        running = 0.0
        for i, seg in enumerate(self.segments_km):
            running += seg
            pos[self.stations[i + 1]] = running
        object.__setattr__(self, "_positions", pos)

    def position(self, station: str) -> float:
        """Cumulative km of ``station`` from stations[0]."""
        return self._positions[station]

    def distance(self, a: str, b: str) -> float:
        """Distance between two stations, direction-agnostic."""
        return abs(self._positions[a] - self._positions[b])

    def index(self, station: str) -> int:
        return self.stations.index(station)


@dataclass(frozen=True)
class Bus:
    """A bus. Direction is *derived* from origin/destination indices on the route,
    not stored as a BK/KB enum — so new routes/paths need no new direction code.

    ``priority`` and ``range_override_km`` are future-proofing fields: present but
    no-op until a rule or the planner reads them.
    """

    id: str
    operator: str
    origin: str
    destination: str
    departure_min: int
    priority: int = 1
    range_override_km: float | None = None


@dataclass
class Scenario:
    """A fully self-contained situation — one scenario file == one of these."""

    name: str
    physical: PhysicalConstants
    route: Route
    stations: dict[str, Station]
    operators: tuple[str, ...]
    weights: dict[str, float]
    buses: list[Bus]

    def weight(self, rule_name: str) -> float:
        """Single source of truth for weights. Unlisted rules default to 1.0,
        so a newly added soft rule is automatically tunable."""
        return self.weights.get(rule_name, 1.0)

    def chargers_at(self, station: str) -> int:
        return self.stations[station].chargers

    def effective_range(self, bus: Bus) -> float:
        return bus.range_override_km or self.physical.battery_range_km
