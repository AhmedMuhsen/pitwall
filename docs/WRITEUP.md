# PitWall: one decision, one failed approach, one lesson

PitWall is a small F1 strategy simulator built on public lap-timing data. It predicts how much slower a lap gets as tyres age and fuel
burns off, strings those predictions into a race, and estimates what a driver's race time would have been under a different pit
strategy. It is a learning project and says so: it does not find the best strategy.

The hard part was never the lap-time model. It was knowing whether the *answers* could be trusted.

## The hard decision: how do you test a comparison nobody can observe?

The app's whole point is a gap: "this other strategy would have been X seconds faster". But no real race has the same car running two
strategies, so there is no ground truth for a gap. Checking the predicted race *total* against the real one is not enough: a total
can be right while the gap between two strategies is wrong, because errors shared by every strategy cancel in a gap.

The closest honest test I found was **pairs of different cars in the same race**: predict the gap between their times and compare it
with the real one. The first version took each car's pace from its whole-race median lap. That turned out to be close to a coin flip
(52% right on the 15-race data set I had then), and the reason is worth stating: a car's whole-race median lap already contains the
effect of its strategy, since fresher tyres make a faster median. The test was partly checking the answer against itself. Correcting
the pace with the model over the whole race would be circular in the same way.

I took each car's pace from its **first half only** and scored only the **second half**, which had the lowest error (10.8 s against 11.8 s
for the raw first-half median) and keeps the scored laps out of the pace estimate. The price is that this cannot test first-stint
choices, and strategy spans the whole race. So I added a second check over the whole race: predict each stint from the *same car's other
stints*. On 1,318 stints in 2023/24 the stint-total error is 7.7 s on average (median 5.3 s), against an average of 25.6 s if the model ignores tyres and fuel.

That 5.3 s became the line the app uses: a predicted gap smaller than the model's own typical stint error is reported as "too close to
call", and a larger one must also stay faster when the model is refitted on 20 different random 80% subsets of the training races. The
pair check agrees with it: below a 5 s predicted gap the faster car is picked 43-63% of the time (a coin flip); above 10 s, 85-99%.
Teammate pairs would have been cleaner, but I found only 20 of them in 7 races, with pace differences that swamped the signal, so I
rejected them.

## A failed approach: thirteen model variants and a boosted-trees benchmark

The stint check exposed two specific problems: first stints were predicted 0.17 s per lap too fast, and laps on tyres 30 or more laps
old were predicted 0.18 s per lap too slow. A residual problem like that is a licence to add structure, so I tried: squared and cubed
fuel terms, a flattening wear term, tyre age squared, a new-tyre warm-up term, track temperature, and combinations, all scored on
2023/24 only, never on 2025. As a ceiling I also fitted gradient boosting.

None of it worked. Lap error moved between 0.549 and 0.566 s against 0.558 for the current model. The best linear variant gained
0.004 s and moved the first-stint bias from -0.172 to -0.148. Track temperature added nothing, and its fitted effect changed sign
between the two held-out years, which is what noise looks like. Boosted trees reached 0.549 s but made the last-stint bias worse
(-0.084) and cannot extrapolate beyond the tyre ages they have seen, which is exactly what a strategy simulator has to do. Because the
same circuit's bias flips sign from one year to the next, what is left looks specific to each race, not a shape the inputs can learn.

So the model stayed as it was, and the two biases are documented limitations. I tried the same thing on the prediction intervals: a
race-total interval calibrated on recent races reached 81% coverage with a 6-race window, but only by widening to about ±20 s on
roughly 40 errors, so I did not adopt it. Race-total intervals cover 71-73% instead of the intended 80%, and the app says that.

## The lesson

A good-looking number is a question, not an answer: *what was it measured against, and did the measurement share anything with the thing
it claims to check?* The whole-race pair test looked like validation until I saw that each car's pace already contained the strategy
being tested, and it scored 52%. The same question caught a mistake of mine near the end. My README printed a prediction interval's
half-width beside a coverage figure that had been measured with a different half-width (±26.7 s beside 89%, when the 89% was measured at
±33.6 s). Every number was real; the pairing was not. I only found it because I was tracing each figure to the command that produced it.
So now every number in the model card has a source next to it, and I trust a result more when the check that produced it could have come
out the other way.

## What I would do differently

I would use the whole corpus from the start. I began with 15 hand-picked races and wrote conclusions on them (for example, that the
old-tyre bias was a 2025 effect), then had to correct that when I widened to 57 races and found the bias in the earlier years too. I would
also generate every README number from a script on the day I write it. The evaluation script behind my numbers had crashed once the
corpus grew, and two of the README's figures had no script printing them at all; I only noticed when I re-ran everything for the model card. And I would
decide how to validate strategy gaps before building the first backtest, not after the first one turned out to be circular.

## Where the numbers come from

The figures for the final model are in [`MODEL_CARD.md`](MODEL_CARD.md), each with the command that prints it; the evaluation is one
command (`uv run python scripts/evaluate.py`, about 85 seconds) and the test suite is `uv run pytest -q`. The 52% first pair test, the
10.8 s against 11.8 s comparison, the teammate-pair attempt and the 6-race calibration window were measured during development, on the
smaller 15-race data set for the first two, and are not reproduced by a committed script.
