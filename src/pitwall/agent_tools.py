"""Tools a language-model agent can call to answer what-if questions about pit strategy.

Each tool is a plain function that returns a JSON-serialisable dict. A problem (unknown race, unsupported request, invalid
strategy) is returned as {"error": ..., "message": ...} rather than raised, so the model can read it and say so, and every
number it states can be traced to a tool result. The agent (agent.py) and its evaluation (agent_eval.py) are built on these.
"""
import json
import re
import unicodedata
from pathlib import Path

from pitwall.comparison import (STINT_ERROR_FLOOR, TRAIN_YEARS, comparable_races, compare_driver, custom_strategy,
                                driver_choices, fit_inputs, gap_ranges, load_dataset, load_driver_names, verdict)
from pitwall.conformal import load_calibration
from pitwall.describe import plain, race_clock
from pitwall.neutralisation import load_neutralisations
from pitwall.processing import race_distance

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
YEARS = (2023, 2024, 2025)

# Common names for a circuit or its country, mapped to the circuit names used in the dataset.
ALIASES = {
    "bahrain": "Sakhir", "sakhir": "Sakhir", "saudi arabia": "Jeddah", "saudi": "Jeddah", "jeddah": "Jeddah",
    "australia": "Melbourne", "australian": "Melbourne", "albert park": "Melbourne", "melbourne": "Melbourne",
    "japan": "Suzuka", "japanese": "Suzuka", "suzuka": "Suzuka", "china": "Shanghai", "chinese": "Shanghai",
    "shanghai": "Shanghai", "miami": "Miami", "emilia romagna": "Imola", "emilia-romagna": "Imola", "imola": "Imola",
    "monaco": "Monte Carlo", "monte carlo": "Monte Carlo", "canada": "Montreal", "canadian": "Montreal",
    "montreal": "Montreal", "spain": "Catalunya", "spanish": "Catalunya", "barcelona": "Catalunya",
    "catalunya": "Catalunya", "austria": "Spielberg", "austrian": "Spielberg", "red bull ring": "Spielberg",
    "spielberg": "Spielberg", "britain": "Silverstone", "british": "Silverstone", "silverstone": "Silverstone",
    "hungary": "Hungaroring", "hungarian": "Hungaroring", "budapest": "Hungaroring", "hungaroring": "Hungaroring",
    "belgium": "Spa-Francorchamps", "belgian": "Spa-Francorchamps", "spa": "Spa-Francorchamps",
    "spa-francorchamps": "Spa-Francorchamps", "netherlands": "Zandvoort", "dutch": "Zandvoort", "zandvoort": "Zandvoort",
    "italy": "Monza", "italian": "Monza", "monza": "Monza", "azerbaijan": "Baku", "baku": "Baku",
    "singapore": "Singapore", "marina bay": "Singapore", "usa": "Austin", "united states": "Austin", "cota": "Austin",
    "austin": "Austin", "mexico": "Mexico City", "mexican": "Mexico City", "mexico city": "Mexico City",
    "brazil": "Interlagos", "brazilian": "Interlagos", "sao paulo": "Interlagos", "interlagos": "Interlagos",
    "las vegas": "Las Vegas", "vegas": "Las Vegas", "qatar": "Lusail", "lusail": "Lusail",
    "abu dhabi": "Yas Marina Circuit", "yas marina": "Yas Marina Circuit", "yas island": "Yas Marina Circuit",
    "yas marina circuit": "Yas Marina Circuit", "uae": "Yas Marina Circuit",
}

REASONS = {
    "red_flag": "a red flag stopped the race (a free tyre change and a standing restart, which the model doesn't simulate)",
    "wet_tyres": "some cars used intermediate or wet tyres (the model is dry-only)",
}

CAVEATS = [
    "This is a model's estimate of lap times, not what would have happened. Gaps are model-against-model, so the model's "
    "shared error mostly cancels, but they are still estimates.",
    "The model only knows tyre age, fuel, traffic and safety cars, so it tends to favour evenly split stints. It cannot "
    "see undercuts, tyre allocation or sudden tyre drop-off; a preferred alternative is not proof the team made a mistake.",
    "Traffic is a simple replay of the other cars' real laps (they never react), and safety cars are replayed from what "
    "really happened, never predicted.",
]


