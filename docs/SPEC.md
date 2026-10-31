# PitWall: specification

One page, written at the start of the project. If this disagrees with
`docs/PitWall_Plan.md`, the plan wins; flag the conflict.

## 1. User and decision

The user is an F1 fan who wants to compare how long a driver would have taken
to finish a race under different pit strategies.

PitWall runs **after** the race, on historical data. It steps through the race
lap by lap — tyre age resets at a pit stop, race lap keeps climbing — but it
does not feed earlier laps back into its own predictions. Each simulated lap
time comes from a model fitted on historical laps, given tyre age, race lap,
compound and circuit. There is no in-race feedback loop and no live mode.

The question it answers: *what would this driver's total race time have been if
they had pitted on different laps, or used different compounds?*

## 2. Inputs

**Inputs the simulator consumes:**

- Which race (Grand Prix and year) and which driver.
- A strategy: starting compound, the lap numbers the car pits on, and the
  compound for each stint.
- Pit loss for that circuit — a parameter we estimate, not a field the API
  gives us. Pit-lane time minus the time to cover the same stretch at racing
  speed.

**Inputs used to build and filter the lap dataset, not consumed at simulation
time:**

- Laps, stints and session metadata from OpenF1 — lap times, compounds, tyre
  age, stint boundaries.
- Gap to the car ahead, to define a **clean lap**. A lap run close behind
  another car is a traffic lap, not a clean lap, and including it would
  contaminate the fitted tyre-age coefficient.
- Flags / race control, to separate green-flag racing laps from everything
  else, and to pick safety-car-free races for the backtest.

Field names and availability for the gap and flag data are **unverified** as of
writing — confirm against the live OpenF1 docs before relying on them.

Weather is **not** a model input in v1. We select dry, non-sprint races so
weather is held roughly constant; it acts as a race-selection filter. Making it
a feature would be a scope change.

## 3. Output

For a given race, driver and strategy, PitWall estimates **total race time in
seconds** under its stated assumptions, plus the per-lap deltas that make up
that total.

Comparisons are valid **between strategies for one driver in one race**. The
app also shows how sensitive that comparison is to uncertainty — mainly the
pit-loss assumption and model error.

## 4. What PitWall will not claim

- **No finishing positions, and no cross-driver comparison.** The model
  predicts lap time relative to each driver's own median clean lap, with one
  baseline per driver per race. Two drivers' predictions are measured from
  different zero points, so subtracting or ordering them is meaningless.
  Separately, position depends on overtaking and traffic, which are not
  modelled at all.
- **No causal claims about tyre degradation.** The model estimates
  tyre-age-associated lap-time loss, not physical tyre wear.
- **No optimal strategy.** PitWall compares a few hypothetical strategies. It
  does not search the space of strategies and cannot say any of them is best.
- **No affiliation** with F1, the FIA or FOM.

## 5. Known limitations

These degrade the numbers and must be stated wherever results are shown:

- **Safety cars** bunch the field and change the cost of a pit stop. Races with
  safety cars are excluded from the backtest rather than modelled.
- **Traffic** — being stuck behind another car — is filtered out of the
  training data, not simulated.
- **Track evolution** hides inside the race-lap term. Race lap is in the model
  as a fuel proxy, but it also absorbs the track getting faster as rubber goes
  down. The two effects cannot be separated here.

## 6. Out of scope for v1

Reinforcement learning; a neural network added to make the project sound more
advanced; live race recommendations; real-time telemetry ingestion; a detailed
multi-car traffic, overtaking or aerodynamics simulator; a chatbot or RAG
layer; agents and LLMs; microservices, Kubernetes, message queues or a
database; a polished commercial-grade frontend.
