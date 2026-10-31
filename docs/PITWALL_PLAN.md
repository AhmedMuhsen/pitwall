# PitWall: Engineering-First Project Plan

## A deliberately scoped F1 race-strategy simulator

**Purpose:** Build a credible, evaluated, deployed ML product while
developing the ability to plan, implement, debug, and explain software
without outsourcing the thinking to AI.

**Time budget:** about 160--200 hours. At a realistic 10--15 hours/week
alongside the job search, that is roughly 3--4 months. The "weeks" in
Section 3 are milestones of about 20 hours each, not calendar weeks.\
**Expected outcome:** A functional portfolio product, not a
professional-grade race strategy engine.\
**Working rule:** You own the decisions. AI can help you understand,
review, debug, and implement bounded pieces, but it must not silently
take over the project.

------------------------------------------------------------------------

# 0. Read this before you start

You previously reached a point where the project became overwhelming and
let an AI tool finish large parts of it. That produced code without
enough understanding or ownership. This plan is designed specifically to
prevent repeating that pattern.

The uncomfortable truth: **a project that runs is not proof that you can
engineer it.** If you cannot explain the assumptions, trace the data,
diagnose a failure, or make a small change without asking an AI to
rewrite everything, the project is not yet doing its job as a learning
experience.

You are allowed to use AI. You are not allowed to use it as a substitute
for understanding.

## Non-negotiable rules

1.  **Write a short plan before writing code.** State the input, output,
    steps, and how you will test the result.
2.  **Make the smallest working change.** Do not ask an AI tool to build
    an entire pipeline, model, simulator, API, or app in one go.
3.  **Attempt the task yourself first.** Spend 15--25 focused minutes
    trying to solve it or writing pseudocode before asking for
    implementation help. Use documentation freely.
4.  **Ask for hints and reviews first.** If stuck, ask for a conceptual
    explanation, a hint, or a critique of your approach. Ask for full
    code only when a smaller explanation or example will not get you
    moving.
5.  **Never accept code you cannot explain.** You do not need to
    memorize every syntax detail, but you should understand each
    function's purpose, inputs, outputs, important branches,
    assumptions, and failure modes.
6.  **Test every meaningful component.** "It ran once" is not a test
    strategy.
7.  **Do not add a dependency or abstraction without a reason.** If an
    ordinary function solves the problem, do not build a class hierarchy
    or service architecture because an AI suggested it.
8.  **Do not expand scope to avoid hard work.** A new feature is not
    progress if the existing feature is not understood or evaluated.
9.  **Keep a decision log.** Record the decision, alternatives
    considered, reason, and remaining uncertainty.
10. **Keep job hunting.** This project is not permission to pause
    applications, networking, SQL, or interview preparation for two
    months.

## What "independent" means here

It does **not** mean writing every line without AI. It means you can: -
define a small task and split it into steps; - make a reasonable first
attempt; - use documentation to find unfamiliar syntax; - evaluate AI
suggestions instead of blindly accepting them; - inspect intermediate
values and debug failures; - explain what you built and why; - make a
small change without asking AI to replace the whole implementation.

If you cannot do those things yet, that is the skill you are practicing.

------------------------------------------------------------------------

# 1. Product definition

## Working name: PitWall

A small application that estimates lap-time behavior from historical F1
timing data and compares a few hypothetical pit-stop strategies.

## User problem

A fan chooses a race dataset and compares a small number of simplified
strategies, such as: - one stop versus two stops; - an earlier versus
later pit lap; - a different sequence of available tire compounds.

The application estimates total race time under its assumptions and
shows how sensitive the comparison is to uncertainty.

## MVP scope

The first portfolio-ready version must do these things:

1.  Retrieve and cache historical data for a small, documented set of
    races.
2.  Produce a clean lap-level dataset with tire compound and tire age
    where the source data supports it.
3.  Plot observed lap time against tire age and race lap, and separate
    the three big effects on lap time: circuit, fuel load and tire wear
    (see Section 2.1).
4.  Train a simple baseline model for lap-time prediction that accounts
    for circuit and fuel, not only tire age.
5.  Evaluate it on held-out races (the 2025 editions of Grands Prix the
    model saw in 2024), not a random split of individual laps from the
    same race.
6.  Simulate a limited set of hypothetical strategies using predicted
    lap times, fuel burn, explicit pit-loss assumptions and the
    two-compound rule.
7.  Compare strategies in a simple Streamlit interface.
8.  Include tests, a README, limitations, reproducible instructions, and
    a public demo if feasible.

## Explicitly out of scope

Do **not** build these for the first version: - reinforcement
learning; - a neural network just to make the project sound more
advanced; - live race recommendations; - real-time telemetry
ingestion; - a detailed multi-car traffic/overtaking/aerodynamics
simulator; - a chatbot or RAG layer; - microservices, Kubernetes,
message queues, or a complex cloud architecture; - a polished
commercial-grade frontend; - claims that the simulator finds the actual
optimal strategy.

These may sound impressive, but they multiply the number of things you
must understand. You need a sound, evaluated core before adding
complexity.

## Success criteria

By the end, a reviewer should be able to: - clone the repository and
follow the setup instructions; - understand the data sources and
assumptions; - run the data pipeline and tests; - see measured model
performance against a simple baseline; - compare at least two
strategies; - use the demo or reproduce an example locally; - read the
limitations and understand what the model does **not** establish.

The success criterion is not "the app has many features." It is "the app
is credible, reproducible, understandable, and honest about
uncertainty."

------------------------------------------------------------------------

# 2. Data source research and data choice

## Primary source: OpenF1

Official documentation: - API docs: https://openf1.org/docs/ - Main
site, access, limitations, and terms context: https://openf1.org/

OpenF1 describes itself as an independent, unofficial API. Its published
free tier includes historical sessions from **2023 onward**, with no
authentication required for historical data. The site lists limits of
**3 requests/second and 30 requests/minute** for the free tier. Live
data requires a paid tier. It supports JSON by default and CSV with
`csv=true`.

**Do not plan around seasons before 2023.** They are outside the
historical coverage OpenF1 advertises. Do not assume the API will
provide every field uniformly across every event or year; inspect the
actual responses for your selected sessions.

OpenF1 says its intended uses include educational projects, personal
learning, research, and non-commercial fan engagement. If you later
intend commercial use, contact OpenF1 and review applicable
data/trademark rights. Do not imply affiliation with Formula 1, FIA, or
FOM.

## Which years should you use?

Use **2024 and 2025 as your initial candidate seasons**, then choose
specific races after checking endpoint coverage. They are complete
seasons in this plan's time context and reduce the temptation to rely on
an in-progress 2026 season.

Use 2023 only if you need more examples after the first data audit. It
is within OpenF1's advertised historical coverage, but older coverage
should be checked field by field rather than assumed identical.

Important distinction: - Historical session, lap, stint, pit, and
weather endpoints exist in OpenF1's API documentation. - OpenF1
documents `stop_duration` as available only from the **2024 United
States Grand Prix onward**. Do not assume stationary pit-stop duration
is available for earlier races. - The `pit_duration` field is marked
deprecated and is documented as scheduled for removal at the end of the
2026 season. Avoid making your code depend on a deprecated field without
a fallback. - For the MVP, use a documented, explicit pit-loss
assumption or a clearly defined pit-lane-duration field. Do not pretend
a stationary stop time is the full time loss of a pit stop; it is not. -
If you use a fixed pit-loss constant, identify it as an assumption and
test how results change when it varies.

## Initial dataset selection

