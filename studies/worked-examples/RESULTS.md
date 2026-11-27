# Worked examples on harder Hell’s Kitchen recipes

Luna delivered **34 of 48 orders from scratch**, **33 of 48 with Luna examples**, and **24 of 48 with Astra examples**. Astra was the more successful donor in the same donor kitchens. Students who saw its examples delivered the fewest orders.

## What ran

Each kitchen had four custom Minecraft recipes. A cook chose one ingredient from each of four shelves. It knew the sum of the correct ranks and observed how many shelf choices matched after a test. A correct attempt produced food in the real crafting grid, and the server verified the delivered food in the chest.

Calibration used twelve independent Luna runs, with four kitchens at each shelf width. The means were 4.00 orders at width four, 2.75 at width five, and 2.25 at width six. Widths five and six were equally close to the target of 2.5, so the prespecified rule selected six. Its clues left 125 to 146 combinations per order before testing.

Astra and Luna each attempted the same eight donor kitchens. Both received thirty 18-second decision slots. The study then ran each of twelve unseen student kitchens under all three conditions. Every student used GPT-6 Luna, the same clues and feedback, and twenty slots at the same cadence and token ceiling. Matched conditions varied only in whether the prompt included examples and which pack it included.

Each example showed the first three tests for a shared donor recipe, beginning with two unsuccessful tests. There were four such examples per pack, selected from donor kitchens 8040 through 8043. Both packs were exactly 1,209 characters, and their opening student prompts used 909 input tokens on all twelve matches. The from-scratch prompt used 407. Recipes in the held-out kitchens were distinct from the donor recipes.

## Student outcomes

Times below are means. Unobserved events use the six-minute cutoff.

| Luna student condition | Verified orders by 6 min | Mean orders out of 4 | Finished all 4 | Time to first craft or cutoff | Tests per delivered order |
| --- | ---: | ---: | ---: | ---: | ---: |
| From scratch | 34/48 | 2.83 | 1/12 | 111.0 s | 7.00 |
| Four Luna examples | 33/48 | 2.75 | 1/12 | 105.2 s | 7.24 |
| Four Astra examples | 24/48 | 2.00 | 1/12 | 193.0 s | 9.96 |

The paired estimate for Luna examples was **−0.08 orders** relative to working from scratch, with a descriptive 95% bootstrap interval of −0.50 to +0.33. Astra examples scored **−0.83 orders** relative to working from scratch, with an interval of −1.67 to −0.08. The difference between the two equal-length packs was **−0.75 orders** for Astra relative to Luna, with an interval of −1.50 to 0.00. Student runs averaged 19.8 to 19.9 valid tests in all three arms. Eleven of twelve students in each arm reached the cutoff, so differences in time to complete all four orders gave little information.

Luna with Astra examples finished fewer orders than from-scratch Luna in five matched kitchens, tied in six, and finished more in one. The two zero-delivery kitchens account for six of the ten orders in that gap. Both zero-delivery students completed all twenty model calls and performed all twenty physical tests. In each case, the trace already contained enough evidence to solve an order, but the student spent its remaining moves on other orders. In kitchen 8058, order `o2` had one candidate left after turn 18. In 8059, order `o3` had one candidate left after turn 16. Removing those two matched kitchens as an exploratory sensitivity check reduces the gap to 0.4 orders, with a descriptive interval of −1.0 to +0.1 for the difference.

## Donor performance and cost

Astra delivered **32/32 orders** and finished all eight donor kitchens. Luna delivered **28/32** and finished five. Astra used 153 tests and Luna used 204. Each student pack drew from orders both donors had successfully discovered. All four third tests in each pack were informative. The average candidates remaining after the third test were 6.5 in the Luna pack and 7.25 in the Astra pack. These are properties of the selected excerpts.

| Method evaluated on twelve student kitchens | Donor tokens | Student tokens | Combined tokens | Estimated standard token cost |
| --- | ---: | ---: | ---: | ---: |
| From scratch | 0 | 285,619 | 285,619 | $0.089 |
| Luna examples | 262,497 | 402,422 | 664,919 | $0.180 |
| Astra examples | 96,006 | 400,149 | 496,155 | $1.182 |

Costs include all eight donor runs for each pack and use reported input and output tokens at published standard list rates. The estimates exclude common calibration overhead and any unreported usage from failed requests. The one-time donor costs were about $0.081 for Luna and $1.084 for Astra. [Official OpenAI model catalog and rates](https://developers.openai.com/api/docs/models)

## Interpretation and verification

The experiment estimates transfer from two specific packs of four three-test examples. The donor result shows that Astra could solve this kitchen task with fewer attempts and a higher completion rate. Luna students who saw those early excerpts delivered fewer orders than their matched from-scratch controls. Both example conditions added prompt context, and the direct comparison between teachers controlled the amount. The study uses twelve matched kitchens, a single pack per teacher, and one clue system. The two severe misses in the Astra group make the magnitude of the apparent disadvantage uncertain.

Every one of the 64 live trials had a verified terminal state, including the twelve calibration trials. The separate physical checks also verified incorrect, near-miss, and correct recipes at every shelf width. Student and donor production took 24 minutes and 8 seconds in Docker on November 27, 2026. There were two student request timeouts, one in the from-scratch group and one in the Luna example group. Four Luna donor requests were interrupted. No trial was replaced. During student runs the median model request took 5.2 to 5.5 seconds across groups and median remaining time to a physical action’s completion was about 0.22 seconds. Minecraft logged tick lag during startup. The six-minute test budget and 18-second cadence governed the number of attempts, and the two zero-delivery runs used their entire allotted budget.

[Figure](worked-examples.pdf) · [Protocol](PROTOCOL.md) · [Reproduction](REPRODUCE.md) · [Machine-readable results](results.json) · [Raw evidence](evidence.tar.gz)

The archive contains the calibration, donor, and student logs. The donor material and its exact rendered prompt text are in `material.json`. Each run contains the prompt, API status, action and test feedback in `trace.json`, the bot’s `agents.log`, and the server’s terminal delivery-chest read in `server-sample.txt`.
