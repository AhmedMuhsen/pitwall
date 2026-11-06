# Data audit

What we fetched from OpenF1, what it contained, and what is still unchecked.
Raw responses are in `data/raw/` (gitignored).

## Requests

All retrieved 2026-11-03 from `https://api.openf1.org/v1`.

| File | Endpoint | Params | Records |
|---|---|---|---|
| `sessions_2024.json` | `/sessions` | `year=2024&session_name=Race` | 24 |
| `sessions_2025.json` | `/sessions` | `year=2025&session_name=Race` | 24 |
| `sprint_sessions_2024.json` | `/sessions` | `year=2024&session_name=Sprint` | 6 |
| `sprint_sessions_2025.json` | `/sessions` | `year=2025&session_name=Sprint` | 6 |
| `laps_9625.json` | `/laps` | `session_key=9625`  | 1,216 |
| `stints_9625.json` | `/stints` | `session_key=9625`  | 41 |
| `intervals_9625_44.json` | `/intervals` | `session_key=9625&driver_number=44`  | 1,489 |

First race explored: Mexico 2024 (`session_key=9625`), chosen for first
exploration only, not yet part of the final race list.

## Sessions: what the responses show

Fields in a session record: `circuit_key`, `circuit_short_name`, `country_code`,
`country_key`, `country_name`, `date_end`, `date_start`, `gmt_offset`,
`is_cancelled`, `location`, `meeting_key`, `session_key`, `session_name`,
`session_type`, `year`.

- `session_type=Race` **includes sprints.** It returned 30 records for each of
2024 and 2025: 24 named `Race` and 6 named `Sprint`. To get Grands Prix only,
filter on `session_name=Race`.
- `country_name` **does not identify a race.** The United States has 3 races
and Italy has 2 in both years.
- `session_key` **and** `meeting_key` **change between years.** To match a Grand
Prix across years, use `circuit_key`. It is unique within each year's 24
races, and all 24 circuits appear in both years.
- **Sprint weekends can change between years.** Spielberg had a sprint in 2024
only, and Spa-Francorchamps in 2025 only.
- No session in these four files has `is_cancelled` set to true.

## Non-sprint candidates

Grands Prix with no sprint in 2024 or 2025: 17 of 24. This only checks the
sprint requirement. It does not check for dry conditions, safety cars or data
coverage.

| Circuit | Country | `circuit_key` | 2024 `session_key` | 2025 `session_key` |
|---|---|---:|---:|---:|
| Sakhir | Bahrain | 63 | 9472 | 10014 |
| Jeddah | Saudi Arabia | 149 | 9480 | 10022 |
| Melbourne | Australia | 10 | 9488 | 9693 |
| Suzuka | Japan | 46 | 9496 | 10006 |
| Imola | Italy | 6 | 9515 | 9987 |
| Monte Carlo | Monaco | 22 | 9523 | 9979 |
| Montreal | Canada | 23 | 9531 | 9963 |
| Catalunya | Spain | 15 | 9539 | 9971 |
| Silverstone | United Kingdom | 2 | 9558 | 9947 |
| Hungaroring | Hungary | 4 | 9566 | 9928 |
| Zandvoort | Netherlands | 55 | 9582 | 9920 |
| Monza | Italy | 39 | 9590 | 9912 |
| Baku | Azerbaijan | 144 | 9598 | 9904 |
| Singapore | Singapore | 61 | 9606 | 9896 |
| Mexico City | Mexico | 65 | 9625 | 9877 |
| Las Vegas | United States | 152 | 9644 | 9858 |
| Yas Marina Circuit | United Arab Emirates | 70 | 9662 | 9839 |

Excluded for a sprint in at least one year: Shanghai, Miami, Spielberg,
Spa-Francorchamps, Austin, Interlagos, Lusail.

## Live docs check

Checked 2026-11-03 against the OpenF1 docs. All match the plan.

- **Rate limits:** 3 requests/second and 30 requests/minute on the free tier.
- **Coverage:** historical data from 2023 onward is free.
- **`stop_duration`:** available only from the 2024 US GP onward.
- **`pit_duration`:** will be removed at the end of the 2026 season.
- **Gap to car ahead:** `interval` on the `/intervals` endpoint. In seconds,
  `+1 LAP` if lapped, null for the race leader (per the docs). Updates about
  every 4 seconds.

## Intervals

- Confirmed to return historical data (Mexico 2024, driver 44).
- No lap number, so we will have to match to laps by time.
- Still don't know how to turn readings into a clean-lap flag, so that will be
  explored later.
- Driver 44's `interval` values: 1,477 floats, 12 nulls, 0 strings. The exact
  lapped-driver string has not been seen in a response yet.

## Laps

