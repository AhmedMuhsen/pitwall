# PitWall: Tire-Degradation Modeling Notes

Reference for Weeks 3 to 5 of `docs/PITWALL_PLAN.md`. Adapted from an outside
guide: kept what fits PitWall v1, fixed one modeling error, removed the
agent-specific parts (v1 has no agents; see Plan Section 15).

## 1. What we are estimating

**Tire-age-associated lap-time loss**, not physical tire wear. OpenF1 has no
tire temperatures, pressures, wear measurements, setup data or fuel mass, so
the model can say "laps on this compound at this track got about X s slower
per lap of tire age, after controlling for fuel and the driver's pace." It
cannot say what physically happened to the tire. Word the README that way.

Not the same thing as:
- **Tire life:** how long teams chose to run a set. That's a strategic
  choice, not a degradation rate.
- **Pit-lap prediction:** when a team actually stopped also depends on pit
  loss, track position, safety cars and team choices. Out of scope.

## 2. Tire age: derive it, then verify it

Likely formula, from `/stints`:

```text
tire_age(lap) = tyre_age_at_start + (lap_number - lap_start)
```

Before trusting it:
- Check whether `lap_start` and `lap_end` are inclusive, and which stint the
  pit-in and pit-out laps belong to. An off-by-one error here shifts every
  slope in the project.
- Hand-check a few laps for two drivers against a known race (e.g. a stint
  you can see on an F1 timing graphic or race report).
- `tyre_age_at_start` can be above zero for used sets. Confirm age doesn't
  wrongly reset to zero.
- Join laps to stints on `session_key`, `driver_number` and the stint's lap
  interval. Never on driver or lap number alone. Check row counts before and
  after.

Write the formula and the check you did into `DECISIONS.md`.

## 3. Clean laps, and two datasets

Candidate exclusions for estimating dry-tire pace, each with a recorded
reason and a count:
- pit-in and pit-out laps;
- missing or implausible lap times;
- Safety Car, VSC and red-flag laps, when `/race_control` identifies them
  reliably (inspect a few by hand; a text search is not a classifier);
- wet or transitional laps;
- lap 1.

Don't delete slow laps just because they're slow. A slow lap can be real
tire performance.

Test the warm-up question instead of assuming it: does dropping the first
lap after the out-lap change the estimate? Keep whichever rule the evidence
supports.

Keep **two datasets**:
- **Clean:** the filtered laps above. Used to *fit* the model.
- **Racing:** all green-flag racing laps, including traffic and messy ones.
  Used alongside the clean set for *evaluation*.

Reporting accuracy only on the clean set makes the model look better than it
is, because the hard laps were removed from both training and testing.

## 4. The modeling ladder

Go up one step only when the step below shows a specific problem.

### Step 1: per-stint slope (diagnostic only)

Fit `lap_time = a + b * tire_age` within each stint and plot it. Report the
number of laps used and the standard error. Flag short stints (pick a
minimum, e.g. 8 clean laps, and justify it).

This slope is **biased**: within a stint, fuel burns off at the same pace the
tire ages, so `b` is roughly (true wear rate minus fuel gain). A flat or
negative slope doesn't mean the tire got better. Use these slopes to find
data problems and odd stints, not as the model.

Robust fitting (Huber or Theil-Sen) reduces the effect of one weird lap. It
does not fix the fuel problem.

### Step 2: pooled model (the v1 model)

One model across all stints, drivers and races in the training set:

```text
delta = compound_offset[c]
      + fuel_coef * race_lap
      + wear_rate[c, circuit] * tire_age
      + noise
```

where `delta` is lap time minus that driver's median clean lap in that race
(Plan Week 4).

**Identification: why the baseline is per driver-race and not per stint.**
Within one stint, `race_lap - tire_age` is a constant. If the model had a
separate intercept for every stint, the fuel term and the wear term would be
perfectly collinear and could not be separated at all. With one baseline per
driver per race, the separation comes from pit stops: tire age resets, race
lap doesn't. That only works for drivers with two or more stints, and works
better when stints start at different laps or on used tires. Check that your
training data has that variety.

(The outside guide suggested stint-level intercepts together with a race-lap
term. That combination can't be estimated, so it's left out here.)

