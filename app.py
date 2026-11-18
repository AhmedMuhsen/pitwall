"""PitWall Streamlit app: one driver's real pit strategy against a few alternatives.

Run with `uv run streamlit run app.py`. Only displays results; every number
comes from pitwall.comparison.
"""
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from pitwall.comparison import (TRAIN_YEARS, comparable_races, compare_driver, cumulative_gap, driver_choices,
                                fit_inputs, gap_ranges, load_dataset, verdict)

DATASET_PATH = Path(__file__).parent / "data" / "processed" / "lap_dataset.parquet"
BASELINE = "actual"
COLOURS = {"faster in every scenario": "#2e7d32", "depends on assumptions": "#8a8a8a",
           "slower in every scenario": "#c62828"}
VERDICT_COLOURS = {"clearly_faster": "#1f6fb2", "maybe_faster": "#e0a100",
                   "baseline_best": "#2e7d32", "baseline_best_everywhere": "#2e7d32"}


@st.cache_resource
def load():
    """Dataset rows and the fitted inputs, built once per server (about 2 s)."""
    rows = load_dataset(DATASET_PATH)
    return rows, fit_inputs(rows, TRAIN_YEARS)


def plain(strategy: dict) -> str:
    """'2 stops: Medium → Hard → Hard, laps 23 & 46' for a strategy dict."""
    ages = strategy.get("start_ages", [0] * len(strategy["compounds"]))
    stints = [c.title() + (" (used)" if age else "") for c, age in zip(strategy["compounds"], ages)]
    stops = [str(p) for p in strategy["pit_laps"]]
    laps = stops[0] if len(stops) == 1 else ", ".join(stops[:-1]) + " & " + stops[-1]
    count = len(stops)
    return f"{count} stop{'s' if count != 1 else ''}: {' → '.join(stints)}, lap{'s' if count != 1 else ''} {laps}"


def race_clock(seconds: float) -> str:
    """5531.2 -> '1:32:11.2'."""
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours}:{minutes:02d}:{secs:04.1f}"


def verdict_box(colour: str, headline: str, body: str) -> None:
    st.markdown(
        f"<div style='border-left: 6px solid {colour}; background: {colour}1f; padding: 0.9rem 1.2rem; "
        f"border-radius: 0.4rem; margin: 0.4rem 0 1.2rem 0'>"
        f"<div style='font-size: 1.35rem; font-weight: 600'>{headline}</div>"
        f"<div style='margin-top: 0.3rem'>{body}</div></div>",
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="PitWall", layout="wide")
st.title("PitWall")
st.markdown("##### What if a driver had pitted differently?")
st.caption(f"Estimates from a lap-time model fitted on {TRAIN_YEARS[0]}–{TRAIN_YEARS[-1]} races "
           "(OpenF1 timing data). A learning project, not affiliated with Formula 1, the FIA or FOM.")

try:
    rows, inputs = load()
except FileNotFoundError:
    st.error(f"Dataset not found at {DATASET_PATH}. Build it first: "
             "`uv run python scripts/fetch_races.py` then `uv run python scripts/build_dataset.py`.")
    st.stop()

races = {f"{circuit} {year}": (year, circuit) for year, circuit in comparable_races(rows)}
year, circuit = races[st.sidebar.selectbox("Race", list(races))]
st.sidebar.caption("Races without a safety car only: the simulator has none, so real times wouldn't compare.")
drivers = driver_choices(rows, circuit, year)
if not drivers:
    st.error(f"No driver at {circuit} {year} ran every lap with a time, so there is nothing to compare.")
    st.stop()
cars = {f"Car #{d}": d for d in drivers}
driver = cars[st.sidebar.selectbox("Car", list(cars))]
st.sidebar.caption("Cars that finished on the lead lap with a time on every lap.")

try:
    result = compare_driver(rows, inputs, circuit, year, driver)
except ValueError as e:
    st.error(f"Can't compare car #{driver} at {circuit} {year}: {e}")
    st.stop()

strategies = result["strategies"]
names = {name: plain(s) for name, s in strategies.items()}
ranges = gap_ranges(result["sensitivity"], BASELINE)
answer = verdict(ranges)
settings = result["settings"]

# --- Who, what they ran, and the answer -------------------------------------------------------
st.subheader(f"Car #{driver} · {circuit} {year}")
st.markdown(f"**Real strategy:** {names[BASELINE]}")
if year not in TRAIN_YEARS:
    st.caption(f"{year} races were never used to fit the model: this race is out-of-sample.")

r = answer["range"]
# The model only knows tyre age and fuel, so it always prefers evenly split stints. Say so next to
# every "faster" answer: it is what the model prefers, not proof the team got it wrong.
blind_spot = ("The model can't see why teams pit when they do (undercuts, traffic, tyre allocation, "
              "tyres suddenly dropping off), so it tends to prefer evenly split stints. "
              "Read this as what the model prefers, not as a mistake by the team.")
