from pathlib import Path
from statistics import median
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from pitwall.evaluation import leave_one_race_out, score, score_by_group, split_by_year, leave_one_year_out
from pitwall.features import add_delta, add_race_fraction, driver_reference_laps
from pitwall.model import PooledWearModel, build_pipeline
from pitwall.analysis import lap_one_losses, max_clean_tyre_age, pit_loss_by_circuit, residual_trends, stop_losses
from pitwall.backtest import backtest_race, second_half_record, strategy_pair_errors
from pitwall.comparison import (BASELINE, TRAIN_YEARS, comparable_races, compare_race, driver_choices,
                                fastest_by_scenario, fit_final_model, fit_inputs, load_dataset)
from pitwall.processing import race_distance
from pitwall.simulator import observed_max_ages
from pitwall.neutralisation import build_neutralisation, fit_sc_pit_loss, load_neutralisations
from pitwall.traffic import fit_traffic_penalty, real_gaps

DATASET_PATH = Path("data/processed/lap_dataset.parquet")
NEUTRALISATIONS_PATH = Path("data/processed/neutralisations.json")
# Tyre-age buckets for the error slices: 0-9, 10-19, 20-29, 30+ laps.
AGE_BINS = [-1, 9, 19, 29, float("inf")]
AGE_LABELS = ["0-9", "10-19", "20-29", "30+"]

# Penalty strengths tried for PooledWearModel; chosen on the cross-year split, never on 2025.
# A 400-lap pair has a sum of squared tyre ages near 1e5, so the useful range is about 1e3-1e6.
POOLING_ALPHAS = [1_000, 10_000, 100_000, 1_000_000]

LAP_BINS = [0, 10, 20, 30, 40, 50, 60, 70]
LAP_LABELS = ["1-10", "11-20", "21-30", "31-40", "41-50", "51-60", "61-70"]

def scored_rows(rows, flag):
    """Rows where `flag` is true, split into (usable, skipped) by whether delta exists."""
    selected = [row for row in rows if row[flag]]
    usable = [row for row in selected if row["delta"] is not None]
    return usable, len(selected) - len(usable)


def zero_baseline(rows):
    """Scores for predicting a delta of 0 on every row."""
    actual = [row["delta"] for row in rows]
    predicted = [0.0] * len(actual)
    return score(actual, predicted)

def fit_model(include_race_lap: bool, wear_by_pair: bool, train, fuel_column="lap_number", pooling_alpha=None):
    """Fitted on the clean rows of train. With pooling_alpha set, a PooledWearModel instead (other flags ignored)."""
    usable_rows, _ = scored_rows(train, "is_clean")
    train_df = pd.DataFrame(usable_rows)

    if pooling_alpha is None:
        pipeline = build_pipeline(include_race_lap, wear_by_pair, fuel_column)
    else:
        pipeline = PooledWearModel(pooling_alpha, fuel_column)
    pipeline.fit(train_df, train_df['delta'])

    return pipeline

def training_pairs(train):
    """(compound, circuit) pairs on the 2024 clean laps the models are fitted on."""
    usable_rows, _ = scored_rows(train, "is_clean")
    return {(row["compound"], row["circuit"]) for row in usable_rows}    

def print_slices(train, test):
    """Error slices on 2025 clean laps, Model B next to Model C."""
    usable, _ = scored_rows(test, "is_clean")
    test_df = pd.DataFrame(usable)
    test_df["age_bucket"] = pd.cut(test_df["tyre_age"], bins=AGE_BINS, labels=AGE_LABELS)

    models = {"B": fit_model(True, False, train), "C": fit_model(True, True, train)}
    for by in ("compound", "circuit", "age_bucket"):
        tables = []
        for name, pipeline in models.items():
            scored = test_df.assign(predicted=pipeline.predict(test_df))
            tables.append(score_by_group(scored, by)[["mae", "bias"]].add_prefix(f"{name}_"))
        table = pd.concat(tables, axis=1)
        table["n"] = test_df.groupby(by, observed=True).size()
        print(f"\nClean 2025 laps by {by} (seconds)")
        print(table.round(3).to_string())


