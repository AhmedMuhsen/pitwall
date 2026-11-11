from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from pitwall.ingestion import load_or_fetch

from pitwall.processing import build_race_rows, keep_dataset_columns, race_quality, quality_markdown

OUTPUT_PATH = Path("data/processed/lap_dataset.parquet")
REPORT_PATH = Path("docs/DATA_QUALITY.md")

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
    report = {}
    for session_key, (circuit, year) in SESSIONS.items():
        laps = load_or_fetch('laps', session_key)
        stints = load_or_fetch('stints', session_key)
        race_control = load_or_fetch('race_control', session_key)
        race_rows = keep_dataset_columns(build_race_rows(laps, stints, race_control, circuit, year))
        report[f"{circuit} {year}"] = race_quality(race_rows)
        all_rows.extend(race_rows)

    for total_year in [2024, 2025]:
        year_rows = [row for row in all_rows if row['year'] == total_year]
        report[f"All {total_year}"] = race_quality(year_rows)
    report["All races"] = race_quality(all_rows)

    pq.write_table(pa.Table.from_pylist(all_rows), OUTPUT_PATH)
    if pq.read_table(OUTPUT_PATH).to_pylist() != all_rows:
        raise ValueError(f"{OUTPUT_PATH} does not match the rows that were written")
    print(f"Wrote {len(all_rows)} rows to {OUTPUT_PATH}")

    REPORT_PATH.write_text(quality_markdown(report), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")

if __name__ == "__main__":
    main()