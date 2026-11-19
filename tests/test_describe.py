from pitwall.describe import plain, race_clock


def test_plain_describes_stops_compounds_and_used_sets():
    assert plain({"compounds": ["MEDIUM", "HARD", "HARD"], "pit_laps": [23, 46]}) == \
        "2 stops: Medium → Hard → Hard, laps 23 & 46"
    assert plain({"compounds": ["SOFT", "HARD"], "pit_laps": [17], "start_ages": [3, 0]}) == \
        "1 stop: Soft (used) → Hard, lap 17"


def test_race_clock():
    assert race_clock(5531.2) == "1:32:11.2"
    assert race_clock(59.04) == "0:00:59.0"
    assert race_clock(3600.0) == "1:00:00.0"
