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


## Laps in/out for all 10 races
- Bahrain (9472): Fairly average pace all over the tyre ages. Only observation is for tyre age 0, lap times are relatively high. I'd say it's for the same reasons as usual, out laps and lap 1.
```
Laps in: 1129, laps out: 1129
Unmatched laps (no stint): 0
Laps with no lap_duration: 0
Laps with neither a stint nor a lap_duration: 0
Lap times:
0 117.634
1 96.98
2 96.779
3 97.559
4 96.93
5 97.027
6 97.097
7 97.131
8 97.134
9 98.094
10 97.04
11 97.229
12 96.988
13 97.309
14 97.292
15 97.067
16 97.051
17 97.404
18 97.091
19 97.276
20 97.432
21 96.972
22 96.988
23 97.373
24 97.181
25 97.85
26 97.038
27 97.007
28 96.582
29 97.335
```

- Monza 2024: Tyres at age > 34 are almost a second faster than laps before it. Interesting. Same observation for tyre age 0. Driver 22 crashed (Yuki) on lap 7
```
Laps in: 1009, laps out: 1009
Unmatched laps (no stint): 1
  driver 22, lap 8, lap_duration None
Laps with no lap_duration: 1
  driver 22, lap 8, tyre_age None
Laps with neither a stint nor a lap_duration: 1
0 101.066
1 88.388
2 86.116
3 85.04
4 85.135
5 85.023
6 84.749
7 85.13
8 84.648
9 84.733
10 84.849
11 84.693
12 84.804
13 84.915
14 85.245
15 85.158
16 84.767
17 84.753
18 85.159
19 85.175
20 84.637
21 85.955
22 85.412
23 85.668
24 85.262
25 85.158
26 85.8
27 85.285
28 85.132
29 85.219
30 85.316
31 84.646
32 85.015
33 85.023
34 84.445
35 84.455
36 84.327
37 84.689
38 84.166
39 84.817
40 84.639
41 84.219
42 84.347
```

- Hungary 2024 (9566): Age 0 averages 99.081s and age 1 averages 87.193s; ages 2-21 stay between 84.083s and 84.596s. Driver 10 also has a null `lap_duration` on lap 1, with a null `date_start`, like Ocon in Mexico 2024.
```
Laps in: 1356, laps out: 1356
Unmatched laps (no stint): 1
  driver 10, lap 34, lap_duration None
Laps with no lap_duration: 2
  driver 10, lap 1, tyre_age 0
  driver 10, lap 34, tyre_age None
Laps with neither a stint nor a lap_duration: 1
0 99.081
1 87.193
2 84.374
3 84.487
4 84.373
5 84.312
6 84.167
7 84.213
8 84.083
9 84.12
10 84.337
11 84.204
12 84.256
13 84.485
14 84.31
15 84.416
16 84.596
17 84.482
18 84.422
19 84.337
20 84.549
21 84.494
22 84.865
23 85.054
24 84.811
25 84.886
26 85.245
27 85.583
28 85.437
29 84.967
30 84.911
31 84.751
32 85.414
33 86.57
34 86.617
35 86.347
36 85.85
37 84.926
38 84.8
39 85.004
40 86.416
```

- Singapore 2024 (9606): Age 0 averages 114.609s. Ages 4-24 are mostly 98.3-98.9s, with one jump at age 20 (100.69s). Ages 35-37 average 101.2-101.7s. Not explained yet.
```
Laps in: 1179, laps out: 1179
Unmatched laps (no stint): 2
  driver 23, lap 16, lap_duration None
  driver 20, lap 58, lap_duration None
Laps with no lap_duration: 2
  driver 23, lap 16, tyre_age None
  driver 20, lap 58, tyre_age None
Laps with neither a stint nor a lap_duration: 2
0 114.609
1 100.407
2 98.847
3 100.41
4 98.327
5 98.566
6 98.454
7 98.899
8 98.541
9 98.557
10 98.428
11 98.599
12 98.627
13 98.411
14 98.367
15 98.456
16 98.46
17 98.454
18 98.793
19 98.493
20 100.69
21 98.611
22 98.634
23 98.714
24 98.893
25 99.234
26 99.668
27 99.531
28 100.394
29 99.109
30 99.29
31 98.995
32 100.139
33 99.861
34 99.259
35 101.721
36 101.704
37 101.188
38 98.81
39 98.594
40 98.363
41 98.612
42 98.462
43 98.634
44 98.984
45 98.558
46 98.838
47 98.3
48 99.771
```

