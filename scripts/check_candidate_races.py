"""Exploration script: which non-sprint Grands Prix were dry and safety-car-free?

Reads the saved sessions files, fetches weather and race control for each
candidate session (skipping files already saved), and prints one row per race.
Not the real ingestion code; that gets designed in its own session.
"""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

RAW = Path("data/raw")
API = "https://api.openf1.org/v1"
WAIT_SECONDS = 3  # free tier allows 30 requests/minute
YEARS = [2024, 2025]


def load(name):
    return json.loads((RAW / name).read_text())


def candidate_sessions():
    """Return race session records for circuits with no sprint in any year."""
    sprint_circuits = set()
    races = []
    for year in YEARS:
        sprint_circuits |= {s["circuit_key"] for s in load(f"sprint_sessions_{year}.json")}
        races += load(f"sessions_{year}.json")
    return [r for r in races if r["circuit_key"] not in sprint_circuits]


def fetch_if_missing(endpoint, session_key):
    """Save one unfiltered response. Raises on an HTTP error or a non-list body."""
    path = RAW / f"{endpoint}_{session_key}.json"
    if path.exists():
        return
    url = f"{API}/{endpoint}?session_key={session_key}"
    with urllib.request.urlopen(url, timeout=30) as response:
        body = response.read()
    if not isinstance(json.loads(body), list):
        raise ValueError(f"{url} did not return a list: {body[:200]!r}")
    path.write_bytes(body)
    time.sleep(WAIT_SECONDS)


def summarise(session):
    """Return one race's rain and disruption facts from its saved files."""
    key = session["session_key"]
    weather = load(f"weather_{key}.json")
    control = load(f"race_control_{key}.json")
    messages = [m for m in control if m["category"] == "SafetyCar"]
    return {
        "year": session["year"],
        "circuit": session["circuit_short_name"],
        "session_key": key,
        "weather_readings": len(weather),
        "rain_readings": sum(1 for w in weather if w["rainfall"]),
        "safety_car": [m["lap_number"] for m in messages if m["message"].upper().startswith("SAFETY CAR DEPLOYED")],
        "virtual_sc": [m["lap_number"] for m in messages if m["message"].upper().startswith("VIRTUAL SAFETY CAR DEPLOYED")],
        "red_flag": [m["lap_number"] for m in control if m.get("flag") == "RED"],
    }


def main():
    sessions = candidate_sessions()
    print(f"{len(sessions)} candidate sessions")
    for session in sessions:
        for endpoint in ["weather", "race_control"]:
            try:
                fetch_if_missing(endpoint, session["session_key"])
            except (urllib.error.URLError, ValueError) as error:
                raise SystemExit(f"Stopped at {endpoint} {session['session_key']}: {error}. Re-run to resume.")

    for row in sorted(map(summarise, sessions), key=lambda r: (r["circuit"], r["year"])):
        print(row)


if __name__ == "__main__":
    main()
