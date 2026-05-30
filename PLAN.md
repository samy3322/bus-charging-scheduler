# BUILD PLAN — Bus Charging Scheduler

Working document (not a submission deliverable). The polished design lives in
`ARCHITECTURE.md`; this is the how-we-get-there, the do/avoid list, the test
plan, and the risk register.

- **Deadline:** June 2nd. Today: May 29. ~3–4 working days.
- **Stack:** Python + Streamlit, one repo, one process, in-memory.
- **Approach:** greedy discrete-event simulation + pluggable weighted policy
  (see ARCHITECTURE §2). CP-SAT documented as the considered alternative.
- **Deliverables:** hosted Streamlit link (public) + public GitHub repo with all
  code, all 5 scenarios as data files, `README.md`, `ARCHITECTURE.md`.

---

## Target repo layout

```
Exponent_energy_bus/
├── README.md                 # run locally, change a weight, add a rule
├── ARCHITECTURE.md           # design (done)
├── PLAN.md                   # this file
├── requirements.txt          # streamlit, pandas  (NO heavy solver)
├── app.py                    # Streamlit UI — thin, render-only
├── scheduler/
│   ├── __init__.py
│   ├── domain.py             # dataclasses: PhysicalConstants, Station, Route, Bus, Scenario
│   ├── loader.py             # JSON scenario file -> Scenario; parse "HH:MM" -> minutes
│   ├── geometry.py           # traversal order, cumulative distances, travel_minutes()
│   ├── planner.py            # feasible_plans() (pure geometry) + PlanPolicy
│   ├── rules/
│   │   ├── __init__.py       # HARD_RULES / SOFT_RULES registries + decorators
│   │   ├── hard.py           # Range, ChargerCapacity, RouteOrder, ChargeDuration
│   │   └── soft.py           # IndividualWait, OperatorFairness, OverallImpact
│   ├── engine.py             # discrete-event sim, charger pools, dispatch decision
│   └── timeline.py           # TimelineEvent, per-bus + per-station builders, validator
├── scenarios/
│   ├── scenario_1_even.json
│   ├── scenario_2_bunched.json
│   ├── scenario_3_asymmetric.json
│   ├── scenario_4_operator_heavy.json
│   └── scenario_5_convergence.json
└── tests/
    ├── test_geometry.py
    ├── test_feasibility.py
    ├── test_engine_invariants.py
    └── test_weight_sensitivity.py
```

---

## Phased plan (each phase ends shippable + tested)

### Phase 0 — Scaffold (30 min)
- `git init` already done. Create folder tree, empty `__init__.py`, `requirements.txt`
  (`streamlit`, `pandas`), `.gitignore` (`__pycache__`, `.venv`).
- Create a throwaway `venv`; confirm `streamlit hello` runs.
- **Done when:** repo imports cleanly, Streamlit launches.

### Phase 1 — Domain + loader (2–3 h)
- Implement `domain.py` dataclasses exactly as in ARCHITECTURE §3.2.
- Implement `loader.py`: read JSON, parse `"HH:MM"` → integer minutes, build
  `Scenario`. Validate file shape (segments length, chargeable ⊆ stations,
  operators cover buses) with clear errors.
- **Done when:** all 5 scenario files load into `Scenario` objects (write the
  data files in Phase 7, stub one now for testing).

### Phase 2 — Geometry + feasibility (2–3 h)
- `geometry.py`: `traversal(route, bus)` (station order for this bus),
  `cumulative_km`, `travel_minutes(a, b, speed)`.
- `planner.py`: `feasible_plans(bus, route, physical)` — enumerate ordered
  subsets of chargeable stations on the traversal, keep those whose max gap
  (origin→first, between, last→dest) ≤ effective range.
- **Done when:** `test_feasibility` confirms B→K yields exactly `{A,C},{B,C},{B,D}`
  as the 2-charge plans, and rejects e.g. `{C,D}`, `{A,D}`.

### Phase 3 — Rules + registries (2 h)
- `rules/__init__.py`: `HARD_RULES`, `SOFT_RULES` lists + `@hard_rule`/`@soft_rule`
  decorators.
