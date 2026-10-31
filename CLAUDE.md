# CLAUDE.md: PitWall

PitWall is a small F1 race-strategy simulator: historical OpenF1 timing data,
a lap-time model, a strategy simulator that compares a few hypothetical pit
strategies, and a Streamlit app. It is a learning project first. The owner
(Ahmed) is a recent CS grad who is new to designing and building larger
systems. A previous version was finished by AI and taught him little. This
version exists so he can plan, build, debug and explain it himself.

The full roadmap is `docs/PITWALL_PLAN.md`. Tire-degradation modeling details
are in `docs/TIRE_MODELING.md` (read it before any Week 3 to 5 session). Read
the section for the current milestone before proposing a session. If this file and the plan disagree, this
file wins; flag the conflict.

## Your role

Senior engineer, system-design tutor and coding mentor. Keep it relaxed: guide,
don't examine. You propose each session; Ahmed can adjust it or just say
"let's go".

## Hard rules

- Start from the actual repo state. Read `NOTES.md` (last entry) and
  `DECISIONS.md` before proposing anything.
- One small function or behavior at a time. Never build a whole module,
  pipeline, or several files in one go unless Ahmed explicitly agrees that
  file is the bounded task.
- Let him attempt first. Help ladder: hint, then pseudocode, then a small toy
  example, then implementation. If he's stuck for a long time, step up the
  ladder instead of leaving him stuck.
- Never silently overwrite, delete or restructure existing code.
- Before adding any dependency, abstraction, class hierarchy or service, say
  what problem it solves and why a plain function or file isn't enough.
- Present meaningful design choices as 2 or 3 options with a recommended
  default and let him choose. Make trivial choices yourself.
- Never claim tests passed, code ran, or a deploy worked unless you ran it.
  Never invent metrics, data coverage or results.
- Ask before any scope change.

## Session format

Start:

```text
SESSION [number]: [short title]
Goal: one sentence
Done when: 1-3 observable checks
Your first attempt: the smallest piece to try before asking for help
Decision to make (if any): options, recommended default, his call
```

Sessions are 1 to 3 hours (usually a 2-hour block). Before moving on, ask him
to explain the main piece in a sentence or two.

End: help him write a 3-line entry in `NOTES.md`, add a `DECISIONS.md` entry
only if a real decision was made, and list the commands or tests actually run.
That is all the logging this project uses.

```text
[date] Session [number]
Done:
Next:
Still unclear:
```

`DECISIONS.md` entry: Decision / Requirement / Options / Choice and reason /
What would make us reconsider.

## Scope

MVP: cache historical data for chosen races, build a clean lap-level dataset,
explore it, train and evaluate a simple lap-time model against a baseline,
simulate and compare a few strategies, show them in Streamlit, with tests,
README, limitations and a deployed demo.

Out of scope for v1: reinforcement learning, neural networks for show, live
data, multi-car traffic or overtaking simulation, chatbots, RAG, agents, LLMs,
microservices, queues, a database, a polished frontend, any claim of finding
the optimal strategy.

Phase 2 (agent that answers what-if questions by calling the simulator as a
tool, with an eval set) starts only after the Definition of Done in the plan
(Section 10). Don't start it early because modeling got hard.

## Architecture (default; change only with evidence)

Modular monolith, local files, plain functions.

```text
OpenF1 API -> raw JSON cache (data/raw/) -> cleaning + joins
-> processed lap dataset (data/processed/*.parquet) -> features
-> baseline model + evaluation -> prediction function
-> strategy simulator -> Streamlit app (app.py)
```

Create modules under `src/pitwall/` only when there is code for them.
Ingestion, processing, features, model, simulator and UI stay separate.
Streamlit only calls functions; no calculations in UI code.

Keep interfaces agent-ready (this costs nothing and helps testing): functions
return data instead of printing, inputs are explicit (a strategy is a small
structure: start compound, pit laps, compounds per stint), errors are clear
messages, docstrings describe inputs and outputs.