def load_context(data_dir: Path = DATA_DIR, refits: int = 20) -> dict:
    '''
    Everything the tools need, loaded once.

    data_dir: folder with lap_dataset.parquet, neutralisations.json, driver_names.json, calibration.json and
        race_selection.json (the committed data/processed/)
    refits: how many refits of the model back the "faster in n of k refits" figure

    returns: dict with "rows", "windows", "inputs", "names", "calibration", "selection" and "offered" (the set of
    (year, circuit) races the tools can compare).

    raises FileNotFoundError if the dataset is missing.
    '''
    rows = load_dataset(data_dir / "lap_dataset.parquet")
    windows = load_neutralisations(data_dir / "neutralisations.json")
    inputs = fit_inputs(rows, TRAIN_YEARS, windows, refits=refits)
    selection_path = data_dir / "race_selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8")) if selection_path.exists() else {}
    return {"rows": rows, "windows": windows, "inputs": inputs, "names": load_driver_names(data_dir / "driver_names.json"),
            "calibration": load_calibration(data_dir / "calibration.json"), "selection": selection,
            "offered": set(comparable_races(rows, windows, inputs))}


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\b(grand prix|gp|the)\b", " ", text)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\- ]", " ", text)).strip()


def _error(kind: str, message: str, **extra) -> dict:
    return {"error": kind, "message": message, **extra}


def resolve_race(ctx: dict, text: str) -> tuple[int, str] | dict:
    '''
    Turns "Monza 2024", "Italian GP 2024" or "Abu Dhabi 2023" into (year, circuit).

    returns: the pair, or an error dict (no year, a year the data doesn't cover, an unknown circuit).
    '''
    year_match = re.search(r"\b(19|20)\d\d\b", text)
    if not year_match:
        return _error("year_needed", f"Which year? The data covers {YEARS[0]} to {YEARS[-1]}.", example="Monza 2024")
    year = int(year_match.group())
    if year not in YEARS:
        why = ("OpenF1, the data source, has no data before 2023" if year < 2023 else
               "2026 is outside the 2022-2025 regulation period this project covers" if year == 2026 else
               "that year isn't in the data")
        return _error("year_not_available", f"{year} isn't available: {why}. Available: {YEARS[0]} to {YEARS[-1]}.")
    name = _normalise(text.replace(year_match.group(), " "))
    circuits = sorted({k.rsplit(" ", 1)[0] for k in ctx["selection"]} | {c for _, c in ctx["offered"]})
    by_name = {_normalise(c): c for c in circuits} | ALIASES
    circuit = by_name.get(name)
    if circuit is None:                       # fall back to the longest alias contained in the text
        hits = [alias for alias in by_name if alias in name]
        circuit = by_name[max(hits, key=len)] if hits else None
    if circuit is None:
        return _error("unknown_race", f"I couldn't match {text!r} to a circuit or country.", circuits=circuits)
    return year, circuit


def _race_problem(ctx: dict, year: int, circuit: str) -> dict | None:
    """An error dict if (year, circuit) can't be compared, with the reason in plain words; None if it can."""
    label = f"{circuit} {year}"
    if (year, circuit) in ctx["offered"]:
        return None
    info = ctx["selection"].get(label)
    if info is None:
        return _error("no_such_race", f"There was no {label} Grand Prix in the data (it may not have been held, or the "
                                      "circuit wasn't on the calendar that year).")
    if not info["used"]:
        reasons = " and ".join(REASONS.get(r, r) for r in info["reasons"])
        return _error("race_excluded", f"{label} isn't available: {reasons}.")
    if circuit not in ctx["inputs"]["pit_loss"]:
        return _error("race_not_offered", f"{label} isn't offered: the model has no other race at {circuit} to learn pit "
                                          "loss and tyre wear from.")
    return _error("race_not_offered", f"{label} isn't offered: its safety car can't be replayed (every car pitted together, "
                                      "so there is no field lap time).")


def _label(car: dict) -> str:
    return f"{car['acronym']} ({car['name']}, #{car['number']})" if car.get("acronym") else f"#{car['number']}"


def _cars(ctx: dict, year: int, circuit: str) -> list[dict]:
    session = next(r["session_key"] for r in ctx["rows"] if r["circuit"] == circuit and r["year"] == year)
    cars = []
    for number in driver_choices(ctx["rows"], circuit, year, ctx["inputs"]["model"], windows=ctx["windows"]):
        known = ctx["names"].get((session, number)) or {}
        cars.append({"number": number, "acronym": known.get("acronym"), "name": known.get("name"), "team": known.get("team")})
    return cars