- Abu Dhabi 2024 (9662): Ages 0-2 average 107.24s, 102.028s and 95.209s, slower than the about 89-90.5s from age 4 on, apart from jumps at age 23 (91.723s) and age 43 (91.019s). Not explained yet. Driver 11 also has a null `lap_duration` on lap 1, but with a `date_start`.
```
Laps in: 1037, laps out: 1037
Unmatched laps (no stint): 3
  driver 43, lap 27, lap_duration None
  driver 77, lap 31, lap_duration None
  driver 30, lap 56, lap_duration None
Laps with no lap_duration: 4
  driver 11, lap 1, tyre_age 0
  driver 43, lap 27, tyre_age None
  driver 77, lap 31, tyre_age None
  driver 30, lap 56, tyre_age None
Laps with neither a stint nor a lap_duration: 3
0 107.24
1 102.028
2 95.209
3 90.869
4 89.439
5 89.767
6 90.447
7 89.625
8 89.579
9 89.724
10 89.836
11 89.948
12 89.672
13 89.706
14 89.504
15 89.427
16 89.598
17 89.445
18 89.562
19 89.739
20 89.573
21 89.637
22 89.876
23 91.723
24 89.418
25 89.297
26 89.487
27 89.434
28 89.242
29 88.956
30 89.179
31 89.35
32 89.329
33 89.574
34 89.337
35 89.311
36 89.352
37 89.679
38 90.056
39 89.897
40 90.401
41 90.336
42 90.111
43 91.019
44 90.449
```

- Bahrain 2025 (10014): Join results only; tyre-age averages left out because 2025 is the test set.
```
Laps in: 1129, laps out: 1129
Unmatched laps (no stint): 1
  driver 55, lap 46, lap_duration None
Laps with no lap_duration: 1
  driver 55, lap 46, tyre_age None
Laps with neither a stint nor a lap_duration: 1
```

- Hungary 2025 (9928): Join results only; tyre-age averages left out because 2025 is the test set.
```
Laps in: 1369, laps out: 1369
Unmatched laps (no stint): 1
  driver 87, lap 49, lap_duration None
Laps with no lap_duration: 1
  driver 87, lap 49, tyre_age None
Laps with neither a stint nor a lap_duration: 1
```

- Monza 2025 (9912): Join results only; tyre-age averages left out because 2025 is the test set.
```
Laps in: 976, laps out: 976
Unmatched laps (no stint): 1
  driver 14, lap 25, lap_duration None
Laps with no lap_duration: 2
  driver 27, lap 1, tyre_age 0
  driver 14, lap 25, tyre_age None
Laps with neither a stint nor a lap_duration: 1
```

- Singapore 2025 (9896): Join results only; tyre-age averages left out because 2025 is the test set.
```
Laps in: 1229, laps out: 1229
Unmatched laps (no stint): 0
Laps with no lap_duration: 0
Laps with neither a stint nor a lap_duration: 0
```

- Abu Dhabi 2025 (9839): Join results only; tyre-age averages left out because 2025 is the test set.
```
Laps in: 1156, laps out: 1156
Unmatched laps (no stint): 0
Laps with no lap_duration: 0
Laps with neither a stint nor a lap_duration: 0
```

### Join summary for the 10 races

- No overlapping stints in any session (`find_stint` would have raised), and no
  repeated (`driver_number`, `lap_number`) pairs.
