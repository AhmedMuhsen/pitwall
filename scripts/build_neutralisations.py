"""Writes data/processed/neutralisations.json (safety-car and VSC windows per race) from the cached
race_control files (fetch_races.py first)."""
import json
from pathlib import Path

import pyarrow.parquet as pq

from pitwall.ingestion import cache_path
from pitwall.neutralisation import neutralised_windows

DATASET_PATH = Path("data/processed/lap_dataset.parquet")
OUTPUT_PATH = Path("data/processed/neutralisations.json")


def main():
    sessions = sorted(set(pq.read_table(DATASET_PATH, columns=["session_key"]).column("session_key").to_pylist()))
    table = {}
    for session_key in sessions:
        path = cache_path("race_control", session_key)
        if not path.exists():
            print(f"session {session_key}: no cached race_control file, skipped")
            continue
        windows = neutralised_windows(json.loads(path.read_text(encoding="utf-8")))
        table[str(session_key)] = windows
        print(f"session {session_key}: {windows if windows else 'none'}")
    OUTPUT_PATH.write_text(json.dumps(table, indent=1), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH} ({len(table)} sessions)")


if __name__ == "__main__":
    main()
