import urllib.request
import urllib.error
import json

ENDPOINTS = {"laps", "stints", "race_control", "weather"}
API = "https://api.openf1.org/v1"


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