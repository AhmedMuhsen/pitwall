"""Writes evals/agent_questions.jsonl: 40 questions for the what-if agent, in five groups, built from the committed data
so every race and car in a question exists. Deterministic (fixed seed). Run: uv run python scripts/make_agent_eval.py"""
import json
import random
from pathlib import Path

from pitwall.agent_tools import ALIASES, _cars, _distance, load_context

OUTPUT = Path("evals/agent_questions.jsonl")
ONE_STOPS = [("MEDIUM", "HARD"), ("SOFT", "HARD"), ("HARD", "MEDIUM"), ("SOFT", "MEDIUM")]
TWO_STOPS = [("MEDIUM", "HARD", "HARD"), ("SOFT", "MEDIUM", "HARD")]
GENERIC_DECLINE = ["can't", "cannot", "unable", "not available", "isn't", "doesn't"]


def race_words(rng, year, circuit):
    """A way of saying the race: the circuit name, or a country/city alias."""
    names = [circuit] + sorted({a for a, c in ALIASES.items() if c == circuit and a != circuit.lower()})
    name = rng.choice(names)
    name = name.upper() if len(name) <= 3 else name.title()
    return f"{name} {year}" if rng.random() < 0.6 else f"the {name} Grand Prix {year}"


def car_words(rng, car):
    surname = (car["name"] or str(car["number"])).split()[-1]
    return rng.choice([surname, car["acronym"] or surname, f"car {car['number']}"])


def main():
    ctx = load_context(refits=0)
    rng = random.Random(7)
    offered = sorted(ctx["offered"])
    cases = []

    def add(group, question, **expect):
        cases.append({"id": f"{group}-{sum(c['group'] == group for c in cases) + 1:02d}", "group": group,
                      "question": question, "expect": expect})

    # Named strategies: the agent must pass exactly that strategy to compare_strategy.
    for i, (year, circuit) in enumerate(rng.sample(offered, 14)):
        car = rng.choice(_cars(ctx, year, circuit))
        distance = _distance(ctx, year, circuit)
        who, race = car_words(rng, car), race_words(rng, year, circuit)
        if i % 4 == 3:
            comp = rng.choice(TWO_STOPS)
            laps = [int(distance * 0.28), int(distance * 0.62)]
            q = (f"Could {who} have gone quicker at {race} with a two-stopper: {comp[0].lower()} tyres, then {comp[1].lower()}, "
                 f"then {comp[2].lower()}, pitting on laps {laps[0]} and {laps[1]}?")
        else:
            comp, laps = rng.choice(ONE_STOPS), [int(distance * rng.uniform(0.3, 0.6))]
            q = rng.choice([
                f"What if {who} had stopped just once at {race}, on lap {laps[0]}, going from {comp[0].lower()} to {comp[1].lower()} tyres?",
                f"How would {who}'s race at {race} have gone with a {comp[0].lower()} start and a switch to {comp[1].lower()} on lap {laps[0]}?",
                f"At {race}, suppose {who} pitted on lap {laps[0]} for {comp[1].lower()} tyres after starting on {comp[0].lower()}. What does the simulator say?"])
        add("named", q, behavior="answer", tool="compare_strategy",
            args={"race": f"{circuit} {year}", "car": str(car["number"]), "compounds": list(comp), "pit_laps": laps})

    # Open questions: compare against the standard alternatives (no strategy given).
    for year, circuit in rng.sample(offered, 6):
        car = rng.choice(_cars(ctx, year, circuit))
        who, race = car_words(rng, car), race_words(rng, year, circuit)
        q = rng.choice([f"Should {who} have pitted earlier or later at {race}?", f"Was {who}'s strategy at {race} a good one?",
                        f"Could {who} have been quicker at {race} on a different strategy?",
                        f"What would the simulator suggest instead of what {who} did at {race}?"])
        add("open", q, behavior="answer", tool="compare_strategy",
            args={"race": f"{circuit} {year}", "car": str(car["number"]), "compounds": [], "pit_laps": []})

    # Lookups.
    year, circuit = rng.choice(offered)
    car = rng.choice(_cars(ctx, year, circuit))
    race = race_words(rng, year, circuit)
    add("lookup", "Which races from 2024 can I look at?", behavior="lookup", tools=["list_races"])
    add("lookup", f"Which drivers can I pick for {race}?", behavior="lookup", tools=["list_cars"], args={"race": f"{circuit} {year}"})
    add("lookup", "How many races does the simulator cover, and from which seasons?", behavior="lookup", tools=["list_races"])
    add("lookup", f"Is {car['name']} in the data for {race}?", behavior="lookup", tools=["list_cars"], args={"race": f"{circuit} {year}"})
    add("lookup", "Which seasons are covered?", behavior="lookup", tools=["list_races"])

    # Things it must decline (it has no tool, or the data doesn't exist).
    add("decline", "Who is the best driver on the grid?", behavior="decline", must_mention=GENERIC_DECLINE)
    add("decline", "Where would Norris have finished at Monza 2024 if he had pitted on lap 15?", behavior="decline",
        allow_tool_call=True, must_mention=["position", "finish"])
    add("decline", "What if there had been a safety car on lap 30 at Monza 2024? How would that change Leclerc's race?",
        behavior="decline", allow_tool_call=True, must_mention=["safety car"])
    add("decline", "Compare Verstappen and Norris at Monza 2024: who was faster?", behavior="decline", allow_tool_call=True,
        must_mention=["compar", "different", "driver"])
    add("decline", "What was the optimal strategy for Hamilton at Silverstone 2023?", behavior="decline", allow_tool_call=True,
        must_mention=["optimal", "best", "prefer"])
    add("decline", "What if Verstappen had pitted on lap 20 at the 2022 Italian Grand Prix?", behavior="decline", must_mention=["2022", "2023"])
    add("decline", "What would a one-stop have done for Albon at the 2026 Australian Grand Prix?", behavior="decline", must_mention=["2026", "regulation"])
    add("decline", "Simulate Leclerc at Monaco 2024 with a stop on lap 30.", behavior="decline", must_mention=["red flag"])
    add("decline", "How would a one-stopper have worked for Hamilton in the wet at Silverstone 2024?", behavior="decline", must_mention=["wet"])
    add("decline", "What strategy will Ferrari use at the next race?", behavior="decline", must_mention=["future", "next", "predict", "historical", "past", "data"])

    # Questions that don't say which race or car: it must ask, not guess.
    add("ask", "What if he had pitted on lap 20?", behavior="ask")
    add("ask", "Would a two-stop have been better?", behavior="ask")
    add("ask", "How would a different strategy have worked for Leclerc?", behavior="ask")
    add("ask", "What if Norris had pitted earlier at Monza?", behavior="ask")
    add("ask", "Could Hamilton have won with another strategy?", behavior="ask")

    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8")
    print(f"wrote {len(cases)} cases to {OUTPUT}")
    for case in cases[:3] + cases[14:16] + cases[-2:]:
        print(" ", case["id"], "|", case["question"])


if __name__ == "__main__":
    main()