Audit **two or three dry, non-sprint Grand Prix races** first. Once
ingestion works, expand to **8--10 dry races: 4--5 Grands Prix, each in
both 2024 and 2025.** That pairing is what the evaluation in Week 4
depends on, so only pick Grands Prix with usable data in both years.
Each race should have: - a normal race session; - useful lap-time records; -
stint records with compound and tire-age-at-start information; - pit
events; - weather data if you want to examine track conditions; - enough
completed laps to compare stints.

Do not pick races because they produce a convenient story. Pick them
after checking data availability.

A sensible first audit is to compare a few races with different
characteristics: - one relatively straightforward dry race; - one race
with a meaningful variety of tire stints; - optionally one race with
more complications to test how your assumptions fail.

Do not begin with a wet, red-flag-heavy, sprint-format, or unusually
disrupted race as your only dataset. Those can be added later as stress
tests.

## 2.1 What actually sets a lap time

A race lap time is roughly the sum of five things:

-   **Circuit.** The track's length and layout set the base time. A
    Monaco lap and a Spa lap are about 30 seconds apart on any tire.
    This is by far the biggest effect.
-   **Fuel load.** Cars start heavy and get faster as fuel burns, by a
    roughly steady amount per lap. Race lap number is a usable proxy for
    fuel burned (it also picks up track evolution, which improves the
    track over a race; note that in your limitations).
-   **Tire wear.** Laps get slower as the tire ages, at a rate that
    depends on compound and circuit.
-   **Driver and car.** Some cars are simply faster.
-   **Noise and disruptions.** Traffic, safety cars, mistakes, weather.

Two consequences shape the rest of this plan:

1.  **Circuit must be handled explicitly.** If the model doesn't know
    which track a lap comes from, most of its error is just the track.
    The default here is to predict lap time *relative to a reference for
    that race* (for example, the driver's median clean lap in that race),
    which removes most of the circuit and car effect. Then test on the
    same circuits in a later year. That matches how the simulator is
    used: it only ever simulates races that exist in the dataset.
2.  **Fuel and tire age must be separated.** Within a stint, tire age and
    fuel burned both go up by one every lap. A model given only tire age
    credits the fuel gain to the tires and underestimates wear, and the
    simulator then favors long stints and one-stop strategies for the
    wrong reason. Tire age resets at a pit stop while race lap keeps
    counting, so multi-stint data is what lets the model tell them apart.
3.  **Tire wear rate depends on the circuit.** Some tracks are far
    harder on tires than others. One wear rate per compound across all
    circuits is wrong even with the relative target. The model needs
    tire age to interact with compound and circuit, or a separate wear
    rate per circuit.
4.  **The data only covers stints teams chose to run.** Teams avoid
    stints where the tires would fall apart, so very long stints on soft
    compounds may never appear. The model knows nothing past the longest
    observed stint for a compound at a circuit, and the simulator must
    not pretend otherwise.

## 2.2 Facts to verify on Day 2

This plan states some OpenF1 details that may be out of date or wrong:
the free-tier rate limits, 2023-onward historical coverage,
`stop_duration` starting at the 2024 United States Grand Prix, and
`pit_duration` being deprecated. Check each one against the live docs
before writing code that depends on it, and record any difference in
`DECISIONS.md`.

## Endpoints to investigate

Use only the endpoints needed for the current milestone.

  -----------------------------------------------------------------------
  Endpoint                Why it matters          MVP priority
  ----------------------- ----------------------- -----------------------
  `/sessions`             Identify session keys,  Required
                          year, session           
                          name/type, meeting,     
                          dates                   

  `/meetings`             Identify event/circuit  Useful
                          metadata                

  `/laps`                 Lap number, lap         Required
                          duration, out-lap       
                          indicator, sector times 

  `/stints`               Compound, stint         Required
                          boundaries, tire age at 
                          stint start             

  `/pit`                  Pit-lane/pit-stop       Useful
                          timing information      
                          where available         

  `/weather`              Air/track temperature,  Optional initially
                          rainfall, wind,         
                          humidity                

  `/race_control`         Flags, safety-car and   Optional; useful for
                          race-control messages   filtering disrupted
                                                  laps

  `/session_result`       Final result and        Optional for context,
                          session-level outcome   not a strategy ground
                                                  truth
  -----------------------------------------------------------------------

Documentation pages describe fields and filtering: - Sessions:
https://openf1.org/docs/#sessions - Laps:
https://openf1.org/docs/#laps - Stints:
https://openf1.org/docs/#stints - Pit: https://openf1.org/docs/#pit -
Weather: https://openf1.org/docs/#weather - Race control:
https://openf1.org/docs/#race-control

Check the current documentation if anchor links change.

## Data retrieval rules

-   Use the API for historical data, not live endpoints.
-   Query only the sessions you need; do not download everything on day
    one.
-   Respect the published rate limits. Cache every successful response
    locally.
-   Save raw responses separately from cleaned data.
-   Record the request parameters, retrieval date, session key, and
    endpoint for each cached file.
-   Handle empty responses, HTTP errors, unexpected JSON shapes, and
    missing fields.
-   Do not silently replace missing values with zero.
-   Do not hard-code session keys without recording what session each
    key represents.
-   Use stable identifiers such as `session_key`, `meeting_key`,
    `driver_number`, and `lap_number` when joining records.
-   Inspect whether join keys are unique before merging. Check row
    counts before and after joins.
-   Do not assume lap numbers alone uniquely identify a lap. They repeat
    across drivers and sessions.

## Suggested local data layout

Keep the first version simple:

``` text
data/
  raw/
    sessions/
    laps/
    stints/
    pit/
    weather/
    race_control/
  processed/
    lap_dataset.parquet
```

Keep raw data out of Git if files become large or
licensing/redistribution considerations make sharing inappropriate.
Commit a small sample or provide a reproducible download script instead.
Document how to obtain the data.

------------------------------------------------------------------------

# 3. The 10-week plan

Each "week" below is a milestone of about 20 hours. At 10--15 hours a
week, most will take longer than a calendar week. The total is roughly
200 hours. It is a plan, not a deadline to fake progress against.

**Session structure (for a 2-hour block)** - 10 minutes: agree on
today's goal with your guide. - About 80 minutes: focused work,
including docs, coding, and debugging. - 20 minutes: test and review
what changed. - 10 minutes: the 3-line session note, plus a
`DECISIONS.md` entry if you made a real decision.

You can change the distribution when a task needs uninterrupted work,
but do not eliminate testing and review.

## Week 1 --- Development process, API reconnaissance, and feasibility

**Budget: 20 hours**

### Goals

-   Set up a clean repository.
-   Understand the OpenF1 API enough to retrieve one session.
-   Inspect real data before designing the rest of the system.
-   Practice small Python functions without AI writing everything.

### Tasks

1.  Create a new repository or a clean branch/repository for the
    restart. Preserve the old project as an archive; do not blindly copy
    its architecture.
2.  Write the one-page product specification from Section 1 in your own
    words.
3.  Create a minimal Python environment and install only the libraries
    you currently need: `requests`, `pandas`, `pyarrow`, `matplotlib`,
    `scikit-learn`, and `pytest` can be introduced as needed. Do not
    install everything just because it is listed here.
4.  Read the OpenF1 docs for sessions, laps, stints, pit, and weather.
5.  Query `/sessions` for 2024 and 2025. Identify race sessions for
    candidate meetings.
6.  Choose two or three candidate race sessions.
7.  Fetch laps and stints for one session. Inspect the raw JSON
    structure.
8.  Write small exercises: calculate an average, filter a list, group
    lap times by tire age, and test empty/missing inputs.
9.  Record which fields exist and which are missing for each candidate
    race.
10. Write a short feasibility note: which races you selected, why, what
    fields are available, and what remains uncertain.

### Deliverable

A repository with a README, a working one-session data retrieval
experiment, a small data audit, and a decision log.

### Exit check

Can you explain the difference between a meeting, a session, a lap, and
a stint? Can you retrieve a session without copying a complete generated
script? Can you inspect the response and describe the key fields?

**Do not proceed to a large pipeline if you cannot do these things.**

## Week 2 --- Data ingestion and caching

**Budget: 20 hours**

### Goals

Build a small, repeatable ingestion process with sensible failure
handling.

### Tasks

1.  Write one function that requests one endpoint for one session.
2.  Understand HTTP status codes, timeouts, JSON parsing, and error
    handling.
3.  Save the raw response locally.
4.  Add caching so repeated runs do not unnecessarily call the API.
5.  Add a small configuration for selected session keys.
6.  Retrieve laps and stints for the selected races. Add pit and weather
    data only after the required data works.
7.  Inspect row counts, column names, duplicates, missing values, and
    data types.
8.  Write tests for a successful response, empty response, HTTP failure,
    malformed response, and cache hit.
9.  Add logging or clear error messages. Do not swallow errors silently.

### Deliverable

A repeatable script that fetches and caches the required historical
records for the selected sessions.

### Exit check

Can you explain the data flow from API request to saved file? Can you
test a failure case without calling the real API? Can you explain why
caching is useful?

## Week 3 --- Build the lap-level dataset

**Budget: 20 hours**

### Goals

Join the source tables correctly and understand the data before
modeling.

### Tasks

1.  Define the grain of the dataset: one row per driver per session per
    lap.
2.  Identify the join keys for laps and stints. Do not assume the merge
    is correct merely because pandas permits it.
3.  Attach compound, stint number, stint boundaries, and tire age.
    Keep race lap number as its own column (the fuel proxy), and record
    each race's circuit and year. Also save, per circuit and compound,
    the longest observed stint. The simulator uses it in Week 6.
4.  Derive tire age from stint start only if the meaning of the field
    supports that calculation. Document the exact formula and verify it
    on sample rows, including whether stint boundaries are inclusive and
    that used sets don't reset to zero (`docs/TIRE_MODELING.md`,
    Section 2).
