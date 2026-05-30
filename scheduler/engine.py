"""The scheduler engine — a greedy discrete-event simulation.

A single clock advances through ARRIVE / CHARGE_END events. The engine holds no
domain rule and no weight: the two discretionary decisions are delegated out —

  * which stations a bus charges at  -> ``planner.choose_plans`` (Layer 1)
  * who charges next when a charger   -> the weighted ``SOFT_RULES`` (Layer 2)
    frees with buses waiting

Everything is integer minutes; every choice has a deterministic tiebreak, so a
scenario always produces exactly the same schedule.
"""

from __future__ import annotations

import heapq

from .domain import Bus, Scenario
from .geometry import travel_minutes
from .planner import choose_plans
from .rules import SOFT_RULES, DecisionContext
from .timeline import BusStop, ChargeSlot, ScheduleResult

# event kinds — lower number is processed first at equal times, so a charger that
# frees at time t serves an already-waiting bus before a bus arriving at the same t
_CHARGE_END = 0
_ARRIVE = 1


def schedule(scenario: Scenario) -> ScheduleResult:
    route = scenario.route
    speed = scenario.physical.speed_kmph
    charge_min = scenario.physical.charge_minutes

    plans = choose_plans(scenario)
    bus_by_id = {b.id: b for b in scenario.buses}
    stops_of = {b.id: [b.origin, *plans[b.id], b.destination] for b in scenario.buses}

    # per-station charger state
    in_use: dict[str, int] = {s: 0 for s in route.chargeable}
    waiting: dict[str, list[Bus]] = {s: [] for s in route.chargeable}

    # bookkeeping shared with the scoring context
    arrived_at: dict[str, int] = {}            # bus_id -> arrival time at current station
    operator_wait_total: dict[str, int] = {}   # operator -> realised wait so far (min)

    # outputs
    charges: list[ChargeSlot] = []
    bus_stops: dict[str, list[BusStop]] = {b.id: [] for b in scenario.buses}
    final_arrival: dict[str, int] = {}

    # event heap: (time, kind, seq, bus_id, stop_idx)
    heap: list[tuple[int, int, int, str, int]] = []
    seq = 0

    def push(time: int, kind: int, bus_id: str, idx: int) -> None:
        nonlocal seq
        heapq.heappush(heap, (time, kind, seq, bus_id, idx))
        seq += 1

    def begin_charge(bus: Bus, station: str, start: int, idx: int) -> None:
        in_use[station] += 1
        end = start + charge_min
        arrive = arrived_at[bus.id]
        wait = start - arrive
        operator_wait_total[bus.operator] = operator_wait_total.get(bus.operator, 0) + wait
        charges.append(ChargeSlot(bus.id, station, start, end))
        bus_stops[bus.id].append(BusStop(station, arrive, wait, start, end))
        push(end, _CHARGE_END, bus.id, idx)

    def choose_next(candidates: list[Bus], station: str, now: int) -> Bus:
        ctx = DecisionContext(
            now=now,
            station=station,
            scenario=scenario,
            arrived_at=arrived_at,
            operator_wait_total=operator_wait_total,
            remaining_min={
                b.id: travel_minutes(route, station, b.destination, speed)
                for b in candidates
            },
        )

        def score(bus: Bus) -> float:
            return sum(scenario.weight(r.name) * r.urgency(bus, ctx) for r in SOFT_RULES)

        # highest score wins; tiebreak: earlier arrival (waited longest), then id
        return min(candidates, key=lambda b: (-score(b), arrived_at[b.id], b.id))

    # seed: each bus departs its origin and drives to its first stop
    for bus in scenario.buses:
        stops = stops_of[bus.id]
        first = stops[1]
        push(bus.departure_min + travel_minutes(route, stops[0], first, speed),
             _ARRIVE, bus.id, 1)

    while heap:
        time, kind, _, bus_id, idx = heapq.heappop(heap)
        bus = bus_by_id[bus_id]
        stops = stops_of[bus_id]
        station = stops[idx]

        if kind == _ARRIVE:
            if idx == len(stops) - 1:          # reached destination
                final_arrival[bus_id] = time
                continue
            arrived_at[bus_id] = time          # arrived at a charging station
            if in_use[station] < scenario.chargers_at(station):
                begin_charge(bus, station, time, idx)
            else:
                waiting[station].append(bus)

        else:  # _CHARGE_END
            in_use[station] -= 1
            nxt = idx + 1                      # drive on to the next stop
            push(time + travel_minutes(route, station, stops[nxt], speed),
                 _ARRIVE, bus_id, nxt)
            if waiting[station]:               # hand the freed charger to the best waiter
                chosen = choose_next(waiting[station], station, time)
                waiting[station].remove(chosen)
                begin_charge(chosen, station, time, stops_of[chosen.id].index(station))

    station_order = {
        s: sorted([c for c in charges if c.station == s], key=lambda c: (c.start, c.bus_id))
        for s in route.chargeable
    }

    return ScheduleResult(
        scenario=scenario,
        plans=plans,
        charges=charges,
        station_order=station_order,
        final_arrival=final_arrival,
        bus_stops=bus_stops,
        bus_by_id=bus_by_id,
    )
