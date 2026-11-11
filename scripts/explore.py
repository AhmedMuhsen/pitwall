from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # write files only, never open a window
import matplotlib.pyplot as plt
import pyarrow.parquet as pq

from pitwall.analysis import median_clean_lap_by_race_lap

DATASET_PATH = Path("data/processed/lap_dataset.parquet")
FIGURES_DIR = Path("docs/figures")

SESSION_KEY = 9566  # Hungaroring 2024: no safety car, most clean laps of the 2024 races
RACE_LABEL = "Hungaroring 2024"
STINTS_PER_COMPOUND = 2
MIN_CLEAN_LAPS = 8  # shorter stints are too noisy to show a trend

COMPOUND_COLOURS = {"SOFT": "tab:red", "MEDIUM": "tab:orange", "HARD": "tab:gray"}


def longest_clean_stints(rows, session_key):
    """Clean laps of the longest stints per compound in one race.

    Returns a list of (driver_number, stint_number, compound, laps), with laps
    sorted by tyre age. Keeps up to STINTS_PER_COMPOUND stints per compound,
    each with at least MIN_CLEAN_LAPS clean laps.
    """
    stints = defaultdict(list)
    for row in rows:
        if row["session_key"] == session_key and row["is_clean"]:
            key = (row["driver_number"], row["stint_number"], row["compound"])
            stints[key].append(row)

    chosen = []
    for compound in COMPOUND_COLOURS:
        candidates = [
            (key, laps) for key, laps in stints.items()
            if key[2] == compound and len(laps) >= MIN_CLEAN_LAPS
        ]
        candidates.sort(key=lambda item: len(item[1]), reverse=True)
        for key, laps in candidates[:STINTS_PER_COMPOUND]:
            chosen.append((*key, sorted(laps, key=lambda lap: lap["tyre_age"])))
    return chosen


def plot_tyre_age(rows, path):
    fig, ax = plt.subplots(figsize=(9, 5))
    for driver, stint, compound, laps in longest_clean_stints(rows, SESSION_KEY):
        ax.plot(
            [lap["tyre_age"] for lap in laps],
            [lap["lap_duration"] for lap in laps],
            marker="o", markersize=3, color=COMPOUND_COLOURS[compound],
            label=f"#{driver} stint {stint} ({compound}, {len(laps)} laps)",
        )
    ax.set_xlabel("Tyre age (laps)")
    ax.set_ylabel("Lap time (s)")
    ax.set_title(f"{RACE_LABEL}: clean lap time vs tyre age, longest stints")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_race_lap(rows, path):
    medians = median_clean_lap_by_race_lap(rows, SESSION_KEY)
    laps = sorted(medians)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(laps, [medians[lap] for lap in laps], marker="o", markersize=3)
    ax.set_xlabel("Race lap")
    ax.set_ylabel("Median clean lap time (s)")
    ax.set_title(f"{RACE_LABEL}: median clean lap time across drivers vs race lap")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main():
    rows = pq.read_table(DATASET_PATH).to_pylist()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plot_tyre_age(rows, FIGURES_DIR / "hungaroring_2024_tyre_age.png")
    plot_race_lap(rows, FIGURES_DIR / "hungaroring_2024_race_lap.png")
    print(f"Wrote figures to {FIGURES_DIR}")


if __name__ == "__main__":
    main()