Fit with ordinary least squares (scikit-learn `LinearRegression` or
`statsmodels` if you want standard errors). Sanity checks:
- `fuel_coef` should be negative (laps get faster as fuel burns).
- `wear_rate` should be positive for most compound-circuit pairs and should
  grow compared with a model that has no `race_lap` term.
- If either fails, investigate the data before changing the model.

### Step 3: improvements (Week 5, one at a time, only with evidence)

| What residuals show | Try |
|---|---|
| Curvature against tire age | Piecewise-linear or quadratic wear term |
| Noisy rates for compound-circuit pairs with few stints | Partial pooling (mixed model) so sparse pairs borrow strength |
| Race-wide drift left over | Field-relative pace as a diagnostic (below) |
| You want a predictive benchmark | A tree model (e.g. gradient boosting), same held-out split |

Quadratics and trees behave badly beyond the observed tire-age range. The
simulator's observed-range guard (Plan Week 6) covers that.

Field-relative pace on lap `l`:
`z = lap_time - median(lap_time of clean drivers on lap l)`. It removes much
of the race-wide fuel and track-evolution trend, but mixes cars and tire
ages. Use it to cross-check `fuel_coef`, not as the main target.

Out of scope for v1: state-space models (see the reference below; a
reasonable later extension), Bayesian hierarchical models beyond a simple
mixed model.

## 5. Evaluation

Main test (Plan Week 4): train on 2024 races, test on 2025 editions of the
same Grands Prix.

Report:
- MAE and RMSE in seconds, on **both** the clean and the racing datasets;
- **bias** (mean of predicted minus actual), overall and by tire age, so
  systematic over- or under-prediction late in stints shows up;
- error slices by compound, circuit and tire-age bucket;
- the zero-delta baseline and the no-fuel model alongside the chosen model.

Degradation-trend checks (is the wear estimate itself believable?):
- sensitivity of `wear_rate` to reasonable filter changes (with and without
  the warm-up lap, with and without traffic-heavy stints);
- residuals against tire age and race lap, both should look flat;
- stability of wear rates for the same compound and circuit in 2024 vs 2025.

Not needed for v1: rolling-origin "predict the next 3 laps" validation. That
fits a live, in-race tool. PitWall simulates whole races offline, so the
held-out race test matches its use better.

## 6. What the model function returns

Return structured data, not prose. The simulator and the app (and a Phase 2
agent, later) depend on it. Something like:

```python
{
    "compound": "MEDIUM",
    "circuit": "...",
    "tire_age_laps": 18,
    "wear_rate_s_per_lap": ...,          # from the fitted model
    "extra_loss_next_5_laps_s": ...,     # g(age + 5) - g(age)
    "supporting_stints": ...,            # training stints for this pair
    "max_observed_age": ...,             # feeds the observed-range guard
    "warnings": ["few_supporting_stints", "beyond_observed_range"],
}
```

Values are placeholders. If you add an uncertainty number, say whether it's
uncertainty in the expected loss or a prediction interval for a single lap;
they're different. "Extra loss over the next N laps" is a good thing to show
in the app ("staying out 5 more laps costs about X s").

## 7. Common traps

- Joining on lap number alone (it repeats across drivers and sessions).
- Age resetting to zero on used sets.
- Treating race lap as measured fuel. It's a proxy that also carries track
  evolution; label it that way.
- Calling a slope from 3 or 4 clean laps reliable.
- Comparing raw average soft vs hard lap times. Teams pick compounds on
  purpose, so the comparison isn't fair.
- Removing traffic laps from the evaluation set as well as the training set.

## 8. References

1. OpenF1 docs: https://openf1.org/docs/
2. Cappello & Hoegh, "A State-Space Approach to Modeling Tire Degradation in
   Formula 1 Racing" (Montana State University). Preprint:
   https://arxiv.org/abs/2512.00640 . Uses FastF1, not OpenF1; models fuel as
   a fixed linear burn-off with an estimated coefficient, resets pace at pit
   stops, and validates with rolling-origin cross-validation. Useful for
   ideas; its pipeline doesn't transfer directly.
3. Tashman (2000), "Out-of-sample tests of forecasting accuracy: an analysis
   and review."
4. Hyndman & Athanasopoulos, *Forecasting: Principles and Practice*:
   https://otexts.com/fpp3/

The outside guide also cited "Rohan & Farhan (2026)" on piecewise vs linear
models. It could not be found. Don't cite it unless you locate it yourself.
