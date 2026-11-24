# Alternating exploration and chat

This extension tests Greg's schedule after the fixed 24-episode study. Every agent gets its partner's objective card. The assigned bot has to learn its own objectives or infer them. The world, inventory, model, and 180-second deadline match within each block. All agents can explore or act physically in every phase. The experiment makes social communication available in the stated windows.

| Policy | Chat windows from start | Scheduled chat time |
| --- | --- | ---: |
| Always open | 0–180 s | 180 s |
| Up front | 0–60 s | 60 s |
| Alternating | 0–20, 60–80, 120–140 s | 60 s |

The alternating arm implements 20 seconds of chat and then 40 seconds with chat closed, repeated three times. Opening at the same time and fixing scheduled chat seconds in the up-front comparator lets us compare distribution of opportunity. Early successes can use less than the scheduled budget. When a window closes, both agents leave any active conversation and can resume autonomous play. The live prompt indicates the window status. Delivered messages are checked against half-open intervals. Late responses are dropped at the relay.

Three blocks cover bakery, harvest, and dyes, with three objectives per bot. The phase scenario file adds a hay bale to bakery and harvest or purple dye to dyes for Andy. It adds a second sugar-cane product for Jill. Each recipe set stays fixed across its three matched episodes. The higher recipe count makes the task richer and is held constant across arms. The study does not estimate a causal effect of adding recipes.

The blocks use cyclic order so each policy appears first, second, and third once. Analyze nine episodes using the main study's server-verified capped completion definition with all six assigned objectives required. Report per-block differences, terminal success, first message, count of delivered and blocked messages, whether a later window was used, runtime errors, and process restarts. This extension is descriptive with three matched blocks. The primary comparisons for this extension are alternating versus always open, and alternating versus the equal-budget up-front arm. The main 24-episode study and this extension are analyzed separately.
