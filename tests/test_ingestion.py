import io
import urllib.error
from pitwall.ingestion import fetch_endpoint, load_or_fetch
import pytest
import json


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


