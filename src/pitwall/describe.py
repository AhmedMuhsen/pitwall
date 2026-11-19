"""Plain-language text for strategies and times, shared by the app and the agent."""


def plain(strategy: dict) -> str:
    '''
    A strategy in words.

    strategy: dict with "compounds", "pit_laps" and optional "start_ages" (a stint starting on a used set is marked)
    returns: e.g. "2 stops: Medium → Hard → Hard, laps 23 & 46"
    '''
    ages = strategy.get("start_ages", [0] * len(strategy["compounds"]))
    stints = [c.title() + (" (used)" if age else "") for c, age in zip(strategy["compounds"], ages)]
    stops = [str(p) for p in strategy["pit_laps"]]
    laps = stops[0] if len(stops) == 1 else ", ".join(stops[:-1]) + " & " + stops[-1]
    count = len(stops)
    return f"{count} stop{'s' if count != 1 else ''}: {' → '.join(stints)}, lap{'s' if count != 1 else ''} {laps}"


def race_clock(seconds: float) -> str:
    '''Seconds as a race time: 5531.2 -> "1:32:11.2".'''
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours}:{minutes:02d}:{secs:04.1f}"