- Laps in equals laps out in all 10 sessions.
- 10 unmatched laps in total. Each one is that driver's last recorded lap, one
  lap after their last stint's `lap_end`, before the race distance, and has a
  null `lap_duration`. No unmatched lap is mid-race. Whether each was a
  retirement has not been confirmed.
- 13 null `lap_duration` values in total: those 10 last laps, plus lap 1 for
  driver 10 (Hungary 2024), driver 11 (Abu Dhabi 2024) and driver 27 (Monza
  2025).
- The 2025 tyre-age averages were deliberately not printed or recorded: the 2025
  races are not looked at until the model is chosen.

## Exclusion reasons per race (2026-11-08)

Counts from `exclusion_reasons` on the 10 v1 sessions. A lap can have more than
one reason, so the columns don't add up to the excluded total. "No reason yet"
is before the safety-car and VSC rules exist, so it is not the final clean count.
The 2025 rows use lap numbers and flags only, not lap times.

| Session | Laps | `lap_1` | `pit_out` | `in_lap` | `null_lap_duration` | `before_retirement` | `no_stint` | No reason yet |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Bahrain 2024 | 1,129 | 20 | 43 | 43 | 0 | 0 | 0 | 1,024 |
| Hungary 2024 | 1,356 | 20 | 40 | 40 | 2 | 1 | 1 | 1,254 |
| Monza 2024 | 1,009 | 20 | 30 | 30 | 1 | 1 | 1 | 927 |
| Singapore 2024 | 1,179 | 20 | 23 | 23 | 2 | 2 | 2 | 1,109 |
| Abu Dhabi 2024 | 1,037 | 20 | 28 | 28 | 4 | 3 | 3 | 957 |
| Bahrain 2025 | 1,129 | 20 | 42 | 42 | 1 | 1 | 1 | 1,024 |
| Hungary 2025 | 1,369 | 20 | 29 | 29 | 1 | 1 | 1 | 1,289 |
| Monza 2025 | 976 | 20 | 19 | 19 | 2 | 1 | 1 | 916 |
| Singapore 2025 | 1,229 | 20 | 23 | 23 | 0 | 0 | 0 | 1,163 |
| Abu Dhabi 2025 | 1,156 | 20 | 27 | 27 | 0 | 0 | 0 | 1,082 |

## In-lap rule checks (2024 races)

Rule: the last lap of a stint, when the driver has another stint afterwards.

- It finds 164 laps. Each is followed by a flagged pit-out lap, and every
  pit-out lap follows one of them.
- The pit-lane code 2064 in sector 3 fires on all 164, plus 6 laps the rule
  misses: Hungary driver 10 lap 33, Monza driver 22 lap 7, Singapore driver 23
  lap 15 and driver 20 lap 57, Abu Dhabi driver 43 lap 26 and driver 77 lap 30.
  Each is the lap right before an unmatched last lap.
- `/pit` for the five 2024 races (checked 2026-11-08, not cached yet) has the
  same 164 stops, with `lap_number` equal to the in-lap. None of the 6 laps are
  in it.
- `lane_duration` is filled in on every `/pit` record in those races.
  `stop_duration` is null on all of them except Abu Dhabi 2024, as expected
  before the 2024 US GP.

## Tyre-age check (Hungary 2024)

- Driver 44, stint 2 (HARD, laps 17-40, start age 0): age 0 on lap 17, 23 on
  lap 40.
- Driver 18, stint 2 (MEDIUM, laps 15-45, start age 1): age 1 on lap 15, 31 on
  lap 45.
- `add_stint_data` gives the same four numbers as the hand calculation.
- The [official pit stop summary](https://www.formula1.com/en/results/2024/races/1241/hungary/pit-stop-summary)
  lists stops on laps 16 and 40 for driver 44, and 14 and 45 for driver 18, which
  match the stints' `lap_end` values. It doesn't show compounds.
- [OpenF1 docs](https://openf1.org/docs/): `tyre_age_at_start` is "in laps
  completed", and `lap_end` is the "last completed lap in this stint". That fits
  the unmatched laps: a lap the driver never finished is not in any stint.