def held_out_predictions(include_race_lap, train, fuel_column="lap_number"):
    """Clean 2024 laps, each predicted by a model fitted on the other four 2024 races."""
    frames = []
    for _, fold_train, fold_validation in leave_one_race_out(train):
        pipeline = fit_model(include_race_lap, False, fold_train, fuel_column)
        usable, _ = scored_rows(fold_validation, "is_clean")
        validation_df = pd.DataFrame(usable)
        frames.append(validation_df.assign(predicted=pipeline.predict(validation_df)))
    return pd.concat(frames, ignore_index=True)

def cross_year_predictions(include_race_lap, wear_by_pair, rows, fuel_column = "race_fraction", pooling_alpha=None):
    """Clean 2023 and 2024 laps, each predicted by a model fitted on the other year."""
    frames = []
    for year, fold_train, fold_validation in leave_one_year_out(rows, [2023, 2024]):
        pipeline = fit_model(include_race_lap, wear_by_pair, fold_train, fuel_column, pooling_alpha)
        usable, _ = scored_rows(fold_validation, "is_clean")

        pairs = training_pairs(fold_train)
        seen = [row for row in usable if (row['compound'], row['circuit']) in pairs]
        print(f" held out {year}: dropped {len(usable)- len(seen)} rows, pair not in training")
        
        validation_df = pd.DataFrame(seen)
        frames.append(validation_df.assign(predicted=pipeline.predict(validation_df), held_out_year = year))
    return pd.concat(frames, ignore_index=True)


def print_cross_year(rows):
    """B_frac (one wear rate), C_frac (wear per compound@circuit) and pooled (P_<alpha>), fitted on one year, scored on the other."""
    print("\nCross-year (fit on 2023, score 2024, and the reverse), clean laps")
    results = {}
    models = [("B_frac", False, None), ("C_frac", True, None)] + [(f"P_{a}", False, a) for a in POOLING_ALPHAS]
    for name, wear_by_pair, alpha in models:
        df = cross_year_predictions(True, wear_by_pair, rows, pooling_alpha=alpha)
        result = score(df["delta"].tolist(), df["predicted"].tolist())
        print(
            f"  {name:<6}  n={len(df):>5}  "
            f"MAE={result['mae']:.3f}s  RMSE={result['rmse']:.3f}s  bias={result['bias']:+.3f}s"
        )
        results[name] = df

    for by in ("held_out_year", "circuit"):
        for metric in ("mae", "bias"):
            table = pd.concat({name: score_by_group(df, by)[metric] for name, df in results.items()}, axis=1)
            table["n"] = results["B_frac"].groupby(by).size()
            print(f"\nCross-year {metric} by {by} (seconds)")
            print(table.round(3).to_string())


def cross_year_backtest(rows, wear_by_pair=False, pooling_alpha=None, pace="race_median", traffic=False):
    """Backtest records for the safety-car-free 2023 and 2024 races, each with model, pit loss,
    lap-1 loss and observed range estimated on the other year only."""
    records = []
    for year, fold_train, fold_validation in leave_one_year_out(rows, [2023, 2024]):
        train_years = sorted({row["year"] for row in fold_train})
        model = fit_model(True, wear_by_pair, fold_train, "race_fraction", pooling_alpha)
        pit_loss = pit_loss_by_circuit(stop_losses(fold_train, model), train_years)
        lap_one_records = lap_one_losses(fold_train, model)
        lap_one = pit_loss_by_circuit(lap_one_records, train_years)
        # A circuit whose lap 1 was neutralised in the training year (Yas Marina 2024 VSC) has no
        # lap-1 loss; it gets the median over all circuits that year. Same race for every model.
        lap_one_all = median(r["loss"] for r in lap_one_records if r["loss"] is not None)
        max_ages = observed_max_ages(max_clean_tyre_age(fold_train), train_years)
        traffic_table = fit_traffic_penalty(fold_train, model) if traffic else None

        races = {}
        for row in fold_validation:
            races.setdefault(row["session_key"], []).append(row)
        for race in races.values():
            if any("safety_car" in row["exclusion_reasons"] for row in race):
                continue
            circuit = race[0]["circuit"]
            if circuit in lap_one:
                lap_one_loss = lap_one[circuit]["median"]
            else:
                lap_one_loss = lap_one_all
                print(f"    {circuit} {year}: no lap-1 loss in {train_years}, using all-circuit median {lap_one_all:.1f}s")
            records += backtest_race(race, model, pit_loss[circuit]["median"], lap_one_loss, max_ages, pace,
                                     traffic_table)
    return records


