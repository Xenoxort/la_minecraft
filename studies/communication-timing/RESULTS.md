# MineCollab communication timing follow-up

The follow-up asks whether a short period of independent work changes how quickly two agents complete a shared task. It extends Greg’s two-dish pilot to four assigned objectives and makes item transfers explicitly legal. Andy must hold bread and a cookie. Jill must hold a golden apple and paper. Each bot gets the other bot’s recipe card. The two stations give each bot a reason to search and gather independently. The golden apple gives them a reason to coordinate, because Andy starts with the three gold ingots Jill is missing.

Two matched pairs compare immediate chat with a 45-second delay. Both conditions get 180 seconds, the same model, the same starting supplies, and the same arena within each pair. The second pair reverses condition order and mirrors the arena. The relay and conversation command enforce the gate. The delayed condition allows physical actions and transfers during the opening phase. Condition instructions tell agents when chat opens, so the intervention includes that expectation.

The runner uses unprivileged processes in a disposable Docker container and disables generated-code execution. It publishes only the two viewer ports, bound to localhost. The Minecraft server console assigns the initial inventories and records final ownership. First completion is estimated from contemporaneous bot inventory samples at about one-second resolution. The episode continues to the full deadline to verify that the correct bots retain the items. Setup attempts and the short preflight are excluded.

## Results

| Pair and condition | First chat | Objectives seen by 45 s | All four first observed | Held at deadline | Restarts |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 immediate | 4.4 s | 1 | 151.6 s | 4/4 | 1 |
| 1 delayed | 53.1 s | 3 | 65.7 s | 4/4 | 0 |
| 2 delayed | 46.3 s | 2 | 107.0 s | 4/4 | 0 |
| 2 immediate | 3.5 s | 2 | 173.9 s | 4/4 | 6 |

Final inventories show Andy with bread and cookies and Jill with paper and a golden apple in all four episodes. No delayed chat crossed the gate. Pair 1 recorded a blocked command at about 43 seconds. Both delayed runs gathered wheat, cocoa, and cane in the first 45 seconds. In the first delayed run, they made three items before the gate opened and completed the golden apple after Andy handed over gold.

The later chat window left space for independent gathering and crafting. It was associated with earlier joint completion in these two pairs. Both immediate-chat runs also experienced restarts. Logs show connection errors in the OpenAI embedding calls used to retrieve examples, and the last run also logged a Responses API connection error. Minecraft protocol read errors appeared in all four runs. Since restarts were uneven and there are only two trials per condition, this does not establish that delaying chat improved performance. Pair 2 reached two early objectives in both conditions.

The pilot tests how chat availability changes coordination under a shared deadline. Named Minecraft items let Luna infer familiar recipes, so the experiment does not isolate acquisition of new recipe knowledge. A paper-grade follow-up would make example retrieval resilient to connection failures or use a fixed local example selection policy in both conditions, then repeat the paired design across different recipe sets. Include tasks where agents can prepare ingredients independently and tasks where preparation needs a partner's information. Define how to classify infrastructure interruptions before running the comparison.

## Viewer

Prismarine Viewer rendered the live arena, shared crafting table, and Jill from Andy’s perspective in the final trial. It served on localhost from the sandbox and required no paid Minecraft client. A new connection sometimes showed only sky until the bot moved. The screenshot is saved alongside the logs as live-mirrored.jpg. The two viewer ports close when the temporary sandbox stops.

## Reproduction

Run the commands in the study README with GPT-6 Luna. The execution starts Mindcraft directly and uses the study runner for the arena, shared clock, and scoring. The original pilot task and dependency lockfiles are preserved. Raw per-run traces include Minecraft console logs, bot logs, the task and clock, and agent memories. The compact JSON summary is computed by analyze.py from those traces.