if answer["kind"] == "clearly_faster":
    verdict_box(VERDICT_COLOURS["clearly_faster"],
                f"The model prefers a different strategy, by about {-r['gap']:.0f} s.",
                f"<b>{names[answer['strategy']]}</b>: {-r['gap']:.1f} s quicker at the best estimate, and still "
                f"{-r['max_gap']:.1f} to {-r['min_gap']:.1f} s quicker across the pit-loss and tyre-wear ranges "
                f"tested.<br><span style='opacity: 0.8'>{blind_spot}</span>")
elif answer["kind"] == "maybe_faster":
    worst = (f"up to {r['max_gap']:.1f} s slower" if r["max_gap"] >= 0.05 else "level with the real strategy")
    verdict_box(VERDICT_COLOURS["maybe_faster"], "Too close to call under the model.",
                f"Closest: <b>{names[answer['strategy']]}</b>, {-r['gap']:.1f} s quicker at the best estimate, but "
                f"{worst} if pit loss or tyre wear differ from the estimates.")
elif answer["kind"] == "baseline_best":
    verdict_box(VERDICT_COLOURS["baseline_best"], "The model agrees with the real strategy.",
                "At the best estimate it was the quickest of those compared, though some alternatives could "
                "beat it if pit loss or tyre wear differ from the estimates.")
else:
    verdict_box(VERDICT_COLOURS["baseline_best_everywhere"], "The model agrees with the real strategy.",
                "It beat every alternative across the pit-loss and tyre-wear ranges tested.")

# --- The main chart: each alternative's gap with its range -----------------------------------
st.markdown("#### Time compared with the real strategy")
chart_data = pd.DataFrame([{**g, "label": names[g["strategy"]] + ("  ⚠" if g["flagged"] else "")}
                           for g in ranges if g["confidence"] != "baseline"])
order = chart_data["label"].tolist()
y = alt.Y("label:N", sort=order, title=None, axis=alt.Axis(labelLimit=420, labelFontSize=13))
colour = alt.Color("confidence:N", title=None, legend=alt.Legend(orient="bottom", labelFontSize=12),
                   scale=alt.Scale(domain=list(COLOURS), range=list(COLOURS.values())))
tooltip = [alt.Tooltip("label:N", title="Strategy"), alt.Tooltip("gap:Q", title="Best estimate (s)", format="+.1f"),
           alt.Tooltip("min_gap:Q", title="Best case (s)", format="+.1f"),
           alt.Tooltip("max_gap:Q", title="Worst case (s)", format="+.1f")]
base = alt.Chart(chart_data).encode(y=y)
span = base.mark_rule(strokeWidth=6, opacity=0.35, strokeCap="round").encode(
    x=alt.X("min_gap:Q", title="seconds   ← faster than the real strategy  |  slower →"), x2="max_gap:Q",
    color=colour)
dot = base.mark_circle(size=220, opacity=1).encode(x="gap:Q", color=colour, tooltip=tooltip)
value = base.mark_text(dy=-15, fontSize=12, fontWeight="bold").encode(
    x="gap:Q", text=alt.Text("gap:Q", format="+.1f"), color=colour)
zero = alt.Chart(pd.DataFrame({"x": [0.0], "text": ["real strategy"]}))
zero_line = zero.mark_rule(strokeDash=[5, 4], color="gray").encode(x="x:Q")
zero_text = zero.mark_text(dy=-8, color="gray", fontSize=11, baseline="bottom").encode(
    x="x:Q", y=alt.value(0), text="text:N")
st.altair_chart((span + dot + value + zero_line + zero_text).properties(height=70 * len(chart_data) + 60),
                width="stretch")
st.caption("Dot = best estimate. Bar = range if pit loss (25th–75th percentile here) or tyre wear "
           f"(±{inputs['wear_range']:.3f} s per lap of tyre age) are off. "
           "Green: faster under every assumption. Red: slower under every assumption. "
           "Grey: depends on the assumptions. ⚠ = runs tyres older than any seen at this circuit, "
           "so that estimate is an extrapolation and never counts as faster in the verdict.")

# --- Trust and where the time goes ----------------------------------------------------------
left, right = st.columns([1, 2], gap="large")
with left:
    with st.container(border=True):
        st.markdown("**How much to trust this**")
        st.metric("Real race time", race_clock(result["actual_time"]))
        st.metric("Model, same strategy", race_clock(result["simulated_actual"]),
                  delta=f"{result['model_error']:+.1f} s vs real", delta_color="off")
        st.caption("Across safety-car-free races the model's race total was off by about 12 s on average. "
                   "Much of that error is shared by every strategy in a race, so the gaps above are more "
                   "reliable than the totals. The bars show the part that isn't shared.")
        actual_flags = next(row["flags"] for row in result["ranking"] if row["strategy"] == BASELINE)
        if actual_flags:
            st.warning("The real strategy itself uses tyres older than any seen here, so its simulated time "
                       "is an extrapolation.")
