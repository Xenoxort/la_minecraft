# Twelve-minute follow-up on the same tasks

The six-minute study ended with five incomplete episodes across 18 trials. This follow-up measures how often new trials still unfinished at six minutes finish by twelve minutes, and when. The same recipe sets and eight assigned objectives per trial keep the task load fixed across the two batches. New model samples and announced time limits can change how bots act in the first six minutes. The intermediate snapshots measure progress under the longer instructions.

## Fixed design

Use the same [six recipe sets](long_scenarios.json) and [assignment order](long_design.json), including corresponding layouts, supplies, agents, private goal cards, scoring and three-worker assignment. Each set appears once under each schedule. Use two GPT-6 Luna agents, local example retrieval, and the same Minecraft server archive and Docker resource limits as the six-minute study. Generated-code execution stays disabled. Start each trial with a fresh world and bot state.

| Policy | Scheduled chat through 12 minutes |
| --- | --- |
| Always open | Continuous |
| One 60-second window per three minutes | 0:00–1:00, 3:00–4:00, 6:00–7:00, 9:00–10:00 |
| Alternating | First 20 seconds of every minute |

All windows from time zero through six minutes match the earlier policy in the corresponding arm. Both restricted arms schedule 60 seconds of chat per three-minute segment, for 240 seconds in total. Physical actions remain available throughout.

## Outcomes

Stop an episode when the server verifies all eight items in the correct inventories or at 720 seconds. If the episode is still active at 180 or 360 seconds, query both server inventories and save request and receipt times. Use the first verified completion for time-to-finish. Report any completion observed only in the terminal sample at the 720-second cap separately. Times for episodes still unfinished at the cap remain unknown.

Primary outcome is the number of trials unfinished at 360 seconds that finish by 720 seconds, with their elapsed times and the denominator. A single verified finish in that interval shows a six-minute checkpoint can still miss eventual successes under these instructions. Report totals at three, six, and twelve minutes, by schedule and overall, including remaining objectives. For the schedule comparison, use the six matched recipe blocks. Report the difference in mean capped time at 720 seconds for alternating minus one window per three minutes, a descriptive paired block bootstrap interval, and the exact two-sided sign-flip reference. Use 720 seconds for unfinished or endpoint-only observations in capped calculations. The 18 episodes and eight items per episode do not form 144 independent experiments.

Exclude the abbreviated engineering probe. Audit episode startup and joins, model responses and errors, restart counts, the actual inventory samples, and adherence to the chat schedule. Keep assigned failures and transient errors in the analysis if the episode remains scoreable. Retry only failures that prevent scoring and preserve the earlier attempt records. The six-minute cohort provides descriptive context. Directly estimating the effect of the announced deadline would require concurrent randomized deadline assignments under the same task setup.
