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

## 2026-11-04 — Laps with no matching stint are kept, with `None` values

- **Decision** — `add_stint_data` keeps a lap with no matching stint and sets its
  `tyre_age` and `compound` to `None`.
- **Requirement** — Real races have unmatched laps: in Mexico 2024, driver 14's
  lap 16 has no stint. The join has to handle them without hiding them or
  inventing values.
- **Options** — (a) Keep the lap with `None`: the row count stays the same, but
  later code has to handle `None`. (b) Drop the lap in the join and return a count:
  later code is simpler, but the join also becomes cleaning. (c) Raise an error:
  very visible, but real data stops it straight away. I also considered assuming
  the driver was in the pit lane when a later stint exists, but no unmatched lap
  in Mexico has one, and it would add a fact the data doesn't show.
- **Choice and reason** — (a). The join stays a join, and every exclusion can be
  made and counted in one place during cleaning.
- **What would make us reconsider** — Unmatched laps turn up mid-race in other
  races, which would need an explanation rather than just `None`. Or handling
  `None` becomes repetitive once we move to the processed dataset.

## 2026-11-04 — Overlapping stints raise `ValueError`

- **Decision** — `find_stint` raises `ValueError`, naming the driver and lap, when
  more than one of a driver's stints covers the same lap.
- **Requirement** — A car has one set of tyres on a lap, so a lap needs a single
  tyre age and compound. An overlap means the data breaks that assumption.
- **Options** — (a) Raise `ValueError`: visible straight away, but one bad row
  stops the whole race. (b) Return the first match: never stops, but can pass a
  wrong age into the model unnoticed. (c) Use `None`: the run continues, but a data
  error looks the same as a retirement lap.
- **Choice and reason** — (a). We shouldn't guess when a basic assumption fails.
  This is different from an unmatched lap, which is expected in real races.
- **What would make us reconsider** — Overlaps turn out to be common and have a
  known cause when we run more races. Then we'd handle that cause with its own
  rule. Mexico 2024 has none, and no other race has been checked yet.


## 2026-11-05 — Races with a safety car stay in; disrupted laps are dropped

- **Decision** — A dry race with a safety car (SC), virtual safety car (VSC) or
  red flag can still be used. Its disrupted laps are dropped during cleaning,
  with a count per race. Only fully undisrupted sessions are used for the
  simulator backtest.
- **Requirement** — CLAUDE.md asks for 4-5 Grands Prix in both 2024 and 2025,
  with a range of tyre wear across circuits. Only 3 of the 17 non-sprint
  candidates are clean in both years (Hungaroring, Monza, Singapore), and all
  three are mostly one- or two-stop races.
- **Options** — (a) Only races clean in both years: no lap dropping, but 3 races
  with similar wear. (b) Any dry race, drop SC/VSC/red-flag laps, backtest on
  clean sessions only. (c) Treat a VSC as clean: more races, but VSC laps are
  slow and pit stops under a VSC are cheaper, so both the model and the backtest
  get noisier.
- **Choice and reason** — (b). The model treats each lap as its own row, so a
  gap in the lap sequence doesn't hurt it, as long as tyre age and race lap are
  computed from the real lap numbers before anything is dropped. Keeping the
  laps would hurt: in Mexico 2024 the lap 1-6 safety car made the youngest tyres
  look 20+ seconds slow, while clean Hungary 2024 is flat at about 84.1-84.6s
  from age 1 to 17. Accepted cost: tyre age and race lap keep counting during a
  safety car while the tyres barely wear and less fuel is burned, so ages after
  a safety car overstate wear slightly. That goes in the limitations. The laps
  around an SC (deployment and restart) also need to be in the exclusion rule.
- **What would make us reconsider** — Residuals that are consistently off on
  laps after a safety car (then try a "racing laps on this set" feature in
  Week 5), or one race losing so many laps that its wear estimate is unreliable.

## 2026-11-05 — v1 races and how they are split

- **Decision** — v1 uses 5 Grands Prix in both 2024 and 2025: Hungary
  (Hungaroring), Italy (Monza), Singapore, Bahrain (Sakhir) and Abu Dhabi (Yas
  Marina).
  - Training: the 2024 races (9566, 9590, 9606, 9472, 9662).
  - Test: the 2025 races (9928, 9912, 9896, 10014, 9839), not looked at until
    the model is chosen.
  - Model selection: leave one 2024 race out at a time.
  - Backtest: sessions with no SC, VSC or red flag. Held out: Hungary, Monza,
    Singapore, Abu Dhabi 2025. In-sample, reported separately: Hungary, Monza,
    Singapore, Bahrain 2024.
- **Requirement** — 4-5 dry, non-sprint Grands Prix with usable data in both
  years (CLAUDE.md), a range of tyre wear across circuits (rule 3), and enough
  undisrupted sessions for the backtest (rule 8).
- **Options** — (a) These 5. (b) Suzuka instead of Yas Marina: high wear in 2024
  (mostly 3 stops) but almost all 1-stop in 2025, so a harder test that may
  reflect a circuit change we can't model. (c) Las Vegas instead of Yas Marina:
  2024 clean, but 2025 VSCs on laps 2-4 and 16. Zandvoort, Imola, Monaco and the
  rain races were ruled out for heavy disruption, track-position races or rain
  (see `docs/DATA_AUDIT.md`).
- **Choice and reason** — (a). Sakhir adds the only high-wear circuit with
  little disruption (2-3 stops both years, one 4-lap SC in 2025). Yas Marina
  costs 2 VSC laps and behaves similarly in both years. That gives 8
  undisrupted sessions for the backtest.
- **What would make us reconsider** — The lap/stint check fails on one of these
  sessions, Singapore 2025's rain readings turn out to be during the race, or
  Sakhir 2024's missing MEDIUM stints turn out to be a data problem. Suzuka
  2025 and Zandvoort 2024 (both undisrupted) stay available as an optional
  unseen-circuit test.

## 2026-11-05 — Request details go in a sidecar file next to each cached response

- **Decision** — `load_or_fetch` writes `<endpoint>_<session_key>.meta.json`
  next to each cached response, with the endpoint, params, retrieval time (UTC)
  and record count. A "no results" 404 is cached as `[]` with `records: 0`.
- **Requirement** — The data rules require recording the endpoint, params,
  session key and retrieval date for every cached file.
- **Options** — (a) A sidecar file per response: the cached file stays just the
  records, but there are twice as many files and they can get out of sync.
  (b) Wrap the response in `{"meta": ..., "data": [...]}`: one file, but the
  cached file is no longer the API's records, and the 70+ files already saved
  don't match. (c) One `manifest.json` for all files: one place to look, but
  every fetch rewrites a shared file, and a crash halfway can leave it out of
  step with the files.
- **Choice and reason** — (a). It keeps the records as the API sent them and
  works alongside the files cached before this code existed.
- **What would make us reconsider** — Sidecars going missing or out of sync
  with their data files, or needing to answer questions across all files
  (e.g. "what did I fetch last week?") often enough that a manifest pays off.