def print_cross_year_backtest(rows):
    """Race-total backtest, cross-year, for B_frac, C_frac and the pooled alphas (chooses alpha)."""
    print("\nCross-year race-total backtest (safety-car-free 2023 and 2024 races, lead-lap finishers)")
    models = [("B_frac", False, None), ("C_frac", True, None)] + [(f"P_{a}", False, a) for a in POOLING_ALPHAS]
    results = {}
    for name, wear_by_pair, alpha in models:
        df = pd.DataFrame(cross_year_backtest(rows, wear_by_pair, alpha))
        done = df[df["predicted"].notna()].copy()
        done["error_per_lap"] = done["error"] / done["laps"]
        flagged = (done["flags"].str.len() > 0).sum()
        print(
            f"  {name:<9} n={len(done):>3} flagged={flagged:>2} skipped={len(df) - len(done):>3}  "
            f"MAE={done['error'].abs().mean():6.2f}s  bias={done['error'].mean():+6.2f}s  "
            f"MAE/lap={done['error_per_lap'].abs().mean():.3f}s"
        )
        results[name] = done
    print("  skip reasons (B_frac):", pd.DataFrame(cross_year_backtest(rows))["skip_reason"].value_counts().to_dict())

    for metric, func in (("MAE", lambda e: e.abs().mean()), ("bias", lambda e: e.mean())):
        table = pd.concat({name: done.groupby(["year", "circuit"])["error"].agg(func)
                           for name, done in results.items()}, axis=1)
        table["n"] = results["B_frac"].groupby(["year", "circuit"]).size()
        print(f"\nCross-year backtest {metric} by race (seconds)")
        print(table.round(1).to_string())


def print_error_split(rows):
    """Cross-year backtest error split into lap 1, stops and normal laps (mean per race), then the
    normal-lap error by lap bucket: a drift with race lap points at the fuel term, a flat offset
    at the reference lap or pace level."""
    for name, alpha in (("B_frac", None), ("P_100000", 100_000)):
        done = pd.DataFrame(cross_year_backtest(rows, pooling_alpha=alpha)).dropna(subset=["predicted"])
        parts = pd.DataFrame(done["components"].tolist(), index=done.index)
        done = done.join(parts[["lap_one", "stops", "normal"]])
        done["normal_per_lap"] = done["normal"] / parts["normal_by_lap"].str.len()
        table = done.groupby(["year", "circuit"])[["error", "lap_one", "stops", "normal", "normal_per_lap"]].mean()
        table["n"] = done.groupby(["year", "circuit"]).size()
        print(f"\nBacktest error split, {name}: mean per race (seconds, + = predicted too slow)")
        print(table.round(2).to_string())

        laps = pd.DataFrame([{"year": y, "circuit": c, "lap_number": lap, "error": e}
                             for y, c, by_lap in zip(done["year"], done["circuit"], parts["normal_by_lap"])
                             for lap, e in by_lap.items()])
        laps["lap_bucket"] = pd.cut(laps["lap_number"], bins=LAP_BINS, labels=LAP_LABELS)
        drift = laps.pivot_table(index="lap_bucket", columns=["year", "circuit"], values="error",
                                 aggfunc="mean", observed=True)
        print(f"\nNormal-lap error by lap bucket, {name} (seconds per lap)")
        print(drift.round(2).to_string())


def fuel_coefficient(model):
    """Fitted race_fraction coefficient (seconds over the whole race) of a B pipeline or a PooledWearModel."""
    if isinstance(model, PooledWearModel):
        names, coefficients = model.columns_.get_feature_names_out(), model.coef_
    else:
        names = model.named_steps["preprocessor"].get_feature_names_out()
        coefficients = model.named_steps["regressor"].coef_
    return float(dict(zip(names, coefficients))["pass__race_fraction"])


