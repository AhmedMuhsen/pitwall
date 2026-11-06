import urllib.request
import urllib.error
import json
from datetime import datetime, timezone
from pathlib import Path


ENDPOINTS = {"laps", "stints", "race_control", "weather"}
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
