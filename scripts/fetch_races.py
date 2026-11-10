import time
from pitwall.ingestion import cache_path, load_or_fetch
SESSIONS = {
    # 2024: training
    9472: "Bahrain 2024",
    9566: "Hungary 2024",
    9590: "Italy (Monza) 2024",
    9606: "Singapore 2024",
    9662: "Abu Dhabi 2024",
    # 2025: test
    10014: "Bahrain 2025",
    9928: "Hungary 2025",
    9912: "Italy (Monza) 2025",
    9896: "Singapore 2025",
    9839: "Abu Dhabi 2025",
}
ENDPOINTS_TO_FETCH = ["laps", "stints", "race_control"]
WAIT_SECONDS = 3

def main():
    requests = 0
    for (session_key, name) in SESSIONS.items():
        for endpoint in ENDPOINTS_TO_FETCH:
            was_cached = cache_path(endpoint, session_key).exists()
            data = load_or_fetch(endpoint, session_key)
            print(name, endpoint, len(data), "cached" if was_cached else "fetched")
            if not was_cached:
                requests += 1
                time.sleep(WAIT_SECONDS) 
    print(f"Requests made: {requests}")

if __name__ == "__main__":
    main()