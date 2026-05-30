"""Streamlit UI — render-only. Pick a scenario, see the input, see what the
scheduler decided (per-bus timetable + per-station charging order).

All logic lives in the ``scheduler`` package; this file only loads, runs, and
displays. The weight sliders are a thin extra that demonstrates the headline
feature live: drag a weight, watch the per-station order change.
"""

from __future__ import annotations

import glob
import os

import pandas as pd
import streamlit as st

from scheduler import load_scenario, schedule, validate
from scheduler.rules import SOFT_RULES
from scheduler.timeline import fmt_time

SCENARIO_DIR = os.path.join(os.path.dirname(__file__), "scenarios")

st.set_page_config(page_title="Bus Charging Scheduler", page_icon="🚌", layout="wide")


@st.cache_data
def _scenario_files() -> dict[str, str]:
    files = sorted(glob.glob(os.path.join(SCENARIO_DIR, "*.json")))
    out: dict[str, str] = {}
    for f in files:
        sc = load_scenario(f)
        out[sc.name] = f
    return out


def _direction(bus) -> str:
    return f"{bus.origin}→{bus.destination}"


# ── header + scenario picker ────────────────────────────────────────────────
st.title("🚌 Bus Charging Scheduler")

files = _scenario_files()
if not files:
    st.error(f"No scenario files found in {SCENARIO_DIR}")
    st.stop()

choice = st.selectbox("Scenario", list(files.keys()))
scenario = load_scenario(files[choice])

# ── weight sliders (default to the scenario's own weights) ──────────────────
with st.sidebar:
    st.header("Weights")
    st.caption("Tunable soft-rule weights. Defaults come from the scenario file.")
    for rule in SOFT_RULES:
        default = float(scenario.weights.get(rule.name, 1.0))
        scenario.weights[rule.name] = st.slider(
            rule.name, 0.0, 5.0, default, 0.5, key=f"w_{rule.name}_{choice}"
        )

result = schedule(scenario)
violations = validate(result, scenario)

if violations:
    st.error("Schedule INVALID — hard-rule violations:")
    for v in violations:
        st.write("• ", v)
else:
    st.success("✅ Schedule valid — all hard rules satisfied")

tab_in, tab_bus, tab_station = st.tabs(
    ["Scenario input", "Per-bus timetable", "Per-station order"]
)

# ── view 1: input ───────────────────────────────────────────────────────────
with tab_in:
    route = scenario.route
    legs = " ".join(
        f"{route.stations[i]} –{int(route.segments_km[i])}– "
        for i in range(len(route.segments_km))
    ) + route.stations[-1]
    st.markdown(f"**Route:** {legs}")
    p = scenario.physical
    st.markdown(
        f"**Range** {p.battery_range_km:.0f} km · **Charge** {p.charge_minutes} min "
        f"· **Speed** {p.speed_kmph:.0f} km/h · **Chargers/station:** "
        + ", ".join(f"{s}={scenario.chargers_at(s)}" for s in sorted(route.chargeable))
    )
    st.markdown(
        "**Active weights:** "
        + " · ".join(f"{r.name} = {scenario.weight(r.name):g}" for r in SOFT_RULES)
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Bus": b.id,
                    "Operator": b.operator,
                    "Direction": _direction(b),
                    "Departs": fmt_time(b.departure_min),
                }
                for b in scenario.buses
            ]
        ),
        width="stretch",
        hide_index=True,
    )

# ── view 2: per-bus timetable ───────────────────────────────────────────────
with tab_bus:
    summary = pd.DataFrame(
        [
            {
                "Bus": b.id,
                "Operator": b.operator,
                "Direction": _direction(b),
                "Charges at": " → ".join(result.plans[b.id]) or "—",
                "Departs": fmt_time(b.departure_min),
                "Arrives": fmt_time(result.final_arrival[b.id]),
                "Total wait (min)": result.total_wait(b.id),
            }
            for b in scenario.buses
        ]
    )
    st.dataframe(summary, width="stretch", hide_index=True)

    bus_id = st.selectbox("Inspect a bus", [b.id for b in scenario.buses])
    stops = result.bus_stops[bus_id]
    if stops:
        st.table(
            pd.DataFrame(
                [
                    {
                        "Station": s.station,
                        "Arrive": fmt_time(s.arrive),
                        "Wait (min)": s.wait,
                        "Charge start": fmt_time(s.charge_start),
                        "Leave": fmt_time(s.charge_end),
                    }
                    for s in stops
                ]
            )
        )
    st.caption(f"Arrives {fmt_time(result.final_arrival[bus_id])}")

# ── view 3: per-station charging order ──────────────────────────────────────
with tab_station:
    op_of = {b.id: b.operator for b in scenario.buses}
    arr_of = {
        (s.station, c_id): s.arrive
        for c_id in result.bus_stops
        for s in result.bus_stops[c_id]
    }
    for st_id in sorted(scenario.route.chargeable):
        slots = result.station_order[st_id]
        st.subheader(f"Station {st_id}  ·  {scenario.chargers_at(st_id)} charger(s)")
        if not slots:
            st.caption("No buses charged here.")
            continue
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Order": i + 1,
                        "Bus": c.bus_id,
                        "Operator": op_of[c.bus_id],
                        "Arrived": fmt_time(arr_of.get((st_id, c.bus_id), c.start)),
                        "Wait (min)": c.start - arr_of.get((st_id, c.bus_id), c.start),
                        "Charge start": fmt_time(c.start),
                        "Charge end": fmt_time(c.end),
                    }
                    for i, c in enumerate(slots)
                ]
            ),
            width="stretch",
            hide_index=True,
        )
