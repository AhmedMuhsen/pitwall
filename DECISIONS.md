# DECISIONS

One entry per real decision. Format:

- **Decision** — what was decided
- **Requirement** — what forced the choice
- **Options** — what was considered
- **Choice and reason** — what was picked and why
- **What would make us reconsider** — the signal that would reopen it

---

## 2026-10-30 — Environment tooling: uv + pyproject.toml

- **Decision** — Manage the Python environment with `uv` and `pyproject.toml`,
  on a uv-managed CPython 3.13 pinned in `.python-version`.
- **Requirement** — A reproducible environment that someone else (or a
  deployment target) can recreate, without coupling it to my local conda
  install.
- **Options** — (a) `venv` + `requirements.txt`: stdlib only, matches what most
  deploy targets expect, but no lockfile. (b) `uv` + `pyproject.toml`: fast,
  real lockfile, standard metadata, one more tool to learn. (c) `conda`: good
  for scientific binaries, but heavy and we have no binary problem.
- **Choice and reason** — uv. Wanted the lockfile and the standard
  `pyproject.toml` metadata, and I'd rather learn the tool new projects are
  actually using. Set `python-preference = "only-managed"` after uv's first
  sync picked up miniconda's interpreter.
- **What would make us reconsider** — If the AWS deploy target makes uv
  awkward, exporting a `requirements.txt` is a one-command fallback. Also
  pinned 3.13 rather than 3.14 because I have **not** verified that pyarrow,
  scikit-learn and streamlit all ship 3.14 wheels; bump once that's checked.

## 2026-10-30 — Empty input to `average_lap_time_by_tyre_age` raises

- **Decision** — Raise `ValueError` on an empty `laps` list rather than
  returning an empty dict.
- **Requirement** — Decide whether no-laps is a normal outcome or a bug.
- **Options** — (a) return `{}`: caller needs no special case, empty results
  flow through silently. (b) raise `ValueError`: fails loudly at the point of
  the problem, every caller must handle it. (c) return `None`: crashes the
  caller later with no useful message — rejected.
- **Choice and reason** — Raise. Right now an empty list almost certainly means
  data loading or caching failed, and I want to hear about that immediately
  rather than see an empty plot and go hunting through the model.
- **What would make us reconsider** — Once laps are filtered to clean laps per
  driver/compound/circuit, some groups will legitimately be empty, and every
  caller wrapping this in `try`/`except` is the signal to switch to returning
  `{}` and let the caller decide.

## 2026-10-30 — Lap records are a list of dicts, not a DataFrame

- **Decision** — Analysis functions at this layer take a list of dicts, one per
  lap, and read only the keys they need.
- **Requirement** — Inputs that can be written literally in a test and totalled
  by hand.
- **Options** — (a) list of dicts: hand-checkable, no pandas semantics in the
  way. (b) pandas DataFrame: closer to the eventual dataset layer, but the
  arithmetic hides behind groupby and tests get harder to verify by eye.
- **Choice and reason** — List of dicts. The point of this function is a test
  whose expected values I calculated on paper. Also rejected keying by lap
  number: lap 5 is not unique — twenty drivers each have one — so the row grain
  is (session, driver, lap).
- **What would make us reconsider** — The processed dataset layer will be
  pandas/parquet. Pandas enters when we're operating on whole races at once,
  not at this function's level.

## 2026-11-03 — Rain and safety cars: no modelling in v1, safety-car replay later

- **Decision** — v1 does not model rain or safety cars. Once the backtest works
  on clean races, add a clearly labelled extension that replays a race's real
  safety car.
- **Requirement** — Real races have safety cars and rain, and the project has to
  be defensible about how it treats them.
- **Options** — (a) No modelling, limitation stated. (b) (a) plus a later replay
  of the real safety car: slow laps and a cheaper pit stop on the known laps.
  (c) Model rain and random safety cars now: rainfall isn't track wetness, and
  8-10 races can't support safety-car odds per circuit.
- **Choice and reason** — (b). The real safety-car laps are known from
  `race_control`, so a replay doesn't need an invented distribution. Building it
  after a working backtest gives a baseline to measure it against. Safety-car
  laps stay out of fitting either way, because they say nothing about tyres or
  fuel.
- **What would make us reconsider** — The replay doesn't reduce backtest error on
  safety-car races: drop it. A dataset with far more races could reopen
  safety-car odds.