5.  Identify missing lap durations and invalid values.
6.  Exclude or flag out-laps and pit-affected laps where appropriate.
    Document the rule instead of silently dropping rows. Keep two
    datasets: a clean one for fitting and a racing one (all green-flag
    laps) for evaluation (`docs/TIRE_MODELING.md`, Section 3).
7.  Inspect safety-car, yellow-flag, wet-weather, red-flag, and other
    disruptions if the chosen races contain them. Start by documenting
    them; do not build a sophisticated race-control parser unless
    needed.
8.  Save the processed dataset as Parquet.
9.  Produce a data-quality report: rows before/after joins, missingness,
    duplicates, and exclusion counts.
10. Make plots of lap time by tire age, compound, and driver for
    selected stints, and lap time against race lap across a whole race
    to see the fuel effect.

### Deliverable

A reproducible processing script, a cleaned dataset, data-quality
checks, and a short exploratory analysis.

### Exit check

Can you explain why each join is valid? Can you show that row counts
have not unexpectedly multiplied? Can you explain which laps were
excluded and why?

## Week 4 --- Define the prediction task and baseline

**Budget: 20 hours**

### Goals

Build a baseline before attempting anything sophisticated.

### Tasks

1.  Define the target clearly. Default: lap time relative to that
    driver's median clean lap in that race (a delta in seconds), which
    removes most of the circuit and car effect. The alternative is raw
    lap time with circuit as a feature. Choose one and record why in
    `DECISIONS.md`. Note that the reference is computed from the race
    itself; that is acceptable because the simulator only works on races
    whose data exists, but write the assumption down.
2.  Decide which features are legitimate and available at prediction
    time. At minimum: tire age, compound, and race lap (fuel proxy),
    with tire age interacting with compound and circuit (or a separate
    wear rate per circuit). See Section 2.1, point 3.
