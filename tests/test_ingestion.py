import io
import urllib.error
from pitwall.ingestion import fetch_endpoint
import pytest



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