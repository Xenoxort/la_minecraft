# Communication timing and private objectives in MineCollab

Protocol fixed before collecting the 24 study episodes. The earlier smoke tests, four-episode timing pilot, and engineering preflight are excluded.

## Question and testable prediction

Does the effect of a 45-second chat delay depend on which agent holds the objective information? We predict a larger delay penalty when each bot must learn its own objective from the partner than when each bot knows its own objective. To describe a qualitative crossover, both stratum estimates must have the predicted opposite signs. The study estimates this contrast for GPT-6 Luna and the three fixed MineCollab scenarios below. Goal-card access is the manipulation. Minecraft familiarity and spontaneous inference remain possible.

## Design

Six independent world blocks contain all four combinations of opening time (0 or 45 seconds) and goal-card access (own and partner cards available versus partner card only). Use bakery, harvest, and dyes, each with two mirrored layouts. The scenario file fixes targets, recipes, and chests. Each agent starts with the same supplies in all cells. Jill needs three more ingots, and Andy holds three. Agents can transfer physical items at any time. Public chat is disabled and the relay and start-conversation command enforce the chat gate. The agent receives the applicable timing instruction. The intervention includes this notice.

The fixed seed and manifest shuffle block and cell order before data collection. Each block runs sequentially on one worker. Two workers have private world and MindServer ports in a disposable Docker sandbox. Each episode gets a new server copy, agent memory, and starting positions. No generated code or vision. Same Luna model and local word-overlap example selection in every cell. Each model request uses the same timeout and retry policy. Record provider model IDs, completed requests, latency, usage, errors, restarts, and protocol errors. No trial-specific tuning.

## Outcomes and analysis

The primary episode outcome is elapsed seconds to the first server-console verification that the four targets are concurrently held in the assigned inventories. A candidate requires recent bot inventory samples from both agents. A successful episode ends at verification. Otherwise the clock caps at 180 seconds, and the server console records both endpoint inventories. An episode with four targets at the deadline but no earlier verification has a time of 180 seconds.

For each block calculate delayed minus immediate capped time in each information condition. The primary contrast is the partner-only delay penalty minus the own-known delay penalty. Report all six block contrasts, their arithmetic mean, a block bootstrap 95% interval (20,000 draws with fixed seed), and an exact two-sided sign-flip reference for each stratum's paired effect under a sharp no-delay-effect null. The bootstrap is a descriptive uncertainty estimate with only six blocks. Avoid generalizing from this convenience sample or treating the 24 episodes as independent blocks. Report multiplicity and the scope of exploratory comparisons. Secondary summaries are success counts, goals and supplies first observed by 45 seconds, clock time of first relayed message, and model/runtime health. The immediate condition can have early communication. The delayed condition must show no delivered chat before its gate.

## Integrity and stopping rule

Run the fixed 24 cells. Retry only failures of setup or an instrumentation failure that prevents a valid endpoint, keep and list excluded attempts, and keep the assignment unchanged. Transient model errors, reconnects, unproductive play, and reaching the time limit count as observed performance if the endpoint is observable. A disconnect at the deadline leaves an unknown inventory. Record it, score capped time unless there was a prior verified success, and display the missing inventory. A permanent API access error requires intervention and is kept as an infrastructure failure. Report protocol errors and any provider model ID drift. The study is a bounded benchmark experiment, not a replication of the PNAS human study or a test of cumulative cultural evolution.