def print_residual_trends(rows):
    """Leftover race-lap and per-compound tyre-age slopes on the safety-car-free backtest races,
    each race scored by a model fitted on the other year. Tyre-age slopes near 0 mean the
    backtest drift is race-lap error, which every strategy in a race shares."""
    for name, alpha in (("B_frac", None), ("P_100000", 100_000)):
        records = []
        for year, fold_train, fold_validation in leave_one_year_out(rows, [2023, 2024]):
            model = fit_model(True, False, fold_train, "race_fraction", alpha)
            print(f"  {name} fitted without {year}: fuel coefficient {fuel_coefficient(model):+.2f}s over the race")
            safety_car = {r["session_key"] for r in fold_validation if "safety_car" in r["exclusion_reasons"]}
            records += residual_trends([r for r in fold_validation if r["session_key"] not in safety_car], model)
        df = pd.DataFrame(records)
        print(f"\nResidual trends, {name} (race_fraction: s over the race; tyre_age: s per lap of age)")
        print(df.pivot_table(index=["year", "circuit"], values="race_fraction_slope", aggfunc="first")
                .round(2).to_string())
        print(df.pivot_table(index=["year", "circuit"], columns="compound", values="tyre_age_slope",
                             aggfunc="first").round(3).to_string())
        laps = df.pivot_table(index=["year", "circuit"], columns="compound", values="n_laps", aggfunc="first")
        print("clean laps per compound:\n" + laps.to_string())
        print("skip reasons:", df["skip_reason"].value_counts().to_dict())


def print_held_out_2024(train):
    """Models on held-out 2024 races: overall, then B (fuel by lap) vs B_frac (fuel by race fraction)."""
    print("\nHeld-out 2024 races (fit on the other four), clean laps")
    results = {}
    models = (("A", False, "lap_number"), ("B", True, "lap_number"), ("B_frac", True, "race_fraction"))
    for name, include_race_lap, fuel_column in models:
        df = held_out_predictions(include_race_lap, train, fuel_column)
        df["age_bucket"] = pd.cut(df["tyre_age"], bins=AGE_BINS, labels=AGE_LABELS)
        df["lap_bucket"] = pd.cut(df["lap_number"], bins=LAP_BINS, labels=LAP_LABELS)
        result = score(df["delta"].tolist(), df["predicted"].tolist())
        print(
            f"  {name:<6}  n={len(df):>5}  "
            f"MAE={result['mae']:.3f}s  RMSE={result['rmse']:.3f}s  bias={result['bias']:+.3f}s"
        )
        results[name] = df

    for by in ("age_bucket", "lap_bucket"):
        tables = [score_by_group(results[name], by)[["mae", "bias"]].add_prefix(f"{name}_")
                  for name in ("B", "B_frac")]
        table = pd.concat(tables, axis=1)
        table["n"] = results["B"].groupby(by, observed=True).size()
        print(f"\nHeld-out 2024 by {by} (seconds)")
        print(table.round(3).to_string())

    for name in ("B", "B_frac"):
        df = results[name].assign(error=results[name]["predicted"] - results[name]["delta"])
        drift = df.pivot_table(index="lap_bucket", columns="circuit", values="error",
                               aggfunc="mean", observed=True)
        print(f"\nHeld-out 2024, Model {name} bias by lap_bucket and circuit (seconds)")
        print(drift.round(2).to_string())


def print_strategy_comparison(rows):
    """Candidate strategies ranked at each circuit's 2024 race by P_1e5 fitted on 2023+2024
    (DECISIONS 2026-11-17), then re-ranked with pit loss at q25/q75 and wear ± the 75th
    percentile of the held-out wear error."""
    inputs = fit_inputs(rows, TRAIN_YEARS)
    slopes = pd.Series(inputs["held_out_wear_errors"])
    print(f"\nHeld-out wear error, |s per lap of age| over {len(slopes)} compound-races: median "
          f"{slopes.median():.3f}, q75 {inputs['wear_range']:.3f}, max {slopes.max():.3f}; sensitivity uses ±q75")
    model = inputs["model"]
    names = model.columns_.get_feature_names_out()
    print(f"\nStrategy comparison, P_1e5 fitted on {TRAIN_YEARS}: shared wear rate "
          f"{dict(zip(names, model.coef_))['pass__tyre_age']:+.3f} s/lap")

    for circuit in sorted({row["circuit"] for row in rows}):
        result = compare_race(rows, inputs, circuit, 2024)
        settings = result["settings"]
        base = pd.DataFrame(result["ranking"])
        print(f"\n{circuit} 2024, {settings['race_distance']} laps, pit loss q25/median/q75 "
              + "/".join(f"{v:.1f}" for v in settings["pit_losses"].values()) + f" s; gap to {BASELINE} (s)")
        print(base[["rank", "strategy", "total", "gap"]].round(1).to_string(index=False))
        for row in base.itertuples():
            for flag in row.flags:
                print(f"    flag {row.strategy}: {flag}")
            if row.error:
                print(f"    {row.strategy} refused: {row.error}")

        print("  fastest strategy by pit loss (rows) and wear offset s/lap (columns):")
        print(fastest_by_scenario(result["sensitivity"]).rename(columns=lambda c: f"{c:+.3f}").to_string())