def resolve_car(ctx: dict, year: int, circuit: str, text: str) -> dict:
    '''
    Finds one car in a race by number, three-letter code ("LEC"), or name ("Leclerc", "Charles Leclerc").

    returns: the car dict (number, acronym, name, team) or an error dict listing the cars that can be compared.
    '''
    cars = _cars(ctx, year, circuit)
    wanted = _normalise(str(text))
    if wanted.isdigit():
        matches = [c for c in cars if c["number"] == int(wanted)]
    else:
        matches = [c for c in cars if (c["acronym"] or "").lower() == wanted
                   or wanted and wanted in _normalise(c["name"] or "")]
    if len(matches) == 1:
        return matches[0]
    available = [_label(c) for c in cars]
    if matches:
        return _error("ambiguous_car", f"{text!r} matches more than one car: {[_label(c) for c in matches]}.", cars=available)
    return _error("car_not_found", f"No comparable car matches {text!r} at {circuit} {year}. Only cars that ran every lap "
                                   "on the lead lap with enough clean laps are offered.", cars=available)


def list_races(ctx: dict) -> dict:
    '''
    The races the simulator can compare, and why the others can't be.

    returns: {"offered": {year: [circuit, ...]}, "offered_count": {year: n}, "not_available": {"Monte Carlo 2023": reason, ...},
    "years": [...]}; the counts are there so the model never has to count a list itself
    '''
    offered = {}
    for year, circuit in sorted(ctx["offered"]):
        offered.setdefault(str(year), []).append(circuit)
    not_available = {}
    for label, info in ctx["selection"].items():
        year, circuit = int(label.rsplit(" ", 1)[1]), label.rsplit(" ", 1)[0]
        if (year, circuit) not in ctx["offered"]:
            problem = _race_problem(ctx, year, circuit)
            not_available[label] = problem["message"].split(" isn't ", 1)[-1] if problem else ""
    return {"years": list(YEARS), "offered": offered, "offered_count": {y: len(v) for y, v in offered.items()},
            "not_available": not_available,
            "note": "Data comes from OpenF1, which has no data before 2023."}


def list_cars(ctx: dict, race: str) -> dict:
    '''The cars that can be compared in one race (number, three-letter code, name, team), or an error dict.'''
    resolved = resolve_race(ctx, race)
    if isinstance(resolved, dict):
        return resolved
    year, circuit = resolved
    problem = _race_problem(ctx, year, circuit)
    if problem:
        return problem
    cars = _cars(ctx, year, circuit)
    return {"race": f"{circuit} {year}", "car_count": len(cars), "cars": cars}


def _one_decimal(value: float) -> float:
    return round(float(value), 1)