Null `lap_duration` (Mexico 2024): 4 of 1,216 laps.

- Three are on the driver's final lap, so retirements (confirmed by a google search).
- One is Esteban Ocon's lap 1, which also has a null `date_start`. He started
  from the pit lane (from a web search; source link to add). This is one
  example, not a rule.
- Null `lap_duration` is not a pit-lap marker: there are 21 pit-out laps. Pit-lap
  exclusion needs its own rule, with a count.

Other findings from `/laps`:

- No repeated (`driver_number`, `lap_number`) pairs across 1,216 laps and 20
  drivers.
- `is_pit_out_lap` flags only the out-lap. In-laps are not flagged: driver 44's
  lap 28 is 87.1s against about 83s before it.
- Median lap across the field is about 130-138s on laps 2-5 and about 83s from
  lap 7. Looks like a safety car or virtual safety car; not checked against
  `/race_control`.

## Stints

Checked for all 20 drivers in Mexico 2024:

- Stints do not overlap or leave gaps: each `lap_start` is the previous
  `lap_end` + 1.
- Every pit-out lap matches a later stint's `lap_start`.
- **Join gap:** driver 14's last stint ends on lap 15, but they have a lap 16
  (the null-duration lap). That lap has no matching stint.
- `tyre_age_at_start + (lap_number - lap_start)` gives 0 on a stint's first lap
  on a new set. The arithmetic is consistent, but this does not independently
  confirm a tyre's real history.
- 8 of 41 stints start on used sets (age 1 or 3), so the formula must keep the
  starting age.

## Fields I understand and don't understand

Understood:

- `i1_speed`, `i2_speed`: km/h at two intermediate points on the track.
- `st_speed`: km/h at the speed trap.
- `segments_sector_*`: mini-sector codes. Docs: 0 not available, 2048 yellow,
  2049 green, 2051 purple, 2064 pitlane; 2050, 2052 and 2068 unknown. Mini-sector
  counts at this circuit: 8 in sectors 1 and 2, 4 or 5 in sector 3.

Not understood:

- Nulls in `segments_sector_*`: 949 across the race, 943 of them in the first
  mini-sector of sector 1. The docs' table does not list null.
- The docs say "Segments are not available during races", yet this race has
  them. My reading is that this means live sessions; the docs do not say so.
  Do not build the model on these fields.

Lead for the cleaning session, not a rule: code 2064 appears in sector 1 on all
21 pit-out laps, on Ocon's lap 1 (the only lap 1 with it), and in sector 3 on 22
laps, including driver 44's in-lap. 22 laps against 21 stops leaves one to
explain. Compare with a "last lap of a stint" in-lap rule.

## Rain and disruptions across candidates

From `scripts/check_candidate_races.py`: unfiltered `/weather` and
`/race_control` for all 34 candidate sessions (68 files,
`data/raw/<endpoint>_<session_key>.json`, retrieved 2026-11-03).

"Clean" here means no rain reading during the race, and no safety car, virtual
safety car or red flag. It does not check lap or stint data quality, or wet-tyre
use. Counting a virtual safety car as not clean is an assumption, still to be
decided.

| Group | Grands Prix |
|---|---|
| Clean in both years | Hungaroring, Monza, Singapore (2025 had rain before the race only) |
| Dry both years, clean in one | Imola (2024), Las Vegas (2024), Sakhir (2024), Zandvoort (2024), Suzuka (2025), Yas Marina (2025) |
| Dry both years, clean in neither | Baku, Jeddah, Mexico City, Monte Carlo |
| Rain during at least one race | Silverstone (both), Montreal (both; 1 reading in 2025), Melbourne (2025), Catalunya (2024; 1 reading) |

Clean sessions: 12 of 34 (7 in 2024, 5 in 2025).

## Checklist

- [x] Section 2.2 facts against the live docs: rate limits, 2023+ coverage,
      `stop_duration` from the 2024 US GP, `pit_duration` deprecation
- [x] Where gap-to-car-ahead data comes from (needed for the clean-lap definition)
- [x] Which candidates were dry
- [x] `/laps` and `/stints` for one chosen race
- [ ] Exact form of the lapped-driver value in `interval`

## Hungary 2024

### Laps
- 1,356 laps in and out

### Stints
- No overlapping stints.
- Unmatched lap: driver 10, lap 34, with no stint and no `lap_duration`. It is their last lap
  (the race went to 70), the same pattern as driver 14 in Mexico 2024. Retirement not confirmed.

### Tyre ages
- Age 0 is mostly pit-out laps, and the other bit is race start, so they're much slower than the average pace for the race. 15 lap 1s, and 32 pit-outs.
- Age 1 normal laps average 84.32s, same as later ages. There are 2 lap 1s, and 8 pit-out laps, which are pushing the average higher. 48 normal laps.
- Thus, we will exclude lap 1 and pit-out laps by lap type.


