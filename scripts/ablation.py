"""Model ablation: can a different model shape or a weather feature fix the two known residual problems (first stints
predicted too fast, old tyres over-penalised)? Every variant is fitted on one year and scored on the other (2023/24
cross-year); 2025 is never used. Writes the table to docs/MODEL_ABLATION.md.

Run after build_dataset.py:  uv run python scripts/ablation.py"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.preprocessing import OneHotEncoder

import evaluate as ev
from pitwall.comparison import load_dataset
from pitwall.evaluation import leave_one_year_out
from pitwall.model import PairAgeColumns, PooledWearModel
from pitwall.traffic import fit_traffic_penalty

REPORT = Path("docs/MODEL_ABLATION.md")
TRACK_TEMP_CENTRE = 35.0

VARIANTS = {   # name -> extra columns added to the current model
    "current model": [],
    "+ fuel squared": ["rf2"],
    "+ fuel squared and cubed": ["rf2", "rf3"],
    "+ wear hinge at age 25": ["h25"],
    "+ tyre age squared": ["age2"],
    "+ new-tyre warm-up exp(-age/3)": ["warm"],
    "+ fuel squared + hinge": ["rf2", "h25"],
    "+ fuel squared + warm-up": ["rf2", "warm"],
    "+ fuel squared + hinge + warm-up": ["rf2", "h25", "warm"],
    "+ track temperature x tyre age": ["tt_age"],
    "+ track temperature x race fraction": ["tt_rf"],
    "+ track temperature x both": ["tt_age", "tt_rf"],
    "+ track temperature x both + fuel squared + hinge": ["tt_age", "tt_rf", "rf2", "h25"],
}


def with_features(df):
    df = df.copy()
    rf, age = df["race_fraction"], df["tyre_age"]
    df["rf2"], df["rf3"] = rf ** 2, rf ** 3
    df["h25"], df["age2"], df["warm"] = np.maximum(0, age - 25), age ** 2 / 100, np.exp(-age / 3)
    if "track_temp" in df:
        tt = (df["track_temp"] - TRACK_TEMP_CENTRE) / 10
        df["tt_age"], df["tt_rf"] = tt * age, tt * rf
    return df


class Variant(PooledWearModel):
    """The current pooled model plus extra pass-through columns, computed from the row's own columns."""

    def __init__(self, alpha=100_000, fuel_column="race_fraction", extra=()):
        super().__init__(alpha, fuel_column)
        self.extra = list(extra)

    def fit(self, X, y):
        self.columns_ = ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="error", sparse_output=False), ["compound"]),
            ("pass", "passthrough", ["tyre_age", self.fuel_column] + self.extra),
            ("wear", PairAgeColumns(), ["compound", "circuit", "tyre_age"])], remainder="drop")
        features = np.asarray(self.columns_.fit_transform(with_features(X)), dtype=float)
        names = self.columns_.get_feature_names_out()
        penalised = np.array([n.startswith("wear__") for n in names], dtype=float)
        self.coef_ = np.linalg.solve(features.T @ features + self.alpha * np.diag(penalised),
                                     features.T @ np.asarray(y, dtype=float))
        return self

    def predict(self, X):
        return np.asarray(self.columns_.transform(with_features(X)), dtype=float) @ self.coef_


class BoostedTrees:
    """Benchmark: gradient boosting on compound, circuit, tyre age and race fraction. Trees can't extrapolate beyond the
    tyre ages they saw, which is what a strategy simulator has to do."""

    def fit(self, X, y):
        self.pairs_ = set(zip(X["compound"], X["circuit"]))
        self.codes_ = {c: {v: i for i, v in enumerate(sorted(X[c].unique()))} for c in ("compound", "circuit")}
        self.model_ = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                                    min_samples_leaf=40, categorical_features=[0, 1], random_state=0)
        self.model_.fit(self._matrix(X), y)
        return self

    def _matrix(self, X):
        return np.column_stack([X["compound"].map(self.codes_["compound"]), X["circuit"].map(self.codes_["circuit"]),
                                X["tyre_age"], X["race_fraction"]])

    def predict(self, X):
        return self.model_.predict(self._matrix(X))

    def pair_adjustments(self):
        return {f"{c}@{k}": 0.0 for c, k in self.pairs_}