PAIR_BINS = [0, 1, 3, 5, 10, float("inf")]
PAIR_LABELS = ["0-1", "1-3", "3-5", "5-10", "10+"]


def second_half_records(rows, races, model, pit_loss, max_ages, traffic_table=None):
    """second_half_record for every comparable car in the given (year, circuit) races; with
    traffic_table, each car's real gaps and that penalty table are used (traffic on)."""
    records = []
    for year, circuit in races:
        race = [r for r in rows if r["circuit"] == circuit and r["year"] == year]
        distance = race_distance(race)
        traffic = {"gaps": real_gaps(race), "table": traffic_table} if traffic_table is not None else None
        for driver in driver_choices(rows, circuit, year):
            driver_rows = [r for r in race if r["driver_number"] == driver]
            records.append(second_half_record(driver_rows, model, distance, pit_loss[circuit]["median"], max_ages,
                                              traffic=traffic))
    return records


def print_strategy_pair_check(rows):
    """Does the simulator get the gap between two real strategies right? Pairs of cars in the same
    safety-car-free race, pace from each car's first half, scored on the second half only, with
    traffic off and on. 2023 and 2024 races are scored by a model (and traffic table) fitted on the
    other year; 2025 races by the final model."""
    races = comparable_races(rows)
    groups = {"2023-24 cross-year": {False: [], True: []}, "2025 (final model)": {False: [], True: []}}
    for year, fold_train, _ in leave_one_year_out(rows, [2023, 2024]):
        train_years = sorted({r["year"] for r in fold_train})
        model = fit_final_model(fold_train)
        pit_loss = pit_loss_by_circuit(stop_losses(fold_train, model), train_years)
        max_ages = observed_max_ages(max_clean_tyre_age(fold_train), train_years)
        table = fit_traffic_penalty(fold_train, model)
        for traffic in (False, True):
            groups["2023-24 cross-year"][traffic] += second_half_records(
                rows, [race for race in races if race[0] == year], model, pit_loss, max_ages,
                table if traffic else None)
    inputs = fit_inputs(rows, TRAIN_YEARS)
    for traffic in (False, True):
        groups["2025 (final model)"][traffic] = second_half_records(
            rows, [race for race in races if race[0] == 2025], inputs["model"], inputs["pit_loss"],
            inputs["max_ages"], inputs["traffic_table"] if traffic else None)

    print("\nStrategy pairs: predicted vs real second-half gap, each car's pace from its first half")
    for label, by_traffic in groups.items():
        for traffic, records in by_traffic.items():
            skipped = pd.Series([r["skip_reason"] for r in records if r["skip_reason"]]).value_counts().to_dict()
            pairs = pd.DataFrame(strategy_pair_errors(records))
            big = pairs[pairs["real"].abs() > 5]
            print(f"\n  {label}, traffic {'on' if traffic else 'off'}: {len(records)} cars (skipped {skipped}), "
                  f"{len(pairs)} pairs, |real| median {pairs['real'].abs().median():.1f} s")
            for name in ("predicted", "stops_only"):
                error = pairs[name] - pairs["real"]
                sign = (np.sign(big[name]) == np.sign(big["real"])).mean()
                print(f"    {name:<10} MAE {error.abs().mean():5.2f} s  bias {error.mean():+5.2f}  "
                      f"corr {pairs[name].corr(pairs['real']):+.2f}  faster one right when |real| > 5 s: {sign:.0%}")
            print(f"    {'zero':<10} MAE {pairs['real'].abs().mean():5.2f} s")
            pairs["predicted_size"] = pd.cut(pairs["predicted"].abs(), bins=PAIR_BINS, labels=PAIR_LABELS, right=False)
            pairs["right"] = np.sign(pairs["predicted"]) == np.sign(pairs["real"])
            table = pairs.groupby("predicted_size", observed=True).agg(
                n=("right", "size"), right=("right", "mean"), mae=("error", lambda e: e.abs().mean()))
            print("    by size of the predicted gap (s): share where the predicted faster car really was faster")
            print(table.round(2).to_string().replace("\n", "\n      ").join(["      ", ""]))