with right:
    st.markdown("**Where the time is won or lost**")
    alternatives = [g["strategy"] for g in ranges if g["confidence"] != "baseline"]
    picked = st.multiselect("Compare with the real strategy", alternatives,
                            default=[answer["strategy"] or alternatives[0]], format_func=names.get)
    if picked:
        lines = pd.concat([cumulative_gap(result["laps"], strategies, settings["pit_losses"]["median"],
                                          name, BASELINE).assign(strategy=names[name]) for name in picked])
        trace = alt.Chart(lines).mark_line(strokeWidth=2.5, interpolate="step-after").encode(
            x=alt.X("lap_number:Q", title="lap"),
            y=alt.Y("gap:Q", title="seconds behind (+) or ahead (−) of the real strategy"),
            color=alt.Color("strategy:N", title=None, legend=alt.Legend(orient="bottom", labelLimit=400)),
            tooltip=[alt.Tooltip("strategy:N"), alt.Tooltip("lap_number:Q", title="lap"),
                     alt.Tooltip("gap:Q", title="gap (s)", format="+.1f")])
        flat = alt.Chart(pd.DataFrame({"y": [0.0]})).mark_rule(strokeDash=[5, 4], color="gray").encode(y="y:Q")
        st.altair_chart((trace + flat).properties(height=320), width="stretch")
        st.caption("Big steps are pit stops (about {:.0f} s each here). Steady slopes come from tyre age: "
                   "older tyres lose a little time every lap. Where a line ends is the race-total gap."
                   .format(settings["pit_losses"]["median"]))

# --- Details on demand ----------------------------------------------------------------------
with st.expander("How to read this page"):
    st.markdown("""
1. **The real strategy is the yardstick.** Every alternative is simulated with the same model as the real
   strategy and compared with that simulation, not with the real lap times. That way the model's own
   error mostly cancels out.
2. **The verdict** says whether any alternative was faster, and whether it stays faster when pit loss and
   tyre wear are set to less favourable values.
3. **The dot chart** shows each alternative: left of the dashed line is faster, right is slower. A bar that
   crosses the dashed line means the answer depends on the assumptions.
4. **The lap chart** shows *why*: when each strategy loses time in the pits and how fast it loses time on
   older tyres.
""")

with st.expander("All numbers"):
    st.dataframe(pd.DataFrame([{
        "strategy": names[g["strategy"]] + (" (real)" if g["strategy"] == BASELINE else ""),
        "simulated total": race_clock(next(r["total"] for r in result["ranking"] if r["strategy"] == g["strategy"])),
        "gap, best estimate (s)": round(g["gap"], 1),
        "best case (s)": round(g["min_gap"], 1),
        "worst case (s)": round(g["max_gap"], 1),
        "verdict": g["confidence"],
    } for g in ranges]), hide_index=True, width="stretch")
    for row in result["ranking"]:
        for flag in row["flags"]:
            st.caption(f"⚠ {names[row['strategy']]}: {flag}")
        if row["error"]:
            st.caption(f"✘ {row['strategy']} can't be simulated: {row['error']}")

with st.expander("Assumptions and limitations"):
    st.markdown(f"""
- **What the model estimates:** lap-time loss associated with tyre age, not physical tyre wear.
  Lap times are relative to each driver's median clean lap in the race.
- **No driver-specific tyre wear.** The driver only sets the pace level and the real strategy. The
  alternatives rank the same way for every driver in a race.
- **No safety cars, no traffic, no overtaking.** Every car runs in clean air for the whole race, and
  finishing positions are not estimated.
- **Alternatives use new tyre sets.** Real strategies keep their used sets.
- **Track evolution** (the track getting faster) is folded into the race-lap (fuel) term.
- **Pit loss** is per circuit: pit-lane time minus the time to cover the same stretch at racing speed,
  measured in {TRAIN_YEARS[0]}–{TRAIN_YEARS[-1]}.
- **Old tyres:** on 2025 races, laps on tyres 30+ laps old were about 0.7 s faster than the model
  predicts. Long stints may look costlier here than they really are, which favours even stints
  and extra stops.
- **Accuracy:** on 2025 races (never used to build the model) the lap-time error is 0.61 s per clean
  lap, against 0.79 s for always predicting the driver's normal lap. Race totals for real
  strategies were off by about 12 s on average in the backtest.
- This compares a small fixed set of strategies under a model. It does not find an optimal strategy.
""")
