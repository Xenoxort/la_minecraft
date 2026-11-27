# Passing down recipes cut discovery time

Giving Luna exact recipes from Astra’s logs cut mean four-order completion time from **271 to 58 seconds**. Luna finished all four orders in every reused-recipe trial, including every run from scratch. On genuinely new recipes, the procedural playbook gave the same number of deliveries as from-scratch Luna and the timing difference varied across the ten matched puzzles.

## What ran

GPT-6.2 Astra first discovered recipes in ten Minecraft kitchens and delivered all 40 orders. Each verified delivery yielded a recipe card. In forty fresh student trials, GPT-6 Luna tackled four custom recipes per kitchen. The two student comparisons each matched ten puzzles against an independent-discovery control with the same clues, feedback, model, and budget. The reused recipe students saw the same ingredient combinations with reordered shelves. The novel recipe students saw forty different hidden combinations. The bot started stocked at its bench, and every attempted recipe used the real Minecraft crafting grid. The server read the final delivery chest independently.

The experiment included 50 scored trials, 50 Minecraft joins, and 679 model decisions. The runner and synthesis took 22 minutes and 6 seconds in Docker on November 27, 2026. The replay verified every prompt, crafting attempt, teacher card, and terminal result. Every scored decision received a completed response, and no trial required a retry. The server logs show tick-lag warnings during startup and early chunk loading. All scored runs still executed their scheduled decision slots through completion or cutoff. The fixed 18-second cadence means that saving recipe tests accounts for most of the elapsed-time difference.

## Matched student comparisons

All times are means. Full-menu time uses the six-minute cutoff for an unfinished run. Every run delivered at least one order, so first-craft times are observed in all cells.

| Recipe family | What Luna received | Orders by six minutes | Finished all four | First craft | Full menu or cutoff | Tests per run |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Reused | Clues and own feedback | 4.0/4 | 10/10 | 56.8 s | 270.6 s | 15.7 |
| Reused | Same clues and feedback, plus recipe cards | 4.0/4 | 10/10 | 4.1 s | 57.9 s | 4.0 |
| New | Clues and own feedback | 3.9/4 | 9/10 | 86.3 s | 286.8 s | 16.5 |
| New | Same clues and feedback, plus playbook | 3.9/4 | 9/10 | 93.0 s | 290.7 s | 16.7 |

**Reused recipes.** Cards saved an average of 212.7 seconds per matched menu, with a descriptive 95% matched bootstrap interval of 176.9 to 244.9 seconds saved. They also saved 52.8 seconds to the first craft and 11.7 tests on average. Luna used exactly four tests with cards in all ten runs. Working from scratch took nine to twenty tests. On layout 7287, the card run finished in 58.5 seconds and the independent run took 293.3 seconds.

**New recipes.** The mean playbook effect was 0.0 orders, with a descriptive 95% matched bootstrap interval of −0.3 to +0.3 orders. The mean time difference was 3.9 seconds longer with the playbook, with an interval ranging from 37.9 seconds faster to 41.8 seconds slower. Playbook students finished sooner in four of the ten matched layouts and used two more tests in total. One playbook run and one independent run ended with three orders, on different layouts.

## What transferred

The cards conveyed verified solutions. The students had to look up each ingredient’s rank on the reordered shelves and submit the combination. They hit the four-test minimum every time. Total Luna input and output tokens on reused recipes fell from 155,918 to 20,905 across ten runs, an 87% reduction.

Astra selected three procedures from a predefined list after seeing the logs. The playbook told Luna to restrict candidates using the rank sum, keep a ledger of all feedback and eliminate inconsistent possibilities, and test a sole surviving candidate immediately. The supporting observations were layout 7280 order `o1` turn 1, layout 7284 order `o4` turn 3, and layout 7287 order `o4` turn 16. The held-out prompts contained those general procedures and the current kitchen’s public clues. The verifier confirmed that the forty held-out recipes were disjoint from the forty verified training recipes and reconstructed every student prompt from its allowed inputs.

The guide gave a way to reason about the feedback, but the model still had to apply it correctly. For layout **7283**, replay of the playbook run found exactly one candidate for its outstanding order after turn 19. Luna’s next action described two candidates and tried a different triple. It reached the cutoff at three of four orders. The independent student finished all four orders in 293.2 seconds on that layout. On **7287**, the reverse happened. The playbook student finished in 276.2 seconds, and the independent student stopped at three of four.

## Limits and cost

The result supports direct reuse of verified recipes with the same student. The three-tip playbook showed no clear transfer advantage on the held-out puzzles. That comparison uses one guide chosen from a fixed list, one student model, one recipe rule family, and ten matched layouts. The independent and card conditions both reached the delivery ceiling. The teacher cooked under a different shelf ordering, so the controlled effects in this study are the paired Luna comparisons.

The teacher runs and synthesis consumed 83,348 tokens. At published standard input and output rates, the recorded usage corresponds to about $1.04 for those steps before cache-write adjustments. The ten reused-recipe student runs cost an estimated $0.049 from scratch and $0.004 with cards. The training expense and the student savings operate on different timescales. These are list-rate estimates based on reported tokens. [Official OpenAI model catalog and rates](https://developers.openai.com/api/docs/models)

[Figure](recipe-transfer.pdf) · [Protocol](PROTOCOL.md) · [Reproduction](REPRODUCE.md) · [Machine-readable results](results.json) · [Raw evidence](evidence.tar.gz)

The archive has `teacher/` and `students/` folders. Each run contains the actual prompt, selected action, and test feedback in `trace.json`, bot stdout in `agents.log`, and the Minecraft chest read in `server-sample.txt`. Each cohort also has three full Minecraft server logs. The archive’s `knowledge.json` contains the cards, selected playbook, source turns, and abstract training ledger used to choose the procedures.
