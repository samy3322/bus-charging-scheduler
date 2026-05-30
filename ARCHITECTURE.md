# ARCHITECTURE — Bus Charging Scheduler

> Take-home: schedule electric buses across shared charging stations on a fixed
> route, deciding **which stations each bus charges at** and **the order buses
> use each charger**, optimizing a tunable mix of soft objectives while never
> violating the hard physical rules.

This document explains the framework chosen and **why it is the right fit**, the
data model, the **full list of future changes anticipated** (and how the design
absorbs each without an engine rewrite), how to change a weight, how to add a
rule, and the assumptions made.

---

## 1. What kind of problem this is

Stripped of the story, this is a **resource-constrained scheduling problem**:

- **Jobs** = buses. Each must run from an origin endpoint to a destination
  endpoint along an ordered route.
- **Resources** = chargers. Each station is a resource with **capacity N**
  (today N = 1). A charge occupies a charger for a fixed duration.
- **Two coupled decisions:**
  1. **Charging plan** — which subset of stations (in route order) a bus charges
     at, constrained so it never exceeds its range between charges.
  2. **Sequencing** — when several buses want the same charger in overlapping
     time, who charges first and who waits.
- **Objective** = a *tunable* weighted blend of three soft goals: per-bus wait,
  per-operator fairness, and overall network time. Hard rules are inviolable.

The brief is explicit that the bar is **"sensible and defensible,"** not provably
optimal, and that the system must **scale and absorb new rules/weights/world
growth without a rewrite**. Those two facts drive every decision below.

---

## 2. Approach chosen — greedy discrete-event simulation with a pluggable, weighted decision policy

The scheduler is an **online dispatch simulation**. A single event-driven clock
advances through time; buses travel, request chargers, and charge. **Every
discretionary decision is delegated to a policy layer** that scores candidates
using the *weighted soft rules* and filters them with the *hard rules*. The
engine itself contains **no domain rule and no weight** — it only orchestrates.

```
                 ┌──────────────────────────────────────────┐
   scenario  ──► │  LOADER  → World (route, stations, buses, │
   data file     │            weights, physical constants)   │
                 └───────────────┬──────────────────────────┘
                                 │
                    ┌────────────▼─────────────┐     consults
                    │   ENGINE (generic DES)    │ ─────────────────►  HARD RULES   (feasibility filter)
                    │  event loop, charger      │ ─────────────────►  SOFT RULES   (weighted scoring)
                    │  pools, decision points   │ ─────────────────►  PLAN POLICY  (which stations)
                    └────────────┬─────────────┘     (registries)   DISPATCH POLICY (who first)
                                 │
                    per-bus timeline  +  per-station charging order
                                 │
                                 ▼
                           STREAMLIT UI (read-only render)
```

### The one decision that matters: who charges next

When a charger frees and one or more buses are waiting, the engine asks the
**dispatch policy** to rank the waiters. Each soft rule returns an *urgency*
(higher = serve sooner); the engine picks the bus with the highest **weighted
sum**, with a deterministic tiebreak:

```
choice = argmax_over_waiting_buses(
            Σ_rule  weights[rule.name] * rule.urgency(bus, context)
         )
# tiebreak: earlier arrival_time, then bus.id  → fully reproducible
```

Because the weights live in one map and are multiplied here, **changing a weight
demonstrably changes who wins, hence the schedule** — exactly the "different
weights → different defensible schedules" the brief grades on.

### Why this is the right fit

- **It matches the real operation.** A charging network is an *online* system:
  you dispatch with the information you have now, you don't re-solve an entire
  day from scratch every time a bus is late. Greedy priority dispatch is the
  industry-standard model for exactly this (CPU schedulers, job-shop dispatch,
  real EV-charging queue management).
- **It scales linearly.** Cost is `O(events × log events)` with a heap; 20 buses
  or 20,000, the shape is the same. The brief's headline requirement is *scale*,
  and "growing the world must not need a rewrite" — see §5.
- **Rules and weights are data/plugins, not engine code.** Adding a rule is
  registering one function (§7). Changing a weight is editing one number (§6).
  The engine never changes.
- **It maps 1:1 to the required outputs.** The simulation naturally produces a
  per-bus timeline and a per-station ordering — the exact two UI views asked for.