def compare_strategy(ctx: dict, race: str, car: str, compounds: list, pit_laps: list) -> dict:
    '''
    Compares one car's real strategy with alternatives in one race.

    race: e.g. "Monza 2024"
    car: number, three-letter code or name
    compounds, pit_laps: a strategy to test, e.g. ["MEDIUM", "HARD"] and [20] for one stop on lap 20 (the stop is made at the
        end of that lap); both empty means "compare with the standard alternatives"

    returns: dict with the real strategy and times, the verdict, every alternative's gap (negative = faster than the real
    strategy) with its range and how many refits agree, calibrated intervals with their measured coverage, and caveats; or an
    error dict. All numbers are rounded to one decimal.
    '''
    resolved = resolve_race(ctx, race)
    if isinstance(resolved, dict):
        return resolved
    year, circuit = resolved
    problem = _race_problem(ctx, year, circuit)
    if problem:
        return problem
    driver = resolve_car(ctx, year, circuit, car)
    if "error" in driver:
        return driver
    custom = None
    if compounds or pit_laps:
        try:
            custom = custom_strategy(list(compounds), list(pit_laps), _distance(ctx, year, circuit))
        except (ValueError, TypeError) as error:
            return _error("invalid_strategy", str(error))
    try:
        result = compare_driver(ctx["rows"], ctx["inputs"], circuit, year, driver["number"], custom=custom, traffic=True)
    except ValueError as error:
        return _error("cannot_simulate", str(error))

    ranges = gap_ranges(result["sensitivity"], "actual", refit_gaps=result["refit_gaps"])
    answer = verdict(ranges)
    names = {name: plain(strategy) for name, strategy in result["strategies"].items()}
    flags = {row["strategy"]: bool(row["flags"]) for row in result["ranking"]}
    alternatives = []
    for entry in sorted((g for g in ranges if g["confidence"] != "baseline"), key=lambda g: g["gap"]):
        item = {"strategy": names[entry["strategy"]], "gap_s": _one_decimal(entry["gap"]),
                "range_over_pit_loss_assumptions_s": [_one_decimal(entry["min_gap"]), _one_decimal(entry["max_gap"])]}
        if entry["p_faster"] is not None:
            item["faster_in_refits"] = f"{round(entry['p_faster'] * entry['refits'])} of {entry['refits']}"
        if entry["strategy"] == "custom":
            item["is_the_users_strategy"] = True
        if flags.get(entry["strategy"]):
            item["warning"] = "runs tyres older than any seen at this circuit, so its number is an extrapolation"
        alternatives.append(item)
    mine = next((a for a in alternatives if a.get("is_the_users_strategy")), None)
    out = {"race": f"{circuit} {year}", "car": _label(driver), "real_strategy": names["actual"],
           "real_time": race_clock(result["actual_time"]), "simulated_real_time": race_clock(result["simulated_actual"]),
           "model_error_s": _one_decimal(result["model_error"]),
           "gap_meaning": "negative gap = faster than the real strategy; positive = slower",
           "verdict": _verdict_summary(answer, names),
           "alternatives": alternatives,
           "typical_stint_error_s": _one_decimal(STINT_ERROR_FLOOR),
           "caveats": CAVEATS}
    if mine is not None:
        entry = next(g for g in ranges if g["strategy"] == "custom")
        out["your_strategy"] = {**mine, **_your_strategy_summary(mine, entry, ranges)}
    if result["neutralisation_windows"]:
        out["safety_car_replayed"] = [
            f"{'safety car' if w['kind'] == 'SC' else 'virtual safety car'} on laps {w['start']} to {w['end']}"
            for w in result["neutralisation_windows"]]
    out.update(_interval_facts(ctx, bool(result["neutralisation_windows"])))
    return out


def _distance(ctx: dict, year: int, circuit: str) -> int:
    return race_distance([r for r in ctx["rows"] if r["circuit"] == circuit and r["year"] == year])


def _verdict_summary(answer: dict, names: dict) -> dict:
    kind = answer["kind"]
    if kind == "agrees":
        return {"kind": kind, "summary": "The model agrees with the real strategy: none of the alternatives is faster at its best estimate."}
    best, entry = names[answer["strategy"]], answer["range"]
    faster = f", faster in {round(entry['p_faster'] * entry['refits'])} of {entry['refits']} refits" if entry["p_faster"] is not None else ""
    gap = _one_decimal(-entry["gap"])
    if kind == "too_close":
        return {"kind": kind, "best_alternative": best, "faster_by_s": gap,
                "summary": f"Too close for the model to call. The closest alternative is {best}, {gap} s faster at its best estimate{faster}, "
                           f"which is within the model's typical stint error (about {_one_decimal(STINT_ERROR_FLOOR)} s) or not stable across refits."}
    word = "prefers" if kind == "prefers" else "leans towards"
    return {"kind": kind, "best_alternative": best, "faster_by_s": gap,
            "summary": f"The model {word} {best}: {gap} s faster at its best estimate{faster}. Read it as what the model prefers, not as a mistake by the team."}


