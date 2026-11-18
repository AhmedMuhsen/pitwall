"""Writes data/processed/driver_names.json from the cached /drivers files (fetch_races.py first)."""
import json
from pathlib import Path

import pyarrow.parquet as pq

from pitwall.ingestion import cache_path
from pitwall.processing import build_driver_names

DATASET_PATH = Path("data/processed/lap_dataset.parquet")
OUTPUT_PATH = Path("data/processed/driver_names.json")


def main():
    sessions = sorted(set(pq.read_table(DATASET_PATH, columns=["session_key"]).column("session_key").to_pylist()))
    table = {}
    for session_key in sessions:
        path = cache_path("drivers", session_key)
        if not path.exists():
            print(f"session {session_key}: no cached drivers file, skipped")
            continue
        names = build_driver_names(json.loads(path.read_text(encoding="utf-8")))
        table[str(session_key)] = {str(number): value for number, value in names.items()}
        print(f"session {session_key}: {len(names)} drivers")
    OUTPUT_PATH.write_text(json.dumps(table, indent=1), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH} ({len(table)} sessions)")


if __name__ == "__main__":
    main()