- **It is explainable and deployable.** Pure Python, no heavy solver dependency,
  installs cleanly on Streamlit Community Cloud, and every decision can be
  narrated line-by-line in the interview.

### Alternative considered — exact optimization (CP-SAT / MILP)

I considered modeling this as a constraint program (Google OR-Tools CP-SAT):
boolean `charge[bus, station]` variables, interval variables per charger with
`AddNoOverlap`, precedence constraints, and a weighted objective. It would be
**provably optimal** and constraints/objectives are pleasantly declarative
("add a rule" = "add a constraint").

I did **not** make it the primary engine because:

- **Operational reality is online, not a one-shot batch optimum.** The product
  roadmap (priority buses, time-of-day pricing, driver shifts, replanning) is a
  stream of incremental, reactive decisions — the dispatch model fits that; a
  monolithic solve does not.
- **Scaling.** CP-SAT is excellent at the stated size but a global optimum over
  thousands of buses and many resources is exponential in the worst case; a
  dispatch policy stays linear and predictable.
- **Deployment + explainability.** OR-Tools is a heavy native dependency (no
  Python 3.14 wheels at time of writing) and adds Streamlit Cloud risk, and
  defending solver internals live is harder than narrating a scoring function.

The two are **not mutually exclusive in this architecture**: because the decision
logic is isolated behind the policy interface, a CP-SAT-based `DispatchPolicy` /
offline planner could be dropped in later as an *alternative policy* for cases
that want a global optimum, without touching the engine, data model, or UI. That
is itself a point in favor of the chosen separation of concerns.

---

## 3. Data model — "a scenario IS your data structure"

The guiding principle: **the world is data, the engine is generic.** Everything
that could change about the world lives in a self-contained scenario file; the
code reads it and runs. If a field could plausibly vary tomorrow, it is data, not
a constant in code.

### 3.1 Scenario file format (one file = one fully-described situation)

```jsonc
{
  "name": "Scenario 1 — Even spacing",

  "physical": { "battery_range_km": 240, "charge_minutes": 25, "speed_kmph": 60 },

  "route": {
    "name": "BLR-KOCHI",
    "stations":    ["Bengaluru", "A", "B", "C", "D", "Kochi"],  // ordered, endpoints included
    "segments_km": [100, 120, 100, 120, 100],                   // len == stations - 1
    "chargeable":  ["A", "B", "C", "D"]                         // endpoints excluded (slow chargers, full at start)
  },

  "stations": {                                                 // capacity per station
    "A": { "chargers": 1 }, "B": { "chargers": 1 },
    "C": { "chargers": 1 }, "D": { "chargers": 1 }
  },

  "operators": ["kpn", "freshbus", "flixbus"],

  "weights": { "individual": 1.0, "operator": 1.0, "overall": 1.0 },  // per-scenario; unlisted → 1.0

  "buses": [
    { "id": "bus-BK-01", "operator": "kpn",
      "origin": "Bengaluru", "destination": "Kochi", "departure": "19:00" }
    // ...
  ]
}
```

Key modeling choices and the future they buy:

| Choice | Why | What it future-proofs |
|---|---|---|
| **Route = ordered `stations` + `segments_km`** | Geometry is data, not constants | Add a station, change a distance, change the route — all data edits |
| **`chargeable` is an explicit set** | Endpoints aren't scheduling stations | Promote/demote any node to a charging station by listing it |
| **Station has `chargers: int` (capacity N)** | Never assume "1" | "Double the chargers" = change `1`→`2`; engine uses a capacity counter |
| **Bus has `origin`/`destination` (not a `BK/KB` enum)** | Direction is *derived* from where it starts on the route | A third path / loop / partial trip needs no new direction code |
| **`operators` is a list; bus carries `operator` string** | Operators are open-set data | Add/rename/remove operators with zero code change |
| **`weights` is a name→float map** | One source of truth, generic | A *new soft rule* automatically gets a tunable weight (default 1.0) |
| **Time as integer minutes from epoch** | No float drift, deterministic ordering | Stable tiebreaks; "19:00" parsed once at load |
| **Optional fields (`priority`, `range_override_km`)** | Present but no-op by default | Priority buses / mixed fleets need only data + maybe one rule |

### 3.2 In-memory domain (dataclasses)

