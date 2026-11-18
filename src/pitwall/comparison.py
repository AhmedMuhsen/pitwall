"""Compares a small set of strategies with the simulator and tests how assumptions change the ranking."""
from pitwall.simulator import simulate, validate_strategy


def candidate_strategies(race_distance: int) -> dict[str, dict]:
    '''
    The fixed set of strategies compared at every circuit (Week 7).

    race_distance: number of laps in the race

    returns: dict name -> strategy (new sets only), pit laps as a share of the
    race, rounded down:
        "1stop_MH_early": MEDIUM -> HARD, pit at 35%
        "1stop_MH_late":  MEDIUM -> HARD, pit at 50%
        "1stop_HM":       HARD -> MEDIUM, pit at 60%
        "2stop_MHH":      MEDIUM -> HARD -> HARD, pits at 33% and 67%
        "2stop_SHH":      SOFT -> HARD -> HARD, pits at 25% and 60%
    Chosen from what drivers ran in 2023-2024 at these circuits (mostly
    MEDIUM -> HARD, one or two stops, a SOFT start at Sakhir and Hungaroring),
    plus one reverse order. It is a small set to compare, not a search.

    raises ValueError if the race is too short for every strategy to have
    distinct pit laps (validate_strategy's message).
    '''
    d = race_distance
    strategies = {
        "1stop_MH_early": {"compounds": ["MEDIUM", "HARD"], "pit_laps": [d * 35 // 100]},
        "1stop_MH_late": {"compounds": ["MEDIUM", "HARD"], "pit_laps": [d * 50 // 100]},
        "1stop_HM": {"compounds": ["HARD", "MEDIUM"], "pit_laps": [d * 60 // 100]},
        "2stop_MHH": {"compounds": ["MEDIUM", "HARD", "HARD"], "pit_laps": [d // 3, d * 2 // 3]},
        "2stop_SHH": {"compounds": ["SOFT", "HARD", "HARD"], "pit_laps": [d * 25 // 100, d * 60 // 100]},
    }
    for strategy in strategies.values():
        validate_strategy(strategy, race_distance)
    return strategies


def compare_strategies(strategies: dict[str, dict], race_distance: int, circuit: str, model,
                       reference_lap: float, pit_loss: float, lap_one_loss: float, max_ages: dict,
                       baseline: str, wear_offset: float = 0.0) -> list[dict]:
    '''
    Simulated total time of each strategy, ranked, with the gap to a baseline strategy.

    strategies: dict name -> strategy, as in simulator.strategy_laps
    race_distance, circuit, model, reference_lap, pit_loss, lap_one_loss,
        max_ages: as in simulator.simulate
    baseline: name of the strategy the gaps are measured against
    wear_offset: extra wear in seconds per lap of tyre age, added to every
        compound (sensitivity test). The model is linear in tyre age, so this
        adds wear_offset * sum(tyre_age) to the total.

    returns: one dict per strategy, fastest first, with "strategy", "total"
    (seconds), "gap" (total minus the baseline's; positive = slower), "rank"
    (1 = fastest), "flags" (stint_range_flags messages) and "error". A
    strategy the simulator refuses keeps a row at the end with total, gap and
    rank None and the message in "error".

    raises ValueError if baseline isn't in strategies or can't be simulated.
    '''
    if baseline not in strategies:
        raise ValueError(f"Baseline {baseline!r} is not one of {sorted(strategies)}")
    results = []
    for name, strategy in strategies.items():
        row = {"strategy": name, "total": None, "gap": None, "rank": None, "flags": [], "error": None}
        try:
            sim = simulate(strategy, race_distance, circuit, model, reference_lap,
                           pit_loss, lap_one_loss, max_ages)
        except ValueError as e:
            row["error"] = str(e)
        else:
            row["total"] = sim["total_time"] + wear_offset * float(sim["laps"]["tyre_age"].sum())
            row["flags"] = sim["flags"]
        results.append(row)

    totals = {row["strategy"]: row["total"] for row in results}
    if totals[baseline] is None:
        raise ValueError(f"Baseline {baseline!r} can't be simulated: "
                         f"{next(r['error'] for r in results if r['strategy'] == baseline)}")
    ranked = sorted((r for r in results if r["total"] is not None), key=lambda r: r["total"])
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
        row["gap"] = row["total"] - totals[baseline]
    return ranked + [r for r in results if r["total"] is None]


def sensitivity(strategies: dict[str, dict], race_distance: int, circuit: str, model,
                reference_lap: float, pit_losses: dict[str, float], lap_one_loss: float,
                max_ages: dict, baseline: str, wear_offsets: list[float]) -> list[dict]:
    '''
    compare_strategies rerun for every pit-loss value and wear offset.

    pit_losses: dict label -> pit loss in seconds, e.g. {"q25": 20.1,
        "median": 21.0, "q75": 22.4} from analysis.pit_loss_by_circuit
    wear_offsets: extra wear values in seconds per lap of age, e.g.
        [-0.05, 0.0, 0.05]
    other arguments: as in compare_strategies

    returns: compare_strategies rows, each with "pit_loss_label", "pit_loss"
    and "wear_offset" added, for every (pit loss, wear offset) scenario.

    raises ValueError as compare_strategies does.
    '''
    rows = []
    for label, pit_loss in pit_losses.items():
        for offset in wear_offsets:
            for row in compare_strategies(strategies, race_distance, circuit, model, reference_lap,
                                          pit_loss, lap_one_loss, max_ages, baseline, offset):
                rows.append({"pit_loss_label": label, "pit_loss": pit_loss, "wear_offset": offset, **row})
    return rows