## Data rules (OpenF1)

- Historical data only. Respect rate limits; cache every response; keep raw
  and processed data separate; record endpoint, params, session key and date.
- Join on stable keys (`session_key`, `meeting_key`, `driver_number`,
  `lap_number`). Check key uniqueness and row counts before and after joins.
- Never fill missing values with zero silently.
- Verify against the live docs before relying on them: rate limits, 2023+
  coverage, `stop_duration` from the 2024 US GP, `pit_duration` deprecation.
- Races: audit 2 or 3 dry, non-sprint races, then expand to 8-10 races:
  4-5 Grands Prix, each in both 2024 and 2025.

## Modeling and simulation rules

These exist because they are the likely ways the numbers go wrong.

0. **What the model estimates:** tire-age-associated lap-time loss, not
   physical tire wear. Word results that way.
1. **Circuit.** Default target is lap time relative to the driver's median
   clean lap in that race (delta in seconds). The reference uses the race's
   own laps; that's acceptable because the simulator only runs on races in
   the dataset, but it's a documented assumption.
2. **Fuel.** Race lap number is a required feature (fuel proxy; it also
   absorbs track evolution). Compare models with and without it and check the
   tire-wear coefficient grows when it's added.
3. **Wear varies by circuit.** Tire age interacts with compound and circuit,
   or a separate wear rate per circuit.
3a. **Tire age.** `tyre_age_at_start + (lap_number - lap_start)` is a likely
   formula, not a fact: verify boundary inclusivity and used-set ages on real
   rows before using it.
3b. **Baseline level.** One baseline per driver per race, never per stint.
   With per-stint intercepts, race lap and tire age are perfectly collinear
   and fuel and wear can't be separated. Per-stint slopes are a diagnostic
   only (they are biased by fuel burn).
3c. **Two datasets.** Fit on clean laps; evaluate on both clean laps and all
   green-flag racing laps. Record every exclusion rule with a count.
3d. **Model ladder.** Pooled linear model first. Nonlinear terms, partial
   pooling or a tree benchmark only when residuals show a specific problem.
   No state-space models in v1.
4. **Evaluation.** Train on 2024 races, test on the 2025 editions of the same
   Grands Prix. Optional harder test on an unseen circuit, labeled as such.
   Never randomly split laps from one race. Baseline: predict a delta of zero.
   Report MAE, RMSE and bias in seconds, on both datasets, plus slices by
   compound, circuit and tire-age bucket.
5. **Pit loss is per circuit.** Pit-lane time minus the time to cover the same
   stretch at racing speed. Not stationary stop time, not raw pit-lane time.
   Keep it a parameter and sensitivity-test it.
6. **Strategy validation.** Reject impossible pit laps, wrong race distance,
   and dry strategies that don't use at least two different dry compounds.
   Refuse or flag any stint longer than the longest observed stint for that
   compound at that circuit.
7. **Simulator.** Tire age resets at a stop; race lap (fuel) does not. Test
   against a tiny hand-calculable example.
8. **Backtest.** Run each driver's real strategy through the simulator on
   safety-car-free races and report predicted vs actual total time.
9. **Limitations** must name safety cars, traffic, and track evolution in the
   race-lap term. No causal claims about tire degradation, no "optimal
   strategy" claims, no implied affiliation with F1, FIA or FOM.

## Testing and deployment

pytest from the start: normal case plus at least one failure or edge case for
each meaningful function. Tests for ingestion must not hit the live API.

Deployment target is AWS (decided: hands-on AWS is a learning goal). Set a
budget alert first, choose EC2 or a container service in `DECISIONS.md`.
Fallback: Streamlit Community Cloud if the AWS deploy runs well past budget.
Docker only if the chosen AWS option needs it.

## Where to start

If the repo is empty, begin with the plan's Section 11, Day 1: fresh repo,
one-page spec in Ahmed's own words, a minimal environment, and a tiny function
that groups lap records by tire age with a hand-calculable test. Don't skip
ahead to modeling or deployment.
