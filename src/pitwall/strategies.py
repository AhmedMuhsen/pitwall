"""Candidate strategies: the standard set to compare, a user's own strategy, and the safety-car candidate."""


from pitwall.simulator import validate_strategy

# Final model and training years: DECISIONS 2026-11-17 and 2026-11-18.


BASELINE = "1stop_MH_early"


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


def with_start_ages(candidate: dict, actual: dict) -> dict:
    """candidate with start_ages: the first set keeps the real first set's age if it is the same
    compound (everyone starts on the tyres they qualified on); every later set is new."""
    first_age = actual["start_ages"][0] if candidate["compounds"][0] == actual["compounds"][0] else 0
    return {**candidate, "start_ages": [first_age] + [0] * (len(candidate["compounds"]) - 1)}


def custom_strategy(compounds: list[str], pit_laps: list[int], race_distance: int) -> dict:
    '''
    A user-typed strategy, checked.

    compounds: tyre compound of each stint in order, e.g. ["MEDIUM", "HARD"]
    pit_laps: the lap each stop is made on (the in-lap), one fewer than compounds
    race_distance: laps in the race

    returns: {"compounds": ..., "pit_laps": ...}, ready for compare_driver(custom=...)
    raises ValueError with a message the user can act on (simulator.validate_strategy):
    unknown compound, fewer than two different dry compounds, wrong number of pit
    laps, pit laps out of order or outside the race.
    '''
    strategy = {"compounds": [c.upper() for c in compounds], "pit_laps": [int(p) for p in pit_laps]}
    validate_strategy(strategy, race_distance)
    return strategy


def safety_car_candidate(windows: list[dict], race_distance: int) -> dict | None:
    '''
    "Pit under the safety car": one stop, MEDIUM -> HARD, on the first full lap after the
    first real safety car was deployed (the stop is then made under it).

    windows: neutralisation.neutralised_windows of the race
    race_distance: laps in the race
    returns: the strategy dict, or None if the race had no real safety car (a virtual one
    doesn't make a stop cheaper) or the stop would not leave a valid strategy.
    '''
    safety_cars = [w for w in windows if w["kind"] == "SC"]
    if not safety_cars:
        return None
    window = safety_cars[0]
    lap = min(window["start"] + 1, window["end"])
    strategy = {"compounds": ["MEDIUM", "HARD"], "pit_laps": [lap]}
    try:
        validate_strategy(strategy, race_distance)
    except ValueError:
        return None
    return strategy