3.  Establish a naive baseline: predict a delta of zero (every lap equals
    the driver's typical lap).
4.  Main split: train on the 2024 races, test on the 2025 editions of
    the same Grands Prix. This matches how the simulator is used.
    Optionally report a second score on a circuit the model never saw,
    labeled as a harder test. Never randomly split laps from the same
    race.
5.  Build a basic scikit-learn pipeline. Begin with a simple regression
    model.
6.  Compare three models on the same split: the zero baseline, tire age
    and compound only, and tire age and compound plus race lap. Check
    how the tire-wear coefficient changes when race lap is added. You
    should expect it to grow; if it doesn't, find out why. The model
    form, and why the baseline must be per driver per race rather than
    per stint, are in `docs/TIRE_MODELING.md`, Section 4. Per-stint
    slopes are a diagnostic only.
7.  Use MAE, RMSE and bias, on both the clean and the racing datasets,
    and inspect error slices rather than only reporting one score
    (`docs/TIRE_MODELING.md`, Section 5).
8.  Save the split definition and experiment results so you can
    reproduce them.
9.  Investigate leakage risks and confounders such as driver pace,
    circuit, compound, fuel load, traffic, track evolution, weather, and
    safety-car periods.
10. Write down what the model can and cannot claim.

### Deliverable

A baseline model, an evaluation script, an error analysis, and a short
model card or evaluation note.

### Exit check

Can you explain the train/test split? Why is a random lap split risky?
What does MAE mean in seconds? What baseline does the model need to
beat? What does the score not prove?

## Week 5 --- Improve the model only if the evidence supports it

**Budget: 20 hours**

### Goals

Make one justified improvement and determine whether it actually helps.

### Tasks

1.  Inspect residuals by tire age, race lap, compound, circuit, driver,
    session, and weather where data supports it. A pattern by circuit
    means the wear-rate interaction isn't doing its job.
2.  Check whether the baseline misses systematic patterns.
3.  Try one improvement at a time, chosen from what the residuals
    show (table in `docs/TIRE_MODELING.md`, Section 4, Step 3):
    a nonlinear tire-age term, partial pooling, or a tree-based
    benchmark.
4.  Compare the new model to the baseline on the same held-out sessions.
5.  Avoid a giant hyperparameter search. You need to understand the
    experiment.
6.  Test sensitivity to excluded laps and feature choices.
7.  Keep the simpler model if the improvement is weak or unreliable.
8.  Document uncertainty and data limitations. A model can predict lap
    times without identifying causal tire degradation.

### Deliverable

A chosen model with a justified reason for selecting it, comparative
metrics, error plots, and limitations.

### Exit check

Can you explain why you tried the new model? Did it improve held-out
results? Is the difference meaningful enough to justify added
complexity?

**Do not claim to have isolated tire degradation if your model has not
separated it from other causes of lap-time change.**

## Week 6 --- Design and implement a simple strategy simulator

**Budget: 20 hours**

### Goals

Turn predictions into a transparent comparison of hypothetical
strategies.

### Tasks

1.  Define a strategy representation: race distance, starting compound,
    sequence of compounds, and pit laps.
2.  Write a plain-English description of how a strategy becomes a
    sequence of predicted lap times.
3.  Decide how tire age resets after a stop and how the next stint's
    compound and age are set. Race lap, and with it the fuel effect,
    keeps counting across stops.
4.  Define pit loss per circuit, because pit lanes differ in length.
    Pit loss is pit-lane time minus the time it takes to cover the same
    stretch at racing speed, not pit-lane time alone and not stationary
    stop duration. Estimate it per circuit from the data, document the
    method, and keep it as a parameter so it can be sensitivity-tested.
5.  Implement the simulator as small functions with explicit inputs and
    outputs.
6.  Start with two manually specified strategies, not an optimizer.
7.  Add validation for impossible pit laps, invalid compounds, missing
    predictions, mismatched race distance, and the dry-race rule that
    each car must use at least two different dry compounds (confirm the
    wording in the current FIA Sporting Regulations). Also refuse, or
    clearly flag, any stint longer than the longest observed stint for
    that compound at that circuit (saved in Week 3). The simulator must
    not invent tire behavior outside the data.
8.  Write unit tests for a tiny hand-calculable example.
9.  Verify the simulator against a manual calculation on a small
    example.
10. Record all simplifying assumptions, including the lack of detailed
    traffic and overtaking simulation and the lack of safety cars. Safety
    cars change real strategy calls a lot, and v1 does not model them.

### Deliverable

A tested function that calculates estimated total time for a specified
strategy under explicit assumptions.

### Exit check

Can you trace one strategy lap by lap? Can you explain how the tire age
changes at a pit stop while race lap doesn't? Can you manually verify a
tiny example? Does a strategy that uses only one dry compound get
rejected? Does a stint longer than anything observed get refused or
flagged?

## Week 7 --- Compare strategies and represent uncertainty

**Budget: 20 hours**

### Goals

Make the comparison useful without pretending the output is certain.

### Tasks

1.  Compare a small set of strategies: for example, one-stop versus
    two-stop, and early versus late stop.
2.  Keep the strategy set constrained and explain how it was selected.
3.  Add uncertainty only after the deterministic simulator works. Start
    with a simple sensitivity analysis over plausible pit-loss values, the
    fuel effect, or model errors.
4.  If sampling parameter or prediction uncertainty, document where the
    sampled values come from. Do not invent a probability distribution
    merely to make a chart look scientific.
5.  Report estimated total time, time difference versus a baseline
    strategy, and sensitivity to assumptions.
6.  If you display prediction intervals, explain what they represent and
    how they were generated.
7.  Backtest the simulator end to end: run each driver's actual
    strategy through it and compare the predicted total race time with
    the real one, on races without safety cars. Report the error in
    seconds and per lap. This is the main evidence that the whole chain
    (dataset, model, fuel, pit loss, simulator) holds together. Real
    teams' choices are still not a ground-truth optimal strategy.
8.  Test repeatability with a fixed random seed if randomness is used.
9.  Inspect implausible outputs and identify their cause instead of
    hiding them.

### Deliverable

A strategy comparison module with transparent assumptions and an
uncertainty/sensitivity explanation.

### Exit check

Can you explain why the top-ranked strategy wins under your model? Could
a different pit-loss assumption change the ranking? How far off is the
simulator on real strategies from safety-car-free races? What important
real-world effects are absent?

## Week 8 --- Build the smallest usable product

**Budget: 20 hours**

### Goals

Make the core functionality accessible to another person.

### Tasks

1.  Use Streamlit for a simple interface. Do not build a separate
    frontend unless you have a compelling reason.
2.  Let the user select a supported race/session and a small set of
    strategy parameters.
3.  Show a comparison table and one or two useful plots.
4.  Display assumptions, dataset scope, model evaluation summary, and
    limitations in the app or accompanying documentation.
5.  Validate user inputs and display actionable errors.
6.  Keep the data/model/simulator logic separate from UI code so the
    core can be tested without Streamlit.
7.  Run the application from a clean environment using written setup
    instructions.
8.  Add a small example or fallback mode if a remote data request fails,
    but label cached/example data clearly.
9.  Avoid adding accounts, databases, or authentication unless they are
    truly needed.

### Deliverable

A locally usable application that connects data, model, and simulator.

### Exit check

Can another person run it using the README? Can the app recover
gracefully from invalid input? Does it distinguish estimates from facts?

## Week 9 --- Testing, deployment, and reliability

**Budget: 20 hours**

### Goals

Make the application reproducible and accessible.

### Tasks

1.  Expand unit tests for data processing, prediction inputs, simulator
    edge cases, and strategy validation.
2.  Add at least one end-to-end test using a small cached dataset.
3.  Check for secrets, personal tokens, unnecessary raw data, and large
    generated files before pushing.
4.  Pin or document dependencies in a reproducible environment.
5.  Add a basic CI workflow to run tests if you can do so without
    derailing the project.
6.  Deploy on AWS. This is a deliberate choice: hands-on AWS is a
    learning goal. Set a budget alert first, choose between EC2 and a
    container service in `DECISIONS.md`, and keep Streamlit Community
    Cloud as the fallback if the AWS deploy runs well past its time
    budget.
7.  Test the deployed version from a clean browser/session.
8.  Document known failures, data retrieval behavior, and any hosting
    limitations.
9.  Do not introduce Docker merely as decoration. Add it only if it
    solves a real reproducibility or deployment need and you understand
    the configuration.

### Deliverable

A deployed demo, a reproducible local setup, and automated tests for
core logic.

### Exit check

Can you reproduce the main output? Do tests catch a deliberate invalid
input? Does the deployed app work without your local files?

## Week 10 --- Portfolio quality, feedback, and interview readiness

**Budget: 20 hours**

### Goals

Make the project understandable to hiring managers and engineers.

### Tasks

1.  Rewrite the README so it explains the problem, architecture, setup,
    data, evaluation, results, limitations, and demo. Limitations must
    include safety cars, traffic, and track evolution being folded into
    the race-lap term.
2.  Add a simple architecture diagram showing the data flow.
3.  Include one example output and a short explanation of what it means.
4.  Publish a concise technical write-up describing one difficult
    decision, one failed approach, and one lesson.
5.  Ask a few people who understand Python, ML, or F1 to try the demo or
    review the repository.
6.  Record their confusion and bugs; fix the most important issues.
7.  Prepare a 5-minute walkthrough and a 15-minute technical discussion.
8.  Practice explaining model selection, leakage, evaluation, data
    joins, pit-loss assumptions, uncertainty, and limitations without
    reading the README.
9.  Make a final pass for unsupported performance claims or inflated
    descriptions.
10. Write down the next improvements, but do not keep expanding the
    project indefinitely.

### Deliverable

A portfolio-ready repository, a demo, an honest evaluation report,
feedback-driven improvements, and an interview walkthrough.

### Exit check

Can you explain the project without relying on AI to narrate it? Can you
make a small code change during a discussion? Can you state the model's
limitations without getting defensive?

------------------------------------------------------------------------

# 4. How to work when you get stuck

Getting stuck is expected. Repeatedly asking AI to finish the task is
not an acceptable default.

Use this protocol.

## Step 1: State the exact problem

Bad: "My code doesn't work. Fix it."

Better: - What did I expect? - What happened instead? - What input
caused it? - What error or unexpected output did I see? - What have I
checked already?

## Step 2: Inspect the smallest failing example

Reduce the problem. Use a few rows instead of the full dataset. Print
shapes, column names, types, and intermediate values. For functions,
create a tiny test case whose result you can calculate manually.

## Step 3: Form a hypothesis

Write one sentence such as: - "I think the merge duplicates rows because
the stint table has overlapping or repeated keys." - "I think tire age
is off by one because the stint start lap is included in the wrong
way." - "I think the evaluation split leaks race-specific patterns
because laps from the same session appear in both sets."

Your hypothesis can be wrong. The point is to practice reasoning.

## Step 4: Research in this order

1.  Python official tutorial: https://docs.python.org/3/tutorial/
2.  Python standard library reference:
    https://docs.python.org/3/library/
3.  pandas getting started:
    https://pandas.pydata.org/docs/getting_started/
4.  pandas user guide: https://pandas.pydata.org/docs/user_guide/
5.  scikit-learn getting started:
    https://scikit-learn.org/stable/getting_started.html
6.  scikit-learn model evaluation:
    https://scikit-learn.org/stable/modules/model_evaluation.html
7.  pytest getting started:
    https://docs.pytest.org/en/stable/getting-started.html
8.  OpenF1 API docs: https://openf1.org/docs/
9.  Search the exact error message or ask AI to explain the relevant
    documentation section.

Do not watch hours of broad tutorials when you need to understand one
specific function or error. Look for the smallest explanation that
addresses the problem, then return to your code.

## Step 5: Ask AI for targeted help

Use prompts like:

> I am building PitWall. My goal is \[specific outcome\]. My input is
> \[shape/example\]. I expected \[result\] but got \[actual result\]. My
> current hypothesis is \[hypothesis\]. Please help me test this
> hypothesis and give me hints before suggesting a complete rewrite.
> Explain unfamiliar concepts and identify a small test I can run.

Or:

> Review this function for correctness and edge cases. Do not rewrite it
> yet. Explain the first issue you see and ask me to reason about the
> fix.

Or:

> Give me a minimal example of the relevant pandas/scikit-learn concept
> using toy data. Do not build the full project component.

## Step 6: Set a time limit without outsourcing the task

Try for 15--25 minutes first. If you are making no progress, ask for a
hint. If you remain stuck, ask for a minimal example or implementation,
then study and test it.

Do not spend three hours stubbornly guessing at unfamiliar syntax. That
is not independence. But do not let the first error trigger a full AI
rewrite either.

## Step 7: Close the loop

After receiving help: - explain what was wrong; - write a test that
would catch it; - make a small modification yourself; - add it to
"Still unclear" in your session note if it exposed a recurring gap.

If you cannot explain the solution afterward, you have not finished the
task.

------------------------------------------------------------------------

# 5. AI usage policy

## Good uses of AI

-   Explain unfamiliar concepts or documentation.
-   Critique your proposed design.
-   Suggest edge cases and tests.
-   Help interpret stack traces.
-   Review a function you wrote.
-   Show a minimal example of a library API.
-   Generate boilerplate when you understand its purpose.
-   Compare approaches and explain trade-offs.
-   Help you write documentation based on work you can verify.

## Risky uses of AI

-   "Build the whole project."
-   "Implement the entire data pipeline."
-   "Fix everything and return the complete files."
-   Accepting a new framework or dependency without understanding why it
    is needed.
-   Copying a 30-line function, running it once, and moving on.
-   Asking AI to write tests for code you don't understand, then
    treating passing tests as proof of correctness.
-   Letting AI invent model results, data coverage, assumptions, or
    performance claims.
-   Using a sophisticated model because it sounds better on a résumé.

## Before accepting a generated function, answer these questions

1.  What does the function do?
2.  What are its inputs and outputs?
3.  What assumptions does it make?
4.  What happens on empty, malformed, or unexpected input?
5.  Which line performs the core operation?
6.  How could I test it?
7.  Can I modify one behavior without asking AI to rewrite the whole
    function?

If you cannot answer these questions, stop and learn the function before
integrating it.

------------------------------------------------------------------------

# 6. Weekly check-in

During your Sunday review, answer one question: could I explain and
change this week's PitWall code without AI? If the answer is no two weeks
in a row, slow down and revisit before adding anything new.

------------------------------------------------------------------------

# 7. Technical design guardrails

## Keep the architecture boring

A reasonable first architecture is:

``` text
OpenF1 API
    |
    v
Raw JSON cache
    |
    v
Data cleaning and joins
    |
    v
Processed lap-level dataset
    |
    v
Baseline ML model
    |
    v
Strategy simulator
    |
    v
Streamlit application
```

You do not need a separate backend API for the first version. You do not
need a database if local cached files are sufficient. You do not need a
neural network. Start with functions and modules that have clear
responsibilities.

A possible structure, to adapt only when the need becomes clear:

``` text
pitwall/
  README.md
  requirements.txt
  .gitignore
  data/
    raw/
    processed/
  src/
    pitwall/
      data_ingestion.py
      data_processing.py
      features.py
      model.py
      simulator.py
  app.py
  tests/
    test_data_processing.py
    test_simulator.py
```

Do not create empty modules simply to match this diagram. Add files when
there is code that belongs in them.

## Keep concerns separate

-   **Ingestion:** get source data and cache it.
-   **Processing:** validate, clean, join, and transform records.
-   **Features:** define model inputs.
-   **Model:** train, predict, and evaluate.
-   **Simulator:** calculate hypothetical strategy outcomes from
    predictions and assumptions.
-   **UI:** collect user inputs and present results.

The separation exists to make the code easier to reason about and test,
not to make the architecture look professional.

## Avoid leakage and misleading evaluation

-   Do not randomly split laps from the same race across training and
    test sets and present the result as evidence of generalization to
    new races.
-   Prefer holding out whole sessions or races. If possible, use
    time-aware or season-aware evaluation to test the intended use.
-   Make sure features are actually available at the point when a
    prediction is supposed to be made.
-   Do not treat final race results as the optimal strategy label.
-   Do not interpret a predictive association between tire age and lap
    time as a clean causal estimate of tire degradation.
-   Report the baseline and error slices, not only the best headline
    score.
-   If results are poor, investigate and report them honestly. A
    well-explained failed experiment can still be valuable engineering
    work.

## Pit-loss assumptions

Be precise about what the source fields represent: - stationary stop
duration is not the same as total pit-lane time loss; - pit-lane
duration is not automatically the time loss relative to staying on
track; - a constant pit-loss assumption may be useful for an MVP, but it
is an assumption.

For the first version, a transparent per-circuit pit-loss parameter
(pit-lane time minus the time to cover the same stretch at racing
speed) with a sensitivity analysis is acceptable. One constant for every
circuit is not, because pit lanes differ in length. State that it is simplified. Do not
call it a learned or measured race-specific loss unless your method
actually estimates that quantity.

------------------------------------------------------------------------

# 8. Job-search integration

The project should improve your candidacy, not consume your entire
professional life.

During the 10-week project: - keep applying and networking; - continue
interview practice and SQL work; - reserve a fixed amount of time for
the project instead of letting it expand endlessly; - use project
progress as a source for networking conversations when you have a
concrete milestone; - do not wait for the final deployed demo before
applying.

Once you have a working data pipeline or baseline model, you can
describe that progress honestly. Do not claim the simulator is complete
before it works, or claim performance improvements you have not
measured.

The strongest résumé bullet will come from a specific, defensible
result: what you built, what data it uses, how you evaluated it, and
what a user can do with it. Do not invent a business impact number for a
portfolio project.

------------------------------------------------------------------------

# 9. What to do if the schedule slips

The schedule is an estimate, not a reason to rush past learning.

If a milestone takes longer: 1. Identify the specific blocker. 2. Reduce
the scope of the current task. 3. Review whether you understand the
relevant concept. 4. Seek targeted help. 5. Complete and test the
smaller task. 6. Move the schedule if needed.

Cut scope in this order: 1. Optional weather features. 2. Advanced
uncertainty modeling. 3. Extra strategy types. 4. Additional UI polish.
5. AWS deployment (fall back to Streamlit Community Cloud).

Do **not** cut these: - data-quality checks; - the paired 2024/2025
races the evaluation depends on; - the fuel term in the model; - the
simulator backtest; - the observed-range guard; - a
baseline model; - held-out evaluation; - simulator tests; - explicit assumptions and
limitations; - your own understanding of the code.

If after the first two weeks you are still unable to explain the data
flow, do not add ML. If the baseline model is not evaluated, do not add
a sophisticated model. If the simulator is not tested, do not build the
interface.

------------------------------------------------------------------------

# 10. Definition of done

The project is complete enough for a portfolio when all of the following
are true:

-   [ ] The README explains the problem, setup, architecture, data
    source, and limitations.
-   [ ] The data retrieval process is repeatable and respects API
    limits.
-   [ ] Raw and processed data are clearly separated.
-   [ ] Joins, row counts, missing values, and exclusions are checked.
-   [ ] A baseline is reported.
-   [ ] Circuit and fuel effects are handled explicitly and explained,
    and tire wear rate varies by circuit.
-   [ ] The model is evaluated on the 2025 editions of races it saw in
    2024.
-   [ ] The evaluation discusses confounding factors and leakage risks.
-   [ ] The simulator compares at least two strategies and rejects
    strategies that break the two-compound rule.
-   [ ] Pit loss is per circuit, explicit, and not misrepresented.
-   [ ] The simulator refuses or flags stints beyond the observed range.
-   [ ] The simulator is backtested on real strategies from
    safety-car-free races, with the error reported.
-   [ ] Limitations name safety cars, traffic, and track evolution.
-   [ ] Core data-processing and simulation functions have tests.
-   [ ] The app displays useful output and handles invalid input.
-   [ ] Another person can follow the setup instructions.
-   [ ] The demo is deployed if feasible, or deployment limitations are
    explained.
-   [ ] You can walk through the data flow and architecture without AI
    narrating it.
-   [ ] You can explain model evaluation, major assumptions, and failure
    modes.
-   [ ] You can make a small modification to a core function and test
    it.
-   [ ] You have not made unsupported claims about accuracy or optimal
    strategy.

If the application is visually polished but these boxes are not checked,
it is not done.

------------------------------------------------------------------------

# 11. First five working days: exact starting checklist

Do not attempt the entire roadmap at once. Start here.

## Day 1 --- Specification and Python exercise

-   [ ] Create the fresh repository.
-   [ ] Write the one-page specification.
-   [ ] Create a minimal Python environment.
-   [ ] Implement a tiny function that groups lap records by tire age
    and calculates average lap time.
-   [ ] Test it on a hand-calculable example.
-   [ ] Explain each line in your own words.

## Day 2 --- OpenF1 exploration

-   [ ] Read the sessions, laps, and stints documentation.
-   [ ] Verify the OpenF1 facts listed in Section 2.2.
-   [ ] Query 2024 and 2025 race sessions.
-   [ ] Select one candidate race.
-   [ ] Fetch its session metadata, laps, and stints.
-   [ ] Inspect the raw response and write down the fields you
    understand and do not understand.

## Day 3 --- Data audit

-   [ ] Check row counts, column names, missing values, and duplicates.
-   [ ] Identify join keys.
-   [ ] Inspect a few drivers' laps and stints manually.
-   [ ] Verify how tire age can be represented.
-   [ ] Note any missing or inconsistent information.

## Day 4 --- First small analysis

-   [ ] Join a small sample of lap and stint records.
-   [ ] Check row counts before and after the join.
-   [ ] Calculate average lap time by tire age.
-   [ ] Plot lap time against tire age.
-   [ ] Plot lap time against race lap for one driver across the whole
    race. Can you see the fuel effect?
-   [ ] Write three observations and at least two caveats.

## Day 5 --- Review and choose datasets

-   [ ] Repeat the data audit for one or two additional races.
-   [ ] Compare field availability and data quality.
-   [ ] Decide which races to use for the first version: Grands Prix
    with usable data in both 2024 and 2025.
-   [ ] Write down why you chose them.
-   [ ] Review what you can explain without looking at generated code.
-   [ ] List the three biggest things you learned and the next
    unresolved questions.

At the end of Day 5, you should have a small working experiment and a
clear view of the data. You should **not** have a finished simulator, a
neural network, a complex architecture, or a polished frontend.

------------------------------------------------------------------------

# 12. Final rules

1.  **Do not optimize for looking advanced. Optimize for being able to
    explain what you built.**
2.  **Do not let an AI-generated plan become unquestioned
    architecture.** Challenge it, simplify it, and understand its
    assumptions.
3.  **Do not treat a working output as proof of correctness.** Test it
    and compare it against something you can verify.
4.  **Do not hide weak model results.** Diagnose them and report them
    honestly.
5.  **Do not expand scope when the current milestone is failing.**
6.  **Do not confuse reading about a technique with being able to
    implement or evaluate it.**
7.  **Do not spend a whole day stuck on syntax that documentation or a
    targeted question can resolve.** Independence is not needless
    suffering.
8.  **Do not copy code you cannot explain and then call it your
    project.**
9.  **Do not stop applying for jobs until the project is finished.**
10. **Do not abandon the project merely because the first attempt is
    hard.** Reduce the task, identify the missing skill, and work
    through it.

Your job is not to prove you can build PitWall without help. Your job is
to become the person who can lead the build, use help intelligently,
recognize bad suggestions, and take responsibility for the result.

**Start with Day 1. Do not skip ahead to modeling or deployment.**

---

# 13. System-design learning plan: make decisions as you build

This section is part of the working specification. The coding agent must
guide you through system-design decisions at the point where they matter.
Do not try to design the whole system perfectly before coding. Use the
smallest design that satisfies the current milestone, document the choice,
and revisit it only when new evidence justifies a change.

## 13.1 What system design means for this project

System design means deciding:
- what the application must do;
- which responsibilities belong together and which should be separate;
- what data passes between components;
- how components fail and recover;
- where data is stored;
- how the application is tested and deployed;
- which trade-offs are acceptable for a small portfolio product.

It does **not** mean adding as many technologies as possible. PitWall should
start as a **modular monolith**: one Python codebase with small modules and
clear responsibilities. Do not introduce microservices, a separate backend
API, a database, queues, containers, or cloud infrastructure unless a
specific requirement makes them useful.

## 13.2 Default architecture and the reasons behind it

Use this as a starting hypothesis, not as an unquestionable blueprint:

```text
OpenF1 API
   |
   v
Data retrieval + local raw-response cache
   |
   v
Validation, cleaning, and joins
   |
   v
Processed lap-level dataset (Parquet)
   |
   +--------------------+
   |                    |
   v                    v
Feature preparation   Exploratory analysis
   |
   v
Baseline model + evaluation
   |
   v
Lap-time prediction function
   |
   v
Strategy simulator
   |
   v
Streamlit interface
```

Initial choices and why they are reasonable:

| Decision | Starting choice | Why | Reconsider if... |
|---|---|---|---|
| Application structure | One Python codebase, separated into modules | Simple to run, test, and understand | A component has a concrete independent deployment or scaling need |
| Raw data storage | Local JSON files | Preserves source responses and makes debugging/re-running easier | Data volume or collaboration makes local files impractical |
| Processed data storage | Parquet files | Efficient for tabular data and preserves types | Query patterns or concurrent writes call for a database |
| Data manipulation | Python and pandas | Appropriate for a small historical dataset | A measured performance or scale issue requires another tool |
| Model interface | Python function(s) with defined inputs/outputs | Easy to test and replace | Model serving genuinely needs a separate runtime or scaling |
| User interface | Streamlit | Fast path to a working interactive product | User feedback reveals limitations that matter |
| Testing | pytest from early milestones | Catches regressions and makes assumptions executable | Do not postpone this; expand coverage as the project grows |
| Deployment | One application on AWS, after the local workflow works | Hands-on AWS is a deliberate learning goal; one app keeps complexity low | The AWS deploy runs far past its time budget (fall back to Streamlit Community Cloud) |
| Background jobs | No queue initially | Historical data can be fetched and prepared on demand or by a script | Processing becomes slow, scheduled, or needs durable retries |

Do not create all modules at the beginning just to match the diagram.
Create a module when you have a real responsibility that belongs there.

## 13.3 The design-decision loop

At every major milestone, the coding agent should guide you through this loop:

1. **Describe the requirement.** What must the system do at this stage?
2. **Identify the inputs and outputs.** What information enters the component, and what should come out?
3. **List realistic options.** Usually two or three options are enough.
4. **Compare trade-offs.** Consider simplicity, correctness, learning value, reliability, time, and future change.
5. **Choose the simplest adequate option.** Do not optimize for hypothetical scale.
6. **Record the decision.** Include the choice, reason, alternatives rejected, and what evidence would make you reconsider it.
7. **Implement a small slice.** Avoid designing speculative features.
8. **Test the behavior.** Include at least one normal case and one relevant failure or edge case.
9. **Explain it back.** You should be able to describe the design without reading an AI-generated explanation.

The agent should not make important architectural choices silently. It should present options in understandable language, recommend a default, and ask you to make or confirm the decision. It may make trivial local implementation choices without interrupting you, but it must explain meaningful trade-offs.

## 13.4 Design questions to ask at each project phase

### Phase A: API reconnaissance
- Which endpoint and session do we need, and why?
- What does one record represent?
- Which fields are required for the current experiment?
- How will we tell whether data is missing or inconsistent?
- Should we save the response? For repeatability, the default is yes.
- What are the API's rate limits and data-usage constraints?

**Do not build a general-purpose ingestion framework yet.** First retrieve and understand a small real response.

### Phase B: Data ingestion and caching
- What should the fetch function accept: endpoint, session key, or both?
- What should it return: raw JSON, a DataFrame, or both at separate stages?
- How will HTTP errors, timeouts, empty responses, malformed JSON, and rate limits be handled?
- How will the cache key identify the request?
- How do we avoid re-downloading data unnecessarily?
- How can we test failures without depending on a live API?

Default direction: keep API communication and local caching in a small, understandable module. Do not introduce a database.

### Phase C: Data processing
- What is the unit of one row in the processed dataset?
- What keys connect laps to stints?
- Could a join accidentally duplicate lap rows?
- What happens to missing lap times, out-laps, deleted laps, or unknown compounds?
- How can we validate row counts and inspect a few records manually?
- Should a transformation mutate its input, or return a new DataFrame?

Default direction: small functions that transform data, with explicit inputs and outputs. Test joins and row-count assumptions.

### Phase D: Modeling and evaluation
- What exactly are we predicting, and at what point would the prediction be made?
- Which features would actually be known at prediction time?
- Could any feature leak information from the future?
- What simple baseline should the model beat?
- How are circuit differences and the fuel effect handled?
- Why is a held-out session or race more appropriate than randomly splitting laps from the same race?
- Which metric is useful, and what do its units mean?
- What do errors look like across compounds, tire ages, and race conditions?

Default direction: begin with a simple baseline and a transparent evaluation. Add complexity only when error analysis gives a concrete reason.

### Phase E: Strategy simulator
- What inputs define a strategy?
- What does the simulator return?
- How does it convert predicted lap times into a total race time?
- How are pit stops and pit-lane loss represented?
- Which assumptions are data-derived and which are fixed by us?
- How will invalid strategies be rejected?
- Is the two-compound rule enforced?
- What happens when a strategy asks for a stint longer than the data covers?
- Can the simulator be tested using a tiny hand-calculable example?

Default direction: the simulator should be independent of Streamlit. It should accept parameters and return structured results. Use explicit, configurable pit-loss assumptions; do not equate stationary stop duration with total pit-loss.

### Phase F: User interface
- What is the smallest user workflow that demonstrates the product?
- Which inputs must the user choose?
- What should happen when inputs are invalid or data is unavailable?
- Can the interface call existing functions instead of duplicating their logic?
- What needs to be displayed so users understand uncertainty and limitations?

Default direction: Streamlit calls the Python functions already built and tested. Keep calculations out of UI event/layout code where practical.

### Phase G: Testing and deployment
- Can another person reproduce the result from a clean checkout?
- Are data download and model training documented as separate steps?
- Are secrets or local paths accidentally committed?
- Does the application work if cached data is missing?
- What failures should produce a clear message?
- What is the simplest deployment that demonstrates the product reliably?

Default direction: make the local workflow reproducible first; deploy one application rather than splitting services.

## 13.5 Session-by-session workflow for the coding agent

The 10-week roadmap is a sequence of milestones, not a rigid schedule. Work in **sessions of approximately 1–3 hours**, with the 20-hour weekly budget as a guide. The agent should begin each session by proposing a realistic goal based on the actual state of the repository, not blindly following a calendar.

Keep it relaxed. The agent is a guide, not an examiner: it proposes
the session, you can adjust it or just say "let's go", and it doesn't
quiz you on every line. At the start of a session it gives:

```text
SESSION [number]: [short title]

Goal: one sentence
Done when: 1-3 observable checks
Your first attempt: the smallest piece to try before asking for help
Decision to make (if any): options, a recommended default, your call
```

During the session it follows the help ladder: hints first, then
pseudocode, then a small example, then implementation if you're still
stuck. Before moving on, it asks you to explain the main piece in a
sentence or two.

At the end, you write a 3-line note in `NOTES.md` (the agent can draft it
for you to correct):

```text
[date] Session [number]
Done:
Next:
Still unclear:
```

That note is what lets the next session pick up where this one stopped.
Together with `DECISIONS.md`, it is the only logging this project needs.

If a task proves harder than expected, split it. If the time estimate is
exceeded, note it and adjust the plan; do not generate a large block of
code to catch up.

### Suggested session sequence and time budgets

These are starting estimates, not promises. The agent should adapt them to your understanding and progress. Total effort remains approximately 160–200 hours.

| Session group | Estimated effort | Intended outcome |
|---|---:|---|
| 1. Repository, requirements, Python refresher | 3–5 hours | Clean repo, specification, basic function and test |
| 2. OpenF1 documentation and one session | 3–5 hours | Retrieve and inspect real session, lap, and stint data |
| 3. Data feasibility and race selection | 3–5 hours | Data audit and documented race selection |
| 4. Fetch function and HTTP behavior | 4–6 hours | One understandable endpoint request with clear errors |
| 5. Local raw-data cache | 3–5 hours | Repeatable requests without unnecessary downloads |
| 6. Multi-endpoint retrieval | 4–6 hours | Retrieve selected laps and stints, with checks |
| 7. Data cleaning and join design | 5–7 hours | Define row grain and keys; validate joins |
| 8. Lap-level dataset and quality checks | 5–7 hours | Reproducible processed dataset |
| 9. Exploratory analysis | 3–5 hours | Plots, observations, caveats |
| 10. Prediction target and baseline design | 4–6 hours | Target, features, split strategy, metric selected |
| 11. Baseline model | 5–7 hours | Train/evaluate simple model against baseline |
| 12. Error analysis | 4–6 hours | Understand model strengths, failures, and limits |
| 13. One justified model improvement | 4–6 hours | Compare a meaningful alternative without overfitting |
| 14. Simulator contract and hand-calculable example | 3–5 hours | Inputs/outputs and explicit assumptions defined |
| 15. Simulator implementation | 5–7 hours | Calculate strategy outcomes and test edge cases |
| 16. Strategy comparison and sensitivity | 4–6 hours | Compare scenarios and show uncertainty/assumption impact |
| 17. Streamlit user workflow | 5–7 hours | Working UI using tested functions |
| 18. End-to-end integration | 4–6 hours | User input produces a traceable result |
| 19. Reliability and test coverage | 5–7 hours | Failure handling, regression tests, reproducible setup |
| 20. Deployment | 4–6 hours | Public demo if feasible, otherwise reliable local demo |
| 21. README and technical documentation | 3–5 hours | Setup, architecture, evaluation, assumptions, limitations |
| 22. Review, refactor, and interview practice | 5–8 hours | Explain design decisions, fix key issues, prepare project story |

Some sessions will be shorter or longer; some can be combined after the relevant skills are established. Do not move forward just because the estimated time has passed. Use acceptance criteria and teach-back to decide whether to continue.

## 13.6 How the agent should teach architecture without taking over

When a design decision is needed, the agent should not simply announce the answer. It should:
- explain the requirement in plain language;
- offer two or three realistic options;
- state the main trade-offs;
- recommend the simplest suitable option;
- ask me to choose or confirm;
- record the choice in `docs/DECISIONS.md` or a simple `DECISIONS.md`;
- revisit it only when new evidence appears.

Example: before adding a database, ask whether local files actually fail to meet a requirement. If not, use files for the MVP and document the trade-off. Do not add PostgreSQL because it is common in production systems or because it appears on my résumé.

Example: before separating the model into an API, ask whether it needs independent scaling, a different runtime, or a separate release cycle. If not, call the model as a Python function.

Example: before choosing a more complex model, first define the baseline, evaluation split, metric, and a specific weakness the alternative might improve.

## 13.7 Decision log

Create `DECISIONS.md` when the first meaningful design choice is made. Keep entries short:

```text
Decision:
Date/session:
Requirement:
Options considered:
Choice:
Reason:
Trade-offs:
What evidence would make us reconsider:
```

Record only meaningful choices. Do not create paperwork for every variable name or trivial implementation detail.

---

# 14. Coding-agent operating instructions

Give the coding agent this document as the project roadmap and ask it to follow the rules below. These instructions are binding unless I explicitly change them.

## Role

Act as my senior software engineer, system-design tutor, and coding mentor. Keep the tone relaxed: guide, don't examine. Help me build PitWall while learning to plan, implement, test, debug, and explain a software project. I am a recent CS graduate but a beginner at designing and implementing larger software systems. Do not assume I know project architecture, pandas workflows, testing practices, or deployment.

## Source of truth and scope

- Use this Markdown file as the roadmap and current source of truth.
- Start from the actual repository state. Inspect existing files before proposing changes.
- Do not assume a task is complete just because the plan says it should be complete.
- Follow the MVP and scope boundaries. Explain any proposed scope change and ask before major changes.
- Do not build the entire project, multiple major modules, or the full pipeline in one request.
- Do not silently overwrite, delete, or restructure large parts of the repository.
- Do not claim that code, tests, deployment, or evaluation succeeded unless you actually verified it.

## Before every session

Start with a brief session plan using the session template in Section 13.5. Choose the next task based on current progress and my demonstrated understanding. Give a realistic time estimate that includes research, implementation, testing, and review. The estimate is a guide, not a reason to rush.

Ask me to make important system-design decisions when they arise. Explain options and trade-offs in beginner-friendly language. Do not ask me to make every tiny implementation choice.

## Teaching and coding behavior

1. Give me a chance to attempt the task before presenting a full solution.
2. Start with conceptual explanations, hints, or pseudocode. Increase assistance gradually when I am stuck.
3. Prefer one small function or behavior at a time.
4. Before code, explain its purpose, inputs, outputs, and acceptance criteria.
5. Use readable, ordinary Python. Avoid clever abstractions and unnecessary dependencies.
6. Explain unfamiliar syntax and meaningful design choices.
7. When debugging, inspect the actual error and smallest failing example; do not immediately replace my implementation.
8. Do not generate entire files or multiple modules unless I explicitly ask or we have agreed that a specific file is the current bounded task.
9. If you write code, help me trace it with a small example and ask me to explain the behavior.
10. Do not confuse memorizing syntax with understanding. I may use documentation, but I should understand control flow, data shapes, assumptions, and failure cases.
11. Never pretend I understand a concept just because the program runs.
12. If I am stuck for too long, increase assistance rather than leaving me stuck indefinitely.

## System-design behavior

- Teach design just in time, when a real choice affects the current milestone.
- Start with requirements and data flow, then responsibilities, interfaces, failure behavior, and deployment.
- Prefer a modular monolith, local files, simple functions, and one Streamlit application until evidence suggests otherwise.
- Explain trade-offs before recommending additional services or infrastructure.
- Ask me to confirm important architectural decisions and record them in `DECISIONS.md`.
- Keep data ingestion, processing, feature engineering, modeling, simulation, and UI responsibilities distinct where useful.
- Define inputs and outputs between components.
- Avoid speculative scale optimization.
- For any proposed dependency, explain what problem it solves and why a simpler alternative is insufficient.
- When architecture needs to change, explain the evidence motivating the change.

## Research and technical accuracy

- Use official documentation first for APIs and libraries.
- Verify unfamiliar API fields, package behavior, and deployment instructions instead of guessing.
- Treat OpenF1 responses as real data to inspect, not as a schema to assume.
- Respect API limits and cache responses.
- Do not make unsupported claims about optimal race strategies, tire degradation causality, model quality, or affiliation with F1/FIA/FOM.
- Never fabricate performance numbers or test results.

## Required closeout after every session

Help me write the 3-line note in `NOTES.md` (Done, Next, Still unclear),
add a `DECISIONS.md` entry if we made a real decision, and say which
commands or tests were actually run and their results. Nothing more.

## First instruction to the coding agent

Do not start by generating the application or building the complete ingestion pipeline.

1. Inspect this plan and the repository state.
2. Summarize the first milestone in plain English.
3. Propose Session 1 using Section 13.5.
4. Ask me to make only the first small decision or attempt.
5. Begin with requirements, a tiny Python exercise, and OpenF1 reconnaissance.
6. Stop at the agreed session boundary, review the work, and wait for me to continue.

The goal is not merely to finish PitWall. The goal is to finish a credible project that I can explain, test, debug, and continue developing without depending on an AI agent to make every decision.

---

# 15. Phase 2, only after the Definition of Done: a strategy agent

PitWall v1 has no agents or LLMs, on purpose. Once every box in Section
10 is checked, an agent layer is a sensible way to add an
AI-engineering piece on top of a core you understand:

-   An agent that answers questions like "what if this driver had pitted
    five laps earlier at this race?" by calling your simulator and data
    functions as tools, and explains the answer using only their
    outputs.
-   An evaluation set of 20--30 questions whose answers you compute
    directly from the simulator. Measure whether the agent called the
    right tool with the right arguments and reported the numbers
    correctly.
-   The same rules as v1: small slices, your decisions, tests.

Do not start Phase 2 early because modeling got hard. That is exactly
the pattern Section 0 describes.