- `hard.py`: Range, ChargerCapacity, RouteOrder, ChargeDuration as
  `violations(schedule, world)`.
- `soft.py`: IndividualWait, OperatorFairness, OverallImpact as `urgency(bus, ctx)`.
- **Done when:** registries populate on import; rules unit-callable.

### Phase 4 — Engine (1 day, the core)
- Event heap keyed `(time, seq)`; event kinds ARRIVE / CHARGE_END.
- Per station: capacity counter + waiting list. `PlanPolicy` chooses each bus's
  plan up front (default: fewest charges, tiebreak least-loaded estimate).
- On CHARGE_END (or arrival to a free charger): if waiters, `choose_next()` via
  weighted soft scores + deterministic tiebreak; consult `HARD_RULES` before
  committing a charge.
- Emit `TimelineEvent`s as the sim runs.
- **Done when:** Scenario 1 runs end-to-end; every bus reaches its destination.

### Phase 5 — Outputs + validator (3 h)
- `timeline.py`: build per-bus timeline + per-station charging order from events.
- Schedule validator = run all `HARD_RULES` over the finished schedule; assert
  zero violations (also surfaced in the UI as a green check).
- **Done when:** `test_engine_invariants` passes on all 5 scenarios (no range
  breach, no double-booked charger, route order intact).

### Phase 6 — Streamlit UI (half day)
- `app.py`: scenario dropdown → loads file → runs scheduler → renders:
  1. **Scenario view** — input as a readable table (buses, weights, route).
  2. **Per-bus timetable** — each bus: stations used, arrive/wait/charge times,
     final arrival. (pandas DataFrame.)
  3. **Per-station view** — for A/B/C/D, ordered list of (bus, start, end).
- UI is **render-only**: zero scheduling logic. Cache the run with
  `@st.cache_data` keyed on scenario name.
- **Done when:** all 5 scenarios selectable and render sensibly.

### Phase 7 — Encode all 5 scenarios (1–2 h)
- Transcribe the departure tables from the brief into the JSON format.
- Scenario 4 carries `"operator": 2.0` in its weights.
- **Done when:** files match the PDF exactly (bus ids, operators, directions,
  departures); spot-check counts (10/10, 10/10, 10/4, 10/10, 10/10).

### Phase 8 — Tests + weight-sensitivity proof (3 h)
- `test_weight_sensitivity`: run a contended scenario with `operator=1` vs
  `operator=3`; assert the per-station order differs. This *proves* the grading
  criterion "different weights → different schedules."
- **Done when:** `pytest` green.

### Phase 9 — Docs polish + deploy (half day)
- `README.md`: run locally, **how to change a weight** (point at scenario file),
  **how to add a rule** (point at registry + 6-line example). Keep it short.
- Push public repo. Deploy on Streamlit Community Cloud (point at `app.py`,
  it reads `requirements.txt`). Verify the public URL cold-loads.
- **Done when:** hosted link opens to the dropdown for a stranger; submit form.

---

## DO — positives to hold to

- **Design the data structure first.** Lock `domain.py` + the scenario JSON
  before writing engine logic. The brief grades this hardest.
- **One source of truth for weights** — the `weights` map, read only via
  `weights.get(name, 1.0)`. Never read a weight anywhere else.
- **Rules are plugins.** Every domain rule lives in a registry behind a tiny
  protocol; the engine iterates, never names one.
- **Model capacity as `int N` from day one**, even though it's 1. Use a counter,
  never a boolean "free?".
- **Derive direction** from `route + origin`; no `BK/KB` branching in core logic.
- **Stations are global resources keyed by id** so multi-route contention is free.
- **Integer minutes everywhere**, parsed once at load. Deterministic tiebreaks
  on every choice (arrival time, then bus id).
- **Separate pure geometry (feasibility) from time/contention.** Test geometry
  in isolation.
- **Validate every produced schedule** against the hard rules (invariant check) —
  catches bugs and doubles as a demo-able "validator".
- **Keep the UI render-only.** All logic in `scheduler/`.
- **Encode weights *in* the scenario file** (Scenario 4 proves it). Defaults at 1.0.
- **Commit per phase** with clear messages; keep the repo runnable at every commit.
- **Write the README's "add a rule" / "change a weight" sections last but from the
  actual code** so they're copy-paste accurate (they'll test this live).

