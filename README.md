# Bus Charging Scheduler

Schedules electric buses across shared charging stations on a fixed route —
deciding **which stations each bus charges at** and **the order buses use each
charger** — under a tunable mix of soft objectives, never breaking the hard
physical rules.

- **Live app:** _add your Streamlit Community Cloud URL here after deploying_
- **Design & reasoning:** [`ARCHITECTURE.md`](ARCHITECTURE.md)
- **Approach:** greedy discrete-event simulation with a pluggable, weighted
  decision policy (the engine holds no rule and no weight — both are data/plugins).

---

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open the URL it prints, pick a scenario from the dropdown, and explore the three
views: **scenario input**, **per-bus timetable**, **per-station charging order**.
The sidebar has **weight sliders** so you can retune live and watch the order change.

Run the tests:

```bash
pip install pytest && python -m pytest -q
```

---

## Change a weight

Weights are per-scenario data — the single source of truth. Edit the `weights`
map in any scenario file:

```jsonc
// scenarios/scenario_4_operator_heavy.json
"weights": { "individual": 1.0, "operator": 2.0, "overall": 1.0 }
```

That's the only change. No code is touched. Any rule not listed defaults to `1.0`
(via `scenario.weight(name)`), so the system always has a sane default. You can
also drag the sliders in the app to retune without editing files.

---

## Add a rule

The engine iterates two registries and never names a specific rule. Adding one is
registering a class.

**A soft rule** (weighted scoring — ranks waiting buses at a charger). Example:
priority buses. The `priority` field already exists on `Bus`, so this is the
whole change:

```python
# scheduler/rules/soft.py
@soft_rule
class PriorityBus:
    name = "priority"
    def urgency(self, bus, ctx):
        return float(bus.priority)        # higher priority -> served sooner
```

Then give it a weight in any scenario: `"weights": { ..., "priority": 3.0 }`.
The engine discovers it via the registry and weights it via the map.

**A hard rule** (feasibility — inviolable; validates the finished schedule).
Example: driver shift windows:

```python
# scheduler/rules/hard.py
@hard_rule
class DriverShift:
    name = "driver_shift"
    def violations(self, result, scenario):
        bad = []
        for c in result.charges:                       # (bus_id, station, start, end)
            win = scenario.driver_window(c.bus_id)       # from data
            if not (win.start <= c.start and c.end <= win.end):
                bad.append(f"{c.bus_id} charges outside its driver shift")
        return bad
```

In both cases the engine loop is untouched.

---

## Grow the world (no code change)

Everything about the world lives in the scenario file:

- **Double the chargers at B:** `"B": { "chargers": 2 }`
- **Add a station E:** add it to `route.stations`, split the relevant
  `segments_km`, list it in `route.chargeable`, add it to `stations`.
- **New operator:** add it to `operators` and tag buses with it.
- **More buses / new departures:** add to the `buses` array.

See the full anticipated-change table in [`ARCHITECTURE.md`](ARCHITECTURE.md#5-future-changes-anticipated--and-how-the-design-absorbs-each).

---

## Project layout

```
app.py                 Streamlit UI (render-only)
scheduler/
  domain.py            dataclasses — the world is data
  loader.py            scenario file -> Scenario
  geometry.py          traversal, distances, travel time
  planner.py           feasible plans (pure geometry) + plan policy
  rules/
    __init__.py        registries (HARD_RULES / SOFT_RULES) + decorators
    hard.py            range, charger capacity, route order, charge duration
    soft.py            individual wait, operator fairness, overall impact
  engine.py            discrete-event simulation + dispatch decision
  timeline.py          output model + schedule validator
scenarios/             the 5 scenarios, as data files
tests/                 geometry, feasibility, engine invariants, weight sensitivity
```

## The 5 scenarios

1. **Even spacing** — baseline, buses every 15 min both ways.
2. **Bunched start** — tight 8-min cluster early, heavy early contention.
3. **Asymmetric load** — 10 one way, 4 the other.
4. **Operator-heavy** — KPN is 8 of 10 one way; `operator` weight = 2.0.
5. **Worst-case convergence** — all 20 within a 72-min window; max contention.

Every scenario produces a valid, deterministic schedule (`pytest` checks this).
