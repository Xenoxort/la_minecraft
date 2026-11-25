# Communication schedules in Minecraft Hell’s Kitchen

Each episode starts a fresh Minecraft 1.21.1 server from the MineCollab Superflat archive. The kitchen uses the arena from the earlier timing study and the eight-goal Harvest and Bakery recipe sets. Tasks include bread, golden apples, pumpkin pie, cookies, paper, hay, and other items. Every bot joins as a Minecraft player, collects ingredients from a real chest using Mineflayer, and crafts at a real table using Minecraft’s recipe registry. The Minecraft server independently samples every bot’s final inventory.

This experiment holds the action interface fixed across schedules. The dedicated Mineflayer controller accepts a single `take`, `craft`, or `wait` action per attempt. Chests and tables are within reach at separate private stations. Ingredient stock is assigned to the station where the corresponding goal was assigned. The experiment measures recipe discovery, ingredient collection, and crafting in the world. The action interface omits physical item handoffs and free-form tactical movement. Previously shared facts are stored by the controller as part of each bot’s private prompt history. The models cannot access arbitrary files, run generated code, use other bots’ chests, or directly read other players’ inventories.

## Fixed design

| Schedule | Chat open in these execution periods |
| --- | --- |
| A · Fully isolated | None |
| B · Always communicating | 1–10 |
| C · Frequent synchronization | 2, 4, 7, 9 |
| D · Infrequent synchronization | 2, 3, 8, 9 |
| E · Increasing communication | 1, 6, 9, 10 |
| F · Decreasing communication | 1, 2, 5, 10 |
| G · Adaptive, exploratory | Four periods chosen as described below |

C through F offer four open periods. C and D share the same first and last openings. E and F are exact time reversals. Each recipe set is tested under each schedule with 2, 4, and 8 agents in each of two information settings. All conditions have eight assigned item goals. Each agent gets four, two, or one goal as team size increases.

- **Public cards.** All recipe cards and item assignments are visible from the beginning.
- **Split cards.** Each agent starts with the next agent’s card, so a different agent holds their own. Agents may infer goals from ingredients and prior Minecraft knowledge. An open window automatically shares cards with peers.

Before each simultaneous wave in an open period, an all-to-all relay shares the same two fields from each sender, the recipe card they hold and the names of items they successfully crafted. During closed periods those fields stay unchanged. The agent still sees its private note, inventory, chest contents, previous action result, and previously relayed information. Separate chest permissions are enforced by the action interface, so shared world changes do not become a model-side channel.

The fixed matrix has 72 episodes. The matched blocks are recipe set and team size within each information setting. The adaptive arm adds 12 episodes. It opens in period 1 when cards are split. After an isolation period, it opens if the number of goals held has stopped increasing. If needed, it uses the remaining periods to reach exactly four openings. The controller’s decisions can reveal the existence of team stagnation through the phase schedule.

## Compute and scoring

Every team gets ten periods, eight attempt slots per period, and 960 input-plus-output tokens per slot. The team ceiling is 76,800 tokens. A period contains four waves for two agents, two waves for four, and one wave for eight. Each wave submits one request per bot, then waits for all in-game actions to finish. This holds team slots fixed. Individual workloads and parallelism change with team size.

GPT-6 Luna uses the same no-extra-reasoning setting throughout. The provider counts the prompt before generation, then receives the rest of the slot as its output ceiling. Reported usage is checked against that reservation. Unused tokens are not redistributed. A lost response uses a conservative full reservation if generation may have happened. No model call is required to judge the outcome.

An item counts only when its assigned bot crafted and still holds it, with the terminal inventory confirmed by the server. Progress comes from the recorded client inventories after each action wave. The analysis reports exact team success, partial goal progress, best and average individual attainment, card exposure, distinct recipe attempts, simultaneous game-action errors, gains following reopenings, repeated identical craft errors, actual token consumption, and elapsed wall time. Recipe-attempt variety reflects differences in assigned goals as well as exploration. The experiment keeps a token ceiling rather than a clock deadline.