```python
@dataclass(frozen=True)
class PhysicalConstants:
    battery_range_km: float = 240
    charge_minutes:   int   = 25
    speed_kmph:       float = 60.0

@dataclass(frozen=True)
class Station:
    id: str
    chargers: int = 1                      # capacity N — generalises "1 charger" from day one

@dataclass(frozen=True)
class Route:
    name: str
    stations: tuple[str, ...]              # ordered, includes endpoints
    segments_km: tuple[float, ...]         # len == len(stations) - 1
    chargeable: frozenset[str]             # subset with chargers (excludes endpoints)

@dataclass(frozen=True)
class Bus:
    id: str
    operator: str
    origin: str
    destination: str
    departure_min: int                     # minutes from scenario epoch
    priority: int = 1                      # future-proof, no-op until a rule reads it
    range_override_km: float | None = None # future-proof for mixed fleets

@dataclass
class Scenario:                            # the loaded "World"
    name: str
    physical: PhysicalConstants
    route: Route
    stations: dict[str, Station]
    operators: tuple[str, ...]
    weights: dict[str, float]
    buses: list[Bus]
```

### 3.3 Output model

The scheduler emits two plain, serializable structures that drive the UI directly:

```python
@dataclass
class TimelineEvent:
    bus_id: str
    kind: str           # "DEPART" | "TRAVEL" | "ARRIVE" | "WAIT" | "CHARGE" | "FINISH"
    station: str | None
    start_min: int
    end_min: int

# per-bus:     bus_id -> list[TimelineEvent]   (ordered)
# per-station: station_id -> list[(bus_id, charge_start_min, charge_end_min)]  (charging order)
```

### 3.4 A useful consequence: feasibility is pure geometry

Charging always refills to full, and **waiting consumes time but not range**.
Therefore whether a charging plan is *valid* depends only on distances, never on
timing or contention. This cleanly **decouples the two decisions**:

- **Plan feasibility** = a pure function of (chosen station subset, segments).
  Cheap to enumerate (≤ 2⁴ subsets today) and trivially unit-testable.
- **Plan desirability + sequencing** = the time/contention layer handled by the
  simulation and policies.

For the given route a `Bengaluru→Kochi` bus (540 km, 240 km range) has exactly
three feasible **2-charge** plans — `{A,C}`, `{B,C}`, `{B,D}` — plus several
3- and 4-charge ones. The scheduler genuinely chooses among them, which is where
load-balancing across stations happens.

---

## 4. The decision layer — hard rules and soft rules

Two small registries. The engine iterates them; it never names a specific rule.

### Hard rules (feasibility — inviolable)

A hard rule answers a yes/no question and can both **filter candidate actions**
during simulation and **validate a finished schedule** (a built-in invariant
check, also exposed as a "schedule validator").

```python
class HardRule(Protocol):
    name: str
    def violations(self, schedule, world) -> list[str]: ...   # empty == ok

HARD_RULES: list[HardRule] = []           # registry
```

Day-one hard rules: **Range** (≤ battery between consecutive charges, and
start→first / last→destination), **ChargerCapacity** (≤ N buses charging at a
station at any instant), **RouteOrder** (stations visited in traversal order, no
backtracking), **ChargeDuration** (exactly `charge_minutes`).

### Soft rules (weighted scoring — tunable)

Each soft rule returns an **urgency** for serving a given bus now; the engine
combines them with the weights map.

```python
class SoftRule(Protocol):
    name: str
    def urgency(self, bus, ctx) -> float: ...   # higher == serve sooner

SOFT_RULES: list[SoftRule] = []
def soft_rule(cls):                              # registry decorator
    SOFT_RULES.append(cls()); return cls
```

Day-one soft rules:

```python
@soft_rule
class IndividualWait:        # no single bus waits too long
    name = "individual"
    def urgency(self, bus, ctx):
        return ctx.now - ctx.arrived_at[bus.id]          # longer current wait → more urgent

@soft_rule
class OperatorFairness:      # each operator's fleet runs smoothly as a group
    name = "operator"
    def urgency(self, bus, ctx):
        return ctx.operator_accumulated_wait[bus.operator]  # most-delayed operator → more urgent

@soft_rule
class OverallImpact:         # total network time stays low
    name = "overall"
    def urgency(self, bus, ctx):
        return ctx.remaining_trip_min[bus.id]            # serve buses with more trip left first
```

