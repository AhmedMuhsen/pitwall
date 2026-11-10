from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from pitwall.ingestion import load_or_fetch

from pitwall.processing import build_race_rows, keep_dataset_columns

OUTPUT_PATH = Path("data/processed/lap_dataset.parquet")

SESSIONS = {
    9472: ("Sakhir", 2024),
    9566: ("Hungaroring", 2024),
    9590: ("Monza", 2024),
    9606: ("Singapore", 2024),
    9662: ("Yas Marina Circuit", 2024),
    10014: ("Sakhir", 2025),
    9928: ("Hungaroring", 2025),
    9912: ("Monza", 2025),
    9896: ("Singapore", 2025),
    9839: ("Yas Marina Circuit", 2025),
}


def main():
    all_rows = []
    for session_key, (circuit, year) in SESSIONS.items():
        laps = load_or_fetch('laps', session_key)
        stints = load_or_fetch('stints', session_key)
        race_control = load_or_fetch('race_control', session_key)
        race_rows = build_race_rows(laps, stints, race_control, circuit, year)
        clean_count = 0
        racing_count = 0
        for row in race_rows:
            if row['is_clean']:
                clean_count += 1
            if row['is_racing']:
                racing_count += 1
        print(circuit, year, len(race_rows), clean_count, racing_count)
        all_rows.extend(race_rows)

    for total_year in [2024, 2025]:
        total_rows = 0
        total_clean = 0
        total_racing = 0
        for row in all_rows:
            if row['year'] != total_year:
                continue
            total_rows += 1
            if row['is_clean']:
                total_clean += 1
            if row['is_racing']:
                total_racing += 1
        print(total_year, total_rows, total_clean, total_racing)
    print(len(all_rows))

    dataset_rows = keep_dataset_columns(all_rows)
    pq.write_table(pa.Table.from_pylist(dataset_rows), OUTPUT_PATH)
    if pq.read_table(OUTPUT_PATH).to_pylist() != dataset_rows:
        raise ValueError(f"{OUTPUT_PATH} does not match the rows that were written")
    print(f"Wrote {len(dataset_rows)} rows to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()