## AVOID — negatives / pitfalls

- **No magic numbers in code** — 240, 25, 100, 60 all live in data. Grepping the
  engine for `240` should return nothing.
- **Don't bake "1 charger"** into control flow (no un-generalizable boolean gate).
- **Don't entangle plan-selection and sequencing** into one mega-function — they
  are two decisions behind two policies.
- **Don't put scheduling logic in `app.py`.** UI must stay dumb.
- **Don't use FIFO-only contention** — it ignores weights and fails the
  "different weights → different schedules" criterion. Contention *must* consult
  the scoring policy.
- **Don't forget cross-direction contention:** a shared charger merges buses from
  both directions by absolute clock time, not per-direction queues.
- **Avoid float time drift** — one unit (minutes), integers where possible,
  consistent comparison. No `datetime` arithmetic scattered around.
- **Avoid nondeterminism** — dict/set iteration order, unbroken ties. Always sort
  / tiebreak explicitly or schedules will wobble between runs.
- **Don't mismodel endpoints** — Bengaluru/Kochi are full-charge origins, not
  schedulable chargers. They must not appear in `chargeable`.
- **Don't let waiting consume range**, and don't forget charging refills to full.
- **Off-by-one in feasibility:** check origin→first-charge and last-charge→
  destination gaps, not only the between-charge gaps.
- **Don't crash on an infeasible bus** (e.g., a future scenario where range can't
  cover a gap) — surface a clear error, fail loud but graceful.
- **Don't over-engineer** — no DB, no auth, no plugin-loading-from-disk, no async.
  A plain list registry is enough. The brief says so.
- **Don't add OR-Tools** — heavy native dep, no Py3.14 wheels, Streamlit Cloud
  risk. Keep `requirements.txt` to `streamlit` + `pandas`.
- **Don't let the per-station view and per-bus view disagree** — both derive from
  the *same* event log, never recomputed independently.

---

## Test plan

| Test | Asserts |
|---|---|
| `test_geometry` | cumulative distances + travel minutes correct both directions |
| `test_feasibility` | B→K 2-charge plans == `{A,C},{B,C},{B,D}`; infeasible sets rejected; endpoints never chargeable |
| `test_engine_invariants` | for all 5 scenarios: range never exceeded, ≤ N buses per charger at any instant, route order kept, charge == 25 min |
| `test_weight_sensitivity` | a contended scenario produces a *different* per-station order under `operator=1` vs `operator=3` |
| manual (UI) | cycle all 5 scenarios; per-bus plans sensible (≥2 charges B↔K), waits reasonable, per-station order defensible |

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Greedy makes a visibly bad call in worst-case (Scenario 5) | Med | Tune plan-policy to load-balance across `{A,C}/{B,C}/{B,D}`; document it as online/greedy, defensible not optimal |
| Cross-direction contention modeled wrong | Med | Single global per-station resource keyed by id; test invariant catches double-booking |
| Nondeterministic schedules between runs | Med | Explicit tiebreaks everywhere; test re-runs equal |
| Streamlit Cloud cold-start / deps | Low | Minimal `requirements.txt`; deploy on Day 3, not Day 4 |
| Scenario data transcription error | Med | Cross-check counts + spot-check 19:00 rows against the PDF |
| Over-running time budget on engine | Med | Engine is the 1-day core; keep plan-policy simple v1, leave lookahead as documented "next" |

---

## Day mapping (May 29 → Jun 2)

- **Day 1 (May 29–30):** Phase 0–3 (scaffold, domain, loader, geometry,
  feasibility, rules).
- **Day 2 (May 30–31):** Phase 4–5 (engine + outputs + validator), one scenario
  green end-to-end.
- **Day 3 (Jun 1):** Phase 6–8 (UI, all 5 scenarios encoded, tests + weight
  sensitivity). Deploy early.
- **Day 4 (Jun 2):** Phase 9 polish (README, defensive checks), verify hosted
  link, submit form. Buffer.