EMPTY_REPLAY = {"lap_times": {}, "sc_laps": set(), "laps": set(), "no_traffic_laps": set(), "pit_loss_ratio": None}


def safety_car_backtest(rows, windows):
    """Backtest records for every race with a safety car or VSC (first-half pace, traffic on), under three
    treatments of the neutralised laps: "none" (simulated as normal racing, the old behaviour), "laps"
    (the field's real lap times, normal pit loss) and "laps+stops" (also a cheaper stop under a real
    safety car). 2023 and 2024 races use a model, pit loss and ratio fitted on the other year; 2025 on
    2023+2024. Returns a list of dicts: variant, year, circuit, driver, error, skip_reason."""
    out = []
    races = sorted({(r["year"], r["circuit"]) for r in rows if "safety_car" in r["exclusion_reasons"]})
    for year, circuit in races:
        train_years = [y for y in TRAIN_YEARS if y != year]
        train = [r for r in rows if r["year"] in train_years]
        model = fit_final_model(train)
        pit_loss = pit_loss_by_circuit(stop_losses(train, model), train_years)
        lap_one = pit_loss_by_circuit(lap_one_losses(train, model), train_years)
        lap_one_all = median(r["loss"] for r in lap_one_losses(train, model) if r["loss"] is not None)
        lap_one_loss = lap_one[circuit]["median"] if circuit in lap_one else lap_one_all
        max_ages = observed_max_ages(max_clean_tyre_age(train), train_years)
        table = fit_traffic_penalty(train, model)
        sc = fit_sc_pit_loss(train, windows, pit_loss, train_years)
        race = [r for r in rows if r["year"] == year and r["circuit"] == circuit]
        for variant in ("none", "laps", "laps+stops"):
            if variant == "none":
                neutralisation = EMPTY_REPLAY
            else:
                ratio = sc["ratio"] if variant == "laps+stops" and sc else None
                neutralisation = build_neutralisation(race, windows[race[0]["session_key"]], ratio)
            for record in backtest_race(race, model, pit_loss[circuit]["median"], lap_one_loss, max_ages,
                                        "first_half", table, neutralisation):
                out.append({"variant": variant, "year": year, "circuit": circuit, "driver": record["driver_number"],
                            "error": record["error"], "skip_reason": record["skip_reason"],
                            "sc_ratio": None if sc is None else round(sc["ratio"], 2),
                            "sc_stops": None if sc is None else sc["n"]})
    return out


def print_safety_car_backtest(rows, windows):
    """Race-total error on the safety-car and VSC races with the neutralised laps replayed or not."""
    df = pd.DataFrame(safety_car_backtest(rows, windows))
    done = df[df["error"].notna()]
    print("\nSafety-car and VSC races, race-total error per car (seconds, + = predicted too slow), "
          "first-half pace, traffic on")
    for (year, circuit), g in done.groupby(["year", "circuit"]):
        ratio = g["sc_ratio"].iloc[0]
        print(f"  {circuit} {year} (SC stop ratio from training years: {ratio}, n={g['sc_stops'].iloc[0]})")
        for variant, v in g.groupby("variant", sort=False):
            print(f"    {variant:<11} n={len(v):>2}  MAE {v['error'].abs().mean():6.1f}  bias {v['error'].mean():+6.1f}  "
                  f"median |err| {v['error'].abs().median():5.1f}")
    print("  all four races:")
    for variant, v in done.groupby("variant", sort=False):
        print(f"    {variant:<11} n={len(v):>3}  MAE {v['error'].abs().mean():6.1f}  bias {v['error'].mean():+6.1f}")
    print("  skip reasons:", df[df["variant"] == "none"]["skip_reason"].value_counts().to_dict())