def _your_strategy_summary(mine: dict, entry: dict, ranges: list[dict]) -> dict:
    """A verdict about the strategy the user asked about, judged the same way as the standard alternatives."""
    gap = mine["gap_s"]
    if mine.get("warning"):
        return {"summary": "The strategy you asked about runs tyres older than any seen at this circuit, so the model can't judge it "
                           f"reliably; its gap of {gap} s is an extrapolation."}
    baseline = next(g for g in ranges if g["confidence"] == "baseline")
    answer = verdict([baseline, entry])
    refits = f", faster in {mine['faster_in_refits']} refits" if "faster_in_refits" in mine else ""
    if gap >= 0:
        return {"summary": f"Under the model your strategy would have been {_one_decimal(gap)} s slower than the real one (gap {gap} s).",
                "verdict_kind": "agrees"}
    if answer["kind"] == "too_close":
        reason = (f"it is within the model's typical stint error (about {_one_decimal(STINT_ERROR_FLOOR)} s)"
                  if -gap < STINT_ERROR_FLOOR else "the answer changes too often when the model is refitted on different races")
        return {"summary": f"Under the model your strategy is {_one_decimal(-gap)} s faster at its best estimate{refits}, but that is too "
                           f"close for the model to call: {reason}.", "verdict_kind": "too_close"}
    word = "prefers" if answer["kind"] == "prefers" else "leans towards"
    return {"summary": f"Under the model your strategy is {_one_decimal(-gap)} s faster at its best estimate{refits}; the model {word} it over "
                       "the real strategy.", "verdict_kind": answer["kind"]}


def _interval_facts(ctx: dict, safety_car: bool) -> dict:
    calibration = ctx["calibration"]
    if not calibration:
        return {}
    level = f"{calibration['level']:.0%}"
    total = calibration["targets"]["race_total_safety_car" if safety_car else "race_total"]
    gap = calibration["targets"]["gap"]
    return {"intervals": {
        "race_total": f"{level} interval of plus or minus {_one_decimal(total['half_width'])} s; on {calibration['test_year']} races it covered "
                      f"{total['rolling']['coverage']:.0%} of real race totals",
        "gap": f"{level} interval of plus or minus {_one_decimal(gap['half_width'])} s, measured between two different real cars "
               f"(a cautious bound; it covered {gap['rolling']['coverage']:.0%} of {calibration['test_year']} gaps)"}}


_SCHEMA = {"type": "object", "additionalProperties": False}
TOOL_DEFINITIONS = [
    {"name": "list_races", "strict": True,
     "description": "List the Grands Prix the simulator can compare (2023-2025) and, for the others, why they can't be "
                    "(red flag, wet tyres, no data). Use it to check whether a race is available or to answer 'which races'.",
     "input_schema": {**_SCHEMA, "properties": {}, "required": []}},
    {"name": "list_cars", "strict": True,
     "description": "List the cars (number, three-letter code, driver name, team) that can be compared in one race.",
     "input_schema": {**_SCHEMA, "properties": {"race": {"type": "string", "description": "Circuit or country and year, e.g. 'Monza 2024'."}},
                      "required": ["race"]}},
    {"name": "compare_strategy", "strict": True,
     "description": "Simulate one car's race under its real strategy and under alternatives, and return the time gaps, a verdict, "
                    "how sure the model is, and caveats. With empty compounds and pit_laps it compares against the standard "
                    "alternatives. To test a specific strategy, give both: compounds in order and the lap each stop is made on "
                    "(the in-lap), e.g. compounds ['MEDIUM','HARD'] with pit_laps [20] is one stop at the end of lap 20.",
     "input_schema": {**_SCHEMA,
                      "properties": {"race": {"type": "string", "description": "Circuit or country and year, e.g. 'Monza 2024'."},
                                     "car": {"type": "string", "description": "Car number, three-letter code ('LEC') or driver name."},
                                     "compounds": {"type": "array", "items": {"type": "string"},
                                                   "description": "Tyre compound of each stint in order (SOFT, MEDIUM or HARD); [] for the standard comparison."},
                                     "pit_laps": {"type": "array", "items": {"type": "integer"},
                                                  "description": "Lap of each stop, one fewer than compounds; [] for the standard comparison."}},
                      "required": ["race", "car", "compounds", "pit_laps"]}},
]


def run_tool(ctx: dict, name: str, tool_input: dict) -> dict:
    '''Runs one tool by name. Never raises: an unknown tool or bad input comes back as an error dict.'''
    try:
        if name == "list_races":
            return list_races(ctx)
        if name == "list_cars":
            return list_cars(ctx, tool_input["race"])
        if name == "compare_strategy":
            return compare_strategy(ctx, tool_input["race"], tool_input["car"], tool_input.get("compounds") or [],
                                    tool_input.get("pit_laps") or [])
    except (KeyError, TypeError) as error:
        return _error("bad_input", f"The tool input was malformed: {error!r}.")
    return _error("unknown_tool", f"There is no tool called {name!r}. Tools: list_races, list_cars, compare_strategy.")
