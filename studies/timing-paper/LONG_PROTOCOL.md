# Six-minute communication schedule extension

This follow-up asks how often pairs that have yet to finish at three minutes catch up by six minutes, and whether the ranking of communication policies changes. It uses new model samples and an expanded benchmark. It estimates late completion under the six-minute instructions and cannot recover how any individual previous episode would have ended.

## Fixed design

Six recipe sets, each with four assigned objectives per bot, give 18 episodes across all three schedules. Bakery, harvest and dyes are expanded versions of the prior recipes. Woodwork, masonry and metalwork add new goals. The same scenario and layout are used for all three schedules in a block. Each bot starts with the partner’s objective card, and each set retains the gold handoff. Item and information sharing rules follow the earlier study. GPT-6 Luna, local example retrieval, generated-code execution disabled, fixed Minecraft world and scoring, fresh server per episode. The fixed manifest balances schedule order across positions. Three workers process different blocks, with each block kept intact on one worker.

| Schedule | First 180 seconds | Second 180 seconds |
| --- | --- | --- |
| Always open | Continuously open | Continuously open |
| Two 60-second blocks | Chat at 0–60 s | Chat at 180–240 s |
| Alternating | Chat at 0–20, 60–80, 120–140 s | Chat at 180–200, 240–260, 300–320 s |

The limited-chat schedules each offer 60 scheduled chat seconds per half and 120 per six-minute episode. All three have the same first scheduled opportunity. The first half uses the previous schedules, on harder tasks and under a disclosed longer deadline. All physical actions remain available while chat is closed.

## Outcome and stopping rules

The clock starts after initial inventory, placement, and joins. It stops when the console verifies concurrent ownership of all eight targets, or at 360 seconds. At 180 seconds, episodes still active take a console inventory snapshot, with request and response timestamps. Episodes that have already finished use their recorded success. Report success by 180 s and 360 s, late completions out of episodes unfinished at 180 s, remaining tasks at the checkpoint, and complete cases' actual elapsed times. Treat unfinished times as right-censored, and use capped times (180 or 360 seconds for unfinished episodes at the respective horizon) for paired means.

The primary contrast is alternating minus two blocks in mean capped completion time at 360 seconds. Use the six matched blocks and report each paired difference, the mean, a descriptive block bootstrap interval, and the exact two-sided sign-flip reference. The always-open comparison and the change between horizons are secondary. Report protocol errors, model errors and restarts. Do not stop early based on outcomes. Retry only infrastructure failures that prevent evaluating the assigned episode. Keep endpoint failures, delays, transient model errors and unproductive agent behavior in the assigned condition. The abbreviated checkpoint and chat-gate preflight is excluded.

Six matched recipe sets provide broader coverage than three sets, but this does not establish statistical power for small effects. The harder recipes and the longer deadline were changed together compared with the prior study, so cross-study differences are descriptive. A causal comparison of recipe count or announced deadline requires its own randomized factor.