The engine's pick:

```python
def choose_next(waiting, ctx, weights):
    def score(bus):
        return sum(weights.get(r.name, 1.0) * r.urgency(bus, ctx) for r in SOFT_RULES)
    return max(waiting, key=lambda b: (score(b), -ctx.arrived_at[b.id], _neg(b.id)))
```

That `weights.get(r.name, 1.0)` is the whole tunability story: **every rule,
including ones added later, is automatically weight-controlled with a sane
default.**

---

## 5. Future changes anticipated — and how the design absorbs each

This is the section the brief weighs most. For each anticipated change: **what it
is**, **what you touch**, and **why the engine never changes**. The recurring
theme — *world is data, decisions are plugins, weights are a generic map* — keeps
the "chance the code breaks if the world changes tomorrow" near zero.

| # | Anticipated change | What you edit | Engine rewrite? |
|---|---|---|---|
| 1 | **Tune a weight** (e.g. operator 1.0→2.0) | one number in the scenario's `weights` map | No |
| 2 | **Double / change chargers at a station** | `stations.X.chargers` int | No — capacity counter already general |
| 3 | **Add a new station** on the route | append to `route.stations` + `segments_km`, list in `chargeable`, add to `stations` | No — plan enumeration & contention key off data |
| 4 | **Change a segment distance** | one number in `segments_km` | No — feasibility recomputed from data |
| 5 | **Add / swap / rename an operator** | `operators` list + buses' `operator` | No — operator rule groups dynamically |
| 6 | **More buses / new departure pattern** | `buses` array | No — linear-scaling sim |
| 7 | **Priority buses** | set bus `priority`; add a `priority` weight; (one small `SoftRule` reading `bus.priority`) | No — field exists, rule is a plugin |
| 8 | **Time-of-day electricity pricing** | add a cost curve to the scenario; one `SoftRule` scoring charge-start time against it | No — pure plugin + data |
| 9 | **Driver shifts / availability** | driver windows in data; one `HardRule` forbidding charges outside the window (driver modeled as another resource) | No — the resource/feasibility abstraction generalises |
| 10 | **Multiple routes sharing stations** | a `routes` map; buses gain `route_id`; stations stay **global resources keyed by id** | No — contention is keyed by station id, already route-agnostic |
| 11 | **Mixed fleet** (per-bus range) | bus `range_override_km` | No — feasibility reads the effective range |
| 12 | **Per-station charge rate / not-to-full** | optional `charge_minutes` / target override on station | No — charge duration read from effective value |
| 13 | **Variable speed / traffic** | per-segment speed or a time factor in data | No — all travel time flows through one `travel_minutes()` helper |
| 14 | **A different objective** (e.g. minimise energy cost) | one new `SoftRule` + its weight | No — registry + weights map |
| 15 | **Hold a charger for an inbound priority bus** (lookahead) | a new `DispatchPolicy` variant | No — dispatch is a pluggable policy |
| 16 | **Swap to an optimal solver** for offline planning | a CP-SAT `DispatchPolicy` / planner behind the same interface | No — engine/data/UI untouched |

The structural reasons this holds:

- **Stations are global, capacity-`N` resources keyed by id.** "1 charger" is a
  value, not an assumption baked into control flow — so 2 chargers, or stations
  shared by multiple routes, are data, not new code paths.
- **Direction is derived, not enumerated.** Core logic reads a bus's traversal
  order from `route + origin`; there is no `if direction == "BK"` to multiply
  when routes/paths are added.
- **One decision interface.** Both discretionary choices (plan, sequencing) go
  through registries. New rule ⇒ new entry; the loop is closed for modification.
- **Weights are a name-keyed map with a default.** New rules are tunable for free.

---

## 6. How to change a weight (worked example)

Weights are per-scenario data. To make operator fairness dominate (Scenario 4):

```jsonc
// scenarios/scenario_4_operator_heavy.json
"weights": { "individual": 1.0, "operator": 2.0, "overall": 1.0 }
```

That is the **only** change. No code is touched. At every charger the
`operator` urgency term is now doubled, so when KPN buses (8 of 10 in that
scenario) contend, the most-delayed operator is favored more strongly and the
per-station order visibly shifts versus the default weights. Any rule not listed
falls back to `1.0` via `weights.get(name, 1.0)`.