## Stints across shortlisted races

`/stints?session_key=<key>` for both years of 12 dry candidates (22 new files,
`data/raw/stints_<session_key>.json`, retrieved 2026-11-05). Pit stops per
driver = stints - 1, so "0 stops" includes drivers who retired before stopping.
Disrupted laps are from `race_control` (deployed lap to ending lap).

| Circuit | 2024 stops (drivers) | 2025 stops (drivers) | 2024 disruptions | 2025 disruptions |
|---|---|---|---|---|
| Hungaroring | 1:2, 2:16, 3:2 | 1:11, 2:9 | none | none |
| Monza | 0:1, 1:9, 2:9, 3:1 | 0:1, 1:19 | none | none |
| Singapore | 1:18, 2:1, 3:1 | 1:17, 2:3 | none | none (rain readings pre-race only) |
| Sakhir | 2:17, 3:3 | 2:18, 3:2 | none | SC laps 32-35 |
| Yas Marina | 0:1, 1:13, 2:4, 3:1, 4:1 | 1:13, 2:7 | VSC laps 2-3 | none |
| Suzuka | 0:2, 2:2, 3:14, 4:2 | 1:19, 2:1 | red flag lap 1 | none |
| Las Vegas | 1:3, 2:15, 3:2 | 0:1, 1:15, 2:3, 3:1 | none | VSC laps 2-4, 16 |
| Zandvoort | 1:14, 2:6 | 0:1, 1:3, 2:12, 3:3, 4:1 | none | SC 23-26, VSC 31-32, SC 53-57, SC 65-68 |
| Baku | 1:18, 2:2 | 0:1, 1:17, 2:2 | VSC lap 51 (last lap) | SC laps 1-4 |
| Mexico City | 0:3, 1:14, 2:2, 3:1 | 0:1, 1:12, 2:6, 3:1 | SC laps 1-6 | VSC laps 70-71 |
| Jeddah | 0:2, 1:17, 2:1 | 0:2, 1:17, 2:1 | SC laps 7-9 | SC laps 1-3 |
| Imola | 1:16, 2:2, 3:1, 4:1 | 1:4, 2:15, 3:1 | none | VSC 29-31, SC 46-53 |

Not used: Monte Carlo (2024 red flag on lap 1, processional race), rain races
(Silverstone, Montreal 2024, Melbourne 2025), and Catalunya 2024 / Montreal
2025 until their single rain reading is checked.

To check: Sakhir 2024 stints show only SOFT and HARD, no MEDIUM.

## Curl mistakes
- Error message can't differentiate between non-existent endpoint call and non-existent session call. We'll have to make sure these cases aren't reachable from our function itself.
- Both return:
``` HTTP/1.1 404 Not Found
  Server: nginx
  Date: Thu, 05 Nov 2026 22:31:16 GMT
  Content-Type: application/json
  Content-Length: 30
  Connection: keep-alive
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin

  {"detail":"No results found."}%
  ```
## Laps and stints for the 10 v1 sessions

Fetched with `scripts/fetch_races.py` through `pitwall.ingestion.load_or_fetch`
on 2026-11-05: 9 requests (laps for every session except Hungary 2024), then 0
on a second run.

| Session | `session_key` | Laps | Stints |
|---|---:|---:|---:|
| Bahrain 2024 | 9472 | 1,129 | 63 |
| Hungary 2024 | 9566 | 1,356 | 60 |
| Italy (Monza) 2024 | 9590 | 1,009 | 50 |
| Singapore 2024 | 9606 | 1,179 | 43 |
| Abu Dhabi 2024 | 9662 | 1,037 | 48 |
| Bahrain 2025 | 10014 | 1,129 | 62 |
| Hungary 2025 | 9928 | 1,369 | 49 |
| Italy (Monza) 2025 | 9912 | 976 | 39 |
| Singapore 2025 | 9896 | 1,229 | 43 |
| Abu Dhabi 2025 | 9839 | 1,156 | 47 |

- Bahrain has 1,129 laps in both years. Checked: each file holds only its own
  `session_key`, and they start on 2024-03-02 and 2025-04-13. A coincidence,
  not a duplicate.
- Files fetched through `load_or_fetch` have a `.meta.json` sidecar (endpoint,
  params, UTC retrieval time, record count). Files cached before it existed
  have none: all `stints_*`, `laps_9566`, `laps_9625`, and the sessions,
  weather, race_control and intervals files. Their requests are recorded in
  the sections above.
- Not checked yet: the lap/stint join on these sessions, null `lap_duration`
  counts, and unmatched laps.
