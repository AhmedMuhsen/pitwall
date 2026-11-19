import io
import json
import urllib.error

import pytest

from pitwall.ingestion import fetch_endpoint, load_or_fetch


def test_incorrect_endpoint():
    with pytest.raises(ValueError): 
        fetch_endpoint("lapz", 9566)

def test_valid_call(monkeypatch):
    def fake_urlopen(url, timeout=30):
        return io.BytesIO(b'[{"lap_number": 1}]')
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = fetch_endpoint("laps", 9566)

    assert result == [{"lap_number": 1}]

def test_no_data(monkeypatch):
    def fake_urlopen(url, timeout=30):
        raise urllib.error.HTTPError(
            url, 404, "Not Found", {}, io.BytesIO(b'{"detail":"No results found."}')
        )
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = fetch_endpoint("laps", 1)

    assert result == []
    
def test_http_errors(monkeypatch):
    def fake_urlopen(url, timeout=30):
        raise urllib.error.HTTPError(
            url, 500, "Internal Server Error", {}, io.BytesIO(b'{"detail":"Server error"}')
        )
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(urllib.error.HTTPError):
        fetch_endpoint("laps", 9566)

def test_not_a_list(monkeypatch):
    def fake_urlopen(url, timeout=30):
        return io.BytesIO(b'{"lap_number": 1}')
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(ValueError, match = "did not return a list"):
        fetch_endpoint("laps", 9566)

def test_cache_hit_does_not_fetch(monkeypatch, tmp_path):
    (tmp_path / "laps_9566.json").write_text('[{"lap_number": 7}]')

    def fake_fetch(endpoint, session_key):
        raise AssertionError("fetch_endpoint should not be called on a cache hit")
    monkeypatch.setattr("pitwall.ingestion.fetch_endpoint", fake_fetch)
    result = load_or_fetch("laps", 9566, raw_dir=tmp_path)

    assert result == [{"lap_number": 7}]

def test_cache_miss(monkeypatch, tmp_path):

    def fake_fetch(endpoint, session_key):
        return [{"lap_number": 7}]
    monkeypatch.setattr("pitwall.ingestion.fetch_endpoint", fake_fetch)
    result = load_or_fetch("laps", 9566, raw_dir=tmp_path)

    saved = json.loads((tmp_path / "laps_9566.json").read_text())
    meta = json.loads((tmp_path/"laps_9566.meta.json").read_text())

    assert meta["records"] == 1
    assert meta["endpoint"] == "laps"
    assert saved == [{"lap_number": 7}]
    assert result == [{"lap_number": 7}]




def test_race_sessions_reads_cached_files_and_skips_sprints_and_cancelled(tmp_path):
    import json

    from pitwall.ingestion import race_sessions

    def session(key, name, date, circuit="Monza", cancelled=False, year=2024):
        return {"session_key": key, "session_name": name, "date_start": date, "circuit_short_name": circuit,
                "year": year, "meeting_key": key // 10, "is_cancelled": cancelled}
    (tmp_path / "sessions_2024.json").write_text(json.dumps([
        session(2, "Race", "2024-09-01T13:00:00+00:00"), session(1, "Race", "2024-03-02T15:00:00+00:00", "Sakhir"),
        session(3, "Sprint", "2024-04-20T04:00:00+00:00"), session(4, "Race", "2024-05-01T13:00:00+00:00", cancelled=True)]))

    races = race_sessions(tmp_path, years=(2024,))

    assert [(r["session_key"], r["circuit"]) for r in races] == [(1, "Sakhir"), (2, "Monza")]   # oldest first
    assert set(races[0]) == {"session_key", "year", "circuit", "date", "meeting_key"}


def test_race_sessions_rejects_duplicate_keys_and_missing_files(tmp_path):
    import json

    import pytest

    from pitwall.ingestion import race_sessions
    row = {"session_key": 1, "session_name": "Race", "date_start": "2024-03-02T15:00:00+00:00",
           "circuit_short_name": "Sakhir", "year": 2024, "meeting_key": 1}
    (tmp_path / "sessions_2024.json").write_text(json.dumps([row, row]))

    with pytest.raises(ValueError, match="share a session_key"):
        race_sessions(tmp_path, years=(2024,))
    with pytest.raises(FileNotFoundError):
        race_sessions(tmp_path, years=(2025,))