def print_final_test(rows):
    """The one 2025 test of the final model (P_1e5) fitted on 2023+2024, next to B_frac and the
    zero baseline. Reported, never used to choose a model (rule 4)."""
    train, test = split_by_year(rows, [2023, 2024], [2025])
    pairs = training_pairs(train)
    unseen = [row for row in test if (row["compound"], row["circuit"]) not in pairs]
    test = [row for row in test if (row["compound"], row["circuit"]) in pairs]
    print(f"\nFinal test: fit on 2023+2024 ({len(train)} rows), score 2025 ({len(test)} rows); "
          f"left out, pair not in training: {len(unseen)} rows")

    models = {"P_1e5": fit_model(True, False, train, "race_fraction", 100_000),
              "B_frac": fit_model(True, False, train, "race_fraction")}
    for flag in ("is_clean", "is_racing"):
        usable, skipped = scored_rows(test, flag)
        test_df = pd.DataFrame(usable)
        print(f"  {flag} (n={len(usable)}, skipped no delta={skipped})")
        results = {"zero": zero_baseline(usable)}
        for name, model in models.items():
            results[name] = score(test_df["delta"].tolist(), model.predict(test_df).tolist())
        for name, result in results.items():
            print(f"    {name:<7} MAE={result['mae']:.3f}s  RMSE={result['rmse']:.3f}s  bias={result['bias']:+.3f}s")

    usable, _ = scored_rows(test, "is_clean")
    test_df = pd.DataFrame(usable)
    test_df["age_bucket"] = pd.cut(test_df["tyre_age"], bins=AGE_BINS, labels=AGE_LABELS)
    for by in ("compound", "circuit", "age_bucket"):
        tables = [score_by_group(test_df.assign(predicted=0.0), by)[["mae", "bias"]].add_prefix("zero_")]
        for name, model in models.items():
            scored = test_df.assign(predicted=model.predict(test_df))
            tables.append(score_by_group(scored, by)[["mae", "bias"]].add_prefix(f"{name}_"))
        table = pd.concat(tables, axis=1)
        table["n"] = test_df.groupby(by, observed=True).size()
        print(f"\nFinal test, clean 2025 laps by {by} (seconds)")
        print(table.round(3).to_string())


def main():
    rows = load_dataset(DATASET_PATH)
    # 2023 rows are left out here; they're for cross-year validation (leave_one_year_out).
    train, test = split_by_year(rows, [2024], [2025])
    print(f"train (2024): {len(train)} rows, test (2025): {len(test)} rows")

    # No 2024 wear rate exists for these pairs, so every model skips them (DECISIONS 2026-11-13).
    pairs = training_pairs(train)
    unseen = [row for row in test if (row["compound"], row["circuit"]) not in pairs]
    test = [row for row in test if (row["compound"], row["circuit"]) in pairs]
    print(f"left out of 2025 scoring, pair not in 2024 training: {len(unseen)} rows")

    print("\nZero baseline on 2025 test races")
    for flag in ("is_clean", "is_racing"):
        usable, skipped = scored_rows(test, flag)
        result = zero_baseline(usable)
        print(
            f"  {flag:<9}  n={len(usable):>5}  skipped (no delta)={skipped}  "
            f"MAE={result['mae']:.3f}s  RMSE={result['rmse']:.3f}s  bias={result['bias']:+.3f}s"
        )

    for include_race_lap, wear_by_pair in [(False, False), (True, False), (True, True)]:
        pipeline = fit_model(include_race_lap, wear_by_pair, train)
        print(f"\nLinear model, include_race_lap = {include_race_lap}, wear_by_pair = {wear_by_pair}, on 2025 test races")
        for flag in ("is_clean", "is_racing"):
            usable, skipped = scored_rows(test, flag)
            test_df = pd.DataFrame(usable)
            predicted = pipeline.predict(test_df).tolist()
            actual = test_df['delta'].tolist()
            result = score(actual, predicted)
            print(
                f"  {flag:<9}  n={len(usable):>5}  skipped (no delta)={skipped}  "
                f"MAE={result['mae']:.3f}s  RMSE={result['rmse']:.3f}s  bias={result['bias']:+.3f}s"
            )

    print_slices(train, test)
    print_held_out_2024(train)
    print_cross_year(rows)
    print_cross_year_backtest(rows)
    print_error_split(rows)
    print_residual_trends(rows)
    print_strategy_comparison(rows)
    print_final_test(rows)
    print_strategy_pair_check(rows)
    print_safety_car_backtest(rows, load_neutralisations(NEUTRALISATIONS_PATH))


if __name__ == "__main__":
    main()
