"""Caches the OpenF1 data of every Grand Prix in 2023-2025 (the regulation period OpenF1 covers).
Resumable: cached responses are skipped, so a failed or interrupted run can simply be repeated."""
import time
import urllib.error

from pitwall.ingestion import cache_path, load_or_fetch, race_sessions

ENDPOINTS_TO_FETCH = ["laps", "stints", "race_control", "weather", "drivers"]
WAIT_SECONDS = 3


def main():
    requests, failures = 0, []
    races = race_sessions()
    for race in races:
        name = f"{race['circuit']} {race['year']}"
        for endpoint in ENDPOINTS_TO_FETCH:
            was_cached = cache_path(endpoint, race["session_key"]).exists()
            try:
                data = load_or_fetch(endpoint, race["session_key"])
            except (urllib.error.URLError, ValueError) as error:
                failures.append((name, endpoint, str(error)))
                print(name, endpoint, "FAILED:", error, flush=True)
                time.sleep(WAIT_SECONDS)
                continue
            print(name, endpoint, len(data), "cached" if was_cached else "fetched", flush=True)
            if not was_cached:
                requests += 1
                time.sleep(WAIT_SECONDS)
    print(f"Races: {len(races)}. Requests made: {requests}. Failures: {len(failures)}")
    for failure in failures:
        print("  ", failure)


if __name__ == "__main__":
    main()