---

## 7. How to add a rule (worked examples)

### Add a soft rule — "priority buses"

The `priority` field already exists on `Bus` (default `1`, a no-op). Add a rule
that reads it, and give it a weight:

```python
# scheduler/rules/soft.py
@soft_rule
class PriorityBus:
    name = "priority"
    def urgency(self, bus, ctx):
        return float(bus.priority)        # higher priority → served sooner
```

```jsonc
// in any scenario that wants it
"weights": { "individual": 1.0, "operator": 1.0, "overall": 1.0, "priority": 3.0 }
```

Done. The engine discovered the rule via the registry and weighted it via the
map. **No engine edit.**

### Add a hard rule — "driver shift window"

```python
# scheduler/rules/hard.py
@hard_rule
class DriverShift:
    name = "driver_shift"
    def violations(self, schedule, world):
        bad = []
        for ev in schedule.charges():                 # (bus, station, start, end)
            win = world.driver_window(ev.bus_id)       # from data
            if not (win.start <= ev.start_min and ev.end_min <= win.end):
                bad.append(f"{ev.bus_id} charges outside driver shift at {ev.station}")
        return bad
```

The simulation consults `HARD_RULES` before committing a charge (and the same
list validates the finished schedule). A bus that would violate simply isn't
dispatched yet; the next candidate is considered. **No engine edit.**

---

## 8. Growing the world without code (quick reference)

- **Add station E between C and D:** insert `"E"` into `stations`, split the
  `C→D` segment into `C→E`/`E→D` in `segments_km`, add `"E"` to `chargeable` and
  to the `stations` capacity map. Plan enumeration now includes E automatically.
- **Two chargers at B:** `"B": { "chargers": 2 }`.
- **New operator "zingbus":** add to `operators`, tag buses with it.
- **Second route sharing A and B:** add a `routes` map and `route_id` on buses;
  station resources are already global, so contention across routes "just works."

---

## 9. Assumptions made

1. **Constant speed** (default 60 km/h, configurable); travel time =
   distance ÷ speed. With 60 km/h, 1 km = 1 minute.
2. **Charging always fills to full**, fixed 25 min (configurable per scenario;
   the model leaves room for per-station/per-bus overrides later).
3. **Endpoints (Bengaluru, Kochi) deliver a full charge and are not scheduled** —
   modeled as origins with a full battery, excluded from `chargeable`.
4. **Waiting costs time, not range.** Hence plan feasibility is pure geometry
   (independent of contention).
5. **Work-conserving chargers:** if a bus is waiting and a charger is free, it
   charges immediately — no idle holding (until a future lookahead rule says so).
6. **Online/greedy dispatch:** decisions use only information available at the
   moment (current state + already-arrived buses), not knowledge of future
   arrivals. This is the defensible real-world dispatch model; it is *not* a
   global optimum, and we say so.
7. **A bus may pass a chargeable station without charging** — it charges only at
   stations in its chosen plan.
8. **Deterministic tiebreaks** (arrival time, then bus id) ⇒ fully reproducible
   schedules for grading and demos.
9. **Minimum charge count is enforced by the range rule** (Bengaluru→Kochi needs
   ≥ 2). The scheduler may choose more charges when beneficial.
10. **All buses share battery/speed** unless a per-bus override is supplied.
11. **One scenario = one self-contained data file**, including its own weights.

---

## 10. What's intentionally NOT done, and what's next

Honest scope (the brief asks for this):

- **Greedy ≠ global optimum.** The `overall` objective is approximated per
  decision (criticality heuristic), not solved globally. *Next:* a CP-SAT
  `DispatchPolicy`/offline planner behind the same interface for cases that want
  a provable optimum, or a rolling-horizon lookahead for a middle ground.
- **No mid-trip replanning.** A bus's charging plan is fixed at departure. *Next:*
  re-run plan selection at each station using observed congestion.
- **Deterministic world.** No traffic, breakdowns, or stochastic charge times.
  *Next:* Monte-Carlo runs over a distribution, reusing the same engine.
- **One resource type (chargers).** Drivers/other resources are sketched (§5 #9)
  but not built.
- **No persistence/auth/DB.** In-memory by design, per the brief.

The architecture is built so each of these is an *addition* (a new policy, a new
rule, a data field), never a rewrite.
