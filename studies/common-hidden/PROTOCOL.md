# Shared goals and hidden recipes in Minecraft

This follow-up tests two explanations for the value of chat. Teams can use chat to avoid repeating work on shared goals. They can also use it to combine missing information. The hidden-recipe arm tests whether pairs can divide exploration and act on clues they find. The earlier six-minute pilot measured different assigned goals for each player. [Earlier pilot](../timing-paper/LONG_RESULTS.md)

## Matched conditions

Two GPT-6 Luna bots play Minecraft 1.21.1 on the MineCollab Superflat archive. Each pair starts with clear inventories at two mirrored workstations. A station has a real Minecraft chest, crafting table, and, in the hidden arm, clue rooms. The controller offers four model-selected actions. Collecting withdraws a recipe kit from that player's chest. Crafting uses the real ingredients in their inventory. Exploring walks to a specified marker. Waiting takes no game action. A team earns each recipe once if a bot crafted it on time and holds the item at the terminal check.

| Task | Initially visible | What a second bot can contribute |
| --- | --- | --- |
| Shared goals and full cards | Eight shared targets and their full ingredient cards and cupboard codes | Divide work and share progress |
| Shared goals and split cards | Eight targets, with complementary code fragments and ingredient hints | Supply the missing fragment and divide work |
| Hidden recipes | Four complete cards plus 16 searchable clue locations | Search different rooms, share discoveries, and craft any of the 12 hidden goals |

The two common-goal conditions use the same eight recipes and ingredient kits. The split-card arm uses independently drawn lock fragments so ordinary knowledge of Minecraft recipes cannot supply the missing half. The controller opens the kit to the bot once both numbers are supplied. The game engine validates the resulting craft. The hidden arm uses actual carpet markers in the world. Reaching an occupied clue marker reveals a recipe card and a cupboard code. Four markers are empty. Both stations have the same clue-to-room layout for a given seed. This measures search, discovery, and crafting in Minecraft.

Each condition has ten matches. A match holds the menu, ingredient stock, cupboard codes, clue locations, and model constant across all three chat schedules. The seed changes the codes and hidden-room mapping. API generations are stochastic. A fixed shuffle interleaves conditions. The scored matrix has 90 trials. Three shorter preflight trials validate crafting, unique-goal scoring, relay behavior, and real movement to clues.

| Schedule | Chat windows during the six-minute trial |
| --- | --- |
| Always open | 0–360 seconds |
| Two 60-second windows | 0–60 and 180–240 seconds |
| Alternating | 20 seconds open followed by 40 seconds closed, repeated six times |

Both limited policies offer 120 seconds of chat. A pair gets one simultaneous decision every ten seconds, up to 72 individual decision slots. Each slot has a ceiling of 960 input-plus-output tokens. The runner checks the model’s usage against its pre-counted input and the remaining output allowance. The team ceiling is 69,120 tokens. The trial ends early when the Minecraft server verifies that the team holds all required outputs. The model deployment, action interface, and scheduling cadence are the same throughout.

Open decision rounds relay the other bot’s last stated intent, held craft receipts, latest short task message, and up to one explicitly queued card or fragment per sender. Those updates occur only at scheduled and actual open times. Retained information stays visible during isolation. Closed turns can queue a card for the next window. Each bot sees its own game state and has no tool for inspecting the other station or its inventories. Separate ingredient stock enables duplicate work without one bot discovering that the other withdrew supplies.

Up to four Docker-hosted servers run multiple trials in separate station lanes to reduce startup cost. Each lane is reset, and each trial uses fresh bot identities and model context. No ports or host mounts are exposed. Generated code is disabled. The final score comes from the server's own inventory command and the real craft trace.

## Outcomes

The main table reports mean verified goals and pooled seconds spent per verified goal. The numerator sums actual elapsed time when all goals are verified and 360 seconds for unfinished runs. The denominator sums verified outputs. An unfinished run with zero goals still contributes time. A group with no verified goals has an undefined ratio.

For hidden recipes, report mean visible goals out of 4, mean hidden goals out of 12, and mean distinct clues found out of 12. Separating discoveries from crafts shows whether a schedule affects search or just conversion into completed items. The traces also preserve duplicate recipe kits, duplicate crafts, visits to the same clue, messages, timing, prompt rejections, and game errors.

Analyze schedule differences within each task type and report paired differences by seed. Ten trials per cell reduce noise from single episodes. The menus and interface are fixed, so treat any small schedule ranking as evidence about this benchmark. Larger groups, recipe dependency trees, and a fresh replication of the earlier individually assigned six-menu cohort are separate study designs.
