"""Exploration script: does the lap/stint join hold up on Mexico 2024 (session 9625)?

Reads the saved laps and stints files and prints row counts and every lap with
no matching stint. Run from the repo root:
    PYTHONPATH=src uv run python scripts/check_mexico_join.py
"""

import json
from pathlib import Path

from pitwall.analysis import average_lap_time_by_tyre_age
from pitwall.processing import add_stint_data

laps = json.loads(Path("data/raw/laps_9625.json").read_text())
stints = json.loads(Path("data/raw/stints_9625.json").read_text())

result = add_stint_data(laps, stints)

unmatched = [lap for lap in result if lap["tyre_age"] is None]
no_duration = [lap for lap in result if lap["lap_duration"] is None]
both = [lap for lap in unmatched if lap["lap_duration"] is None]

print(f"Laps in: {len(laps)}, laps out: {len(result)}")
print(f"Unmatched laps (no stint): {len(unmatched)}")
for lap in unmatched:
    print(f"  driver {lap['driver_number']}, lap {lap['lap_number']}, lap_duration {lap['lap_duration']}")
print(f"Laps with no lap_duration: {len(no_duration)}")
for lap in no_duration:
    print(f"  driver {lap['driver_number']}, lap {lap['lap_number']}, tyre_age {lap['tyre_age']}")
print(f"Laps with neither a stint nor a lap_duration: {len(both)}")


# testing with average_lap_time_by_tyre_age
averages = average_lap_time_by_tyre_age(result)
for age, average in sorted(averages.items()):
    print(age, round(average, 3))