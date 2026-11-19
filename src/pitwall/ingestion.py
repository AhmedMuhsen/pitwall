import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENDPOINTS = {"laps", "stints", "race_control", "weather", "pit", "drivers"}
API = "https://api.openf1.org/v1"
RAW_DIR = Path("data/raw")

def fetch_endpoint(endpoint: str, session_key: int) -> list:
    '''
    Fetches results using the endpoint.
    Checks if endpoint is valid.
    Uses session key.
    Returns [] when OpenF1 reports no results.
    '''
    if endpoint not in ENDPOINTS:
        raise ValueError(f"{endpoint} isn't a valid endpoint. Valid endpoints: {sorted(ENDPOINTS)}")
    url = f"{API}/{endpoint}?session_key={session_key}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404 and json.loads(error.read()) == {"detail":"No results found."}:
            return []
        else:
            raise
    data = json.loads(body)
    if not isinstance(data, list):
        raise ValueError(f"{url} did not return a list: {body[:200]!r}")
    return data

def cache_path(endpoint: str, session_key:int, raw_dir: Path = RAW_DIR) -> Path:
    '''Returns cache path'''
    return raw_dir/f"{endpoint}_{session_key}.json"


def load_or_fetch(endpoint: str, session_key: int, raw_dir: Path = RAW_DIR) -> list:
    '''
    Returns the records for one endpoint and session, from the cache if saved.
    On a cache miss, fetches with fetch_endpoint, saves the records to
    raw_dir/<endpoint>_<session_key>.json and a sidecar .meta.json recording
    the request and when it was made. Empty results are cached too.
    '''
    path = cache_path(endpoint, session_key, raw_dir)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return data
    data = fetch_endpoint(endpoint, session_key)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    meta = {
        "endpoint": endpoint,
        "params": {"session_key": session_key},
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "records": len(data),
    }
    with open(path.with_suffix(".meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return data


def race_sessions(raw_dir: Path = RAW_DIR, years: tuple[int, ...] = (2023, 2024, 2025)) -> list[dict]:
    '''
    The Grand Prix race sessions OpenF1 lists, from the cached sessions_<year>.json files.

    raw_dir: folder holding sessions_<year>.json (OpenF1 /sessions?year=...&session_name=Race)
    years: seasons to read; OpenF1 has no data before 2023

    returns: one dict per race, oldest first, with "session_key", "year", "circuit"
    (OpenF1's circuit_short_name, e.g. "Yas Marina Circuit"), "date" (race start, ISO string)
    and "meeting_key". Cancelled sessions and sessions that aren't a "Race" are left out.

    raises FileNotFoundError if a year's file is missing, ValueError if two races share a session_key.
    '''
    races = []
    for year in years:
        with open(raw_dir / f"sessions_{year}.json", encoding="utf-8") as f:
            for session in json.load(f):
                if session["session_name"] == "Race" and not session.get("is_cancelled"):
                    races.append({"session_key": session["session_key"], "year": session["year"],
                                  "circuit": session["circuit_short_name"], "date": session["date_start"],
                                  "meeting_key": session["meeting_key"]})
    keys = [race["session_key"] for race in races]
    if len(keys) != len(set(keys)):
        raise ValueError("Two races share a session_key")
    return sorted(races, key=lambda race: race["date"])