def add_race_weather(rows):
    """Adds each race's mean track temperature (over the laps' time span) to its rows as "track_temp"."""
    by_session = {}
    for row in rows:
        by_session.setdefault(row["session_key"], []).append(row)
    for session, race in by_session.items():
        starts = [r["date_start"] for r in race if r["date_start"]]
        start, end = pd.to_datetime(min(starts), utc=True), pd.to_datetime(max(starts), utc=True) + pd.Timedelta(minutes=2)
        weather = pd.DataFrame(json.loads(Path(f"data/raw/weather_{session}.json").read_text()))
        weather["t"] = pd.to_datetime(weather["date"], utc=True, format="ISO8601")
        track = weather[(weather["t"] >= start) & (weather["t"] <= end)]["track_temperature"].mean()
        for row in race:
            row["track_temp"] = float(track)


def markdown_table(df):
    """A GitHub-flavoured Markdown table (no extra dependency)."""
    lines = ["| " + " | ".join(df.columns) + " |", "|---|" + "---:|" * (len(df.columns) - 1)]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def main():
    rows = load_dataset(ev.DATASET_PATH)
    add_race_weather(rows)
    races = sorted({(r["year"], r["circuit"]) for r in rows})
    results = []
    for name, extra in list(VARIANTS.items()) + [("gradient boosting (benchmark)", None)]:
        lap_errors, stints = [], []
        for year, fold_train, fold_test in leave_one_year_out(rows, [2023, 2024]):
            train = pd.DataFrame([r for r in fold_train if r["is_clean"] and r["delta"] is not None])
            model = BoostedTrees().fit(train, train["delta"]) if extra is None else Variant(extra=extra).fit(train, train["delta"])
            seen = set(zip(train["compound"], train["circuit"]))
            test = pd.DataFrame([r for r in fold_test if r["is_clean"] and r["delta"] is not None
                                 and (r["compound"], r["circuit"]) in seen])
            test["error"] = model.predict(test) - test["delta"]
            lap_errors.append(test)
            traffic = fit_traffic_penalty(fold_train, Variant(extra=[]).fit(train, train["delta"]))
            stints.append(pd.DataFrame(ev.stint_check_records(rows, [r for r in races if r[0] == year], model, traffic)))
        laps, stint = pd.concat(lap_errors), pd.concat(stints)
        results.append({"variant": name, "lap MAE (s)": laps["error"].abs().mean(),
                        "stint error, median (s)": stint["error_total"].abs().median(),
                        "first-stint bias (s/lap)": stint[stint["position"] == "first"]["error_per_lap"].mean(),
                        "last-stint bias (s/lap)": stint[stint["position"] == "last"]["error_per_lap"].mean(),
                        "bias at age 30+ (s/lap)": laps[laps["tyre_age"] >= 30]["error"].mean()})
        print(name, "done", flush=True)
    table = pd.DataFrame(results).round(3)
    print(table.to_string(index=False))
    REPORT.write_text(
        "# Model ablation\n\nGenerated by `scripts/ablation.py`. Do not edit by hand.\n\n"
        "Every variant is fitted on one of 2023/2024 and scored on the other (clean laps, compound@circuit pairs the "
        "model knows). 2025 is not used. First/last-stint bias: each stint predicted from the same car's other stints "
        "(positive = predicted too slow). Bias at age 30+: predicted minus actual on laps of tyres 30 or more laps old "
        "(1,613 laps).\n\n" + markdown_table(table) + "\n", encoding="utf-8")
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
