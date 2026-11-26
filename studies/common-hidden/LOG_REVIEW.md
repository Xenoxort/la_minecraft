# Why the chat ranking changed

I reviewed the 18 original six-minute trial logs and the 90 shared-goal and hidden-recipe traces. The two studies exposed different bottlenecks. The original controller could discard an action in response to a new message. The newer controller relayed information before a fixed action round. In its split-card conditions, the number of recipes that either bot could unlock tracked the final score closely.

## The original advantage came from two recipe sets

| Original six-minute comparison | Always open | Alternating |
| --- | ---: | ---: |
| Verified goals across all six pairs | 38 | 44 |
| Seconds spent per goal | 43.4 | 29.2 |
| Seconds spent per goal with Dyes omitted | 36.9 | 33.3 |
| Seconds spent per goal with Dyes and Masonry omitted | 33.2 | 37.6 |

Dyes contributed five of the six extra verified goals under alternating chat. Masonry contributed the other goal. The remaining four sets tied on terminal goal count, and the timing metric favored always-open chat for that subset. Removing sets after seeing results is a sensitivity check. The original result still includes all six.

- **Dyes had a late disclosure of the assigned items.** In the alternating run, Jill listed Andy’s four assigned dyes at 7.5 seconds. Andy had all four by 57.5 seconds, and the joint finish was at 85 seconds. In the always-open run, Jill initially named ingredients. She gave the full target list at 136.0 seconds. Andy kept gathering and discussing other supplies and never held an assigned dye in the recorded inventory snapshots. The server scored 3/8. [Alternating disclosure](../timing-paper/data/long/b04-dyes-alternating/events.jsonl#L30) · [Always-open disclosure](../timing-paper/data/long/b04-dyes-always/events.jsonl#L400)
- **Masonry stalled on a false completion claim.** Andy knew the four targets and had three by about 70 seconds. At 251.1 seconds in the always-open run, he said he already held them all. The snapshots and terminal result still lacked his smooth stone slab. The alternating run held the slab by 147.6 seconds and finished shortly after. [Completion claim](../timing-paper/data/long/b05-masonry-always/events.jsonl#L691) · [Terminal evidence](../timing-paper/data/long/b05-masonry-always/minecraft.log)
- **Bakery went the other way.** Always open finished in 135.1 seconds, compared with 301.6 seconds for alternating. In the alternating run, Andy had his four items by 56.7 seconds and Jill had her golden apple by 90.7 seconds. Jill’s other three assigned items appeared in her inventory only after 293 seconds. This was a different failure pattern from Dyes. [Timing and inventories](../timing-paper/LONG_RESULTS.md)

The raw agent logs show **61 discarded responses out of 658 recorded model responses** in always-open trials and **34 out of 657** in alternating trials. The two-window trials had 29 out of 754. The trace message is `received new message while generating, discarding old response`. The controller compared prompt timestamps and discarded answers when a newer prompt had started. For example, Dyes discarded Andy’s generated `!viewChest` at about 14 seconds and Jill’s `!searchForBlock("chest", 128)` around 17 seconds in its always-open run. These are observed interruptions. Their effect on finish time cannot be recovered from the logs. The earlier chat audit marked zero six-minute turns as clearly off topic. [Original controller](../../src/models/prompter.js#L217) · [Chat coding results](../timing-paper/CHAT_ANALYSIS.md)

## The newer split-card gap arose before crafting

These are counts of recipe-by-trial targets pooled over ten matches. A recipe reaches the first stage if either bot has both cupboard codes in its prompt. The code grant and the subsequent chest and craft actions are recorded separately.

| Split cards | Recipes where either bot saw both codes | Recipes for which a bot collected the kit | Recipes crafted and verified |
| --- | ---: | ---: | ---: |
| Always open | 64/80 | 58/80 | 54/80 |
| Alternating | 45/80 | 41/80 | 37/80 |
| Two 60-second windows | 32/80 | 30/80 | 29/80 |

Always open exposed both codes for 19 more targets than alternating and verified 17 more crafts. Teams finished 84% and 82% of targets once either bot saw both codes, respectively. Those conditional percentages are descriptive. Recipes that unlock early or that bots choose to pursue may be easier to finish. The stage counts locate the shortfall upstream of crafting.

Matched seed **2714** shows all three paths. In always-open chat, Andy assembled both packed-mud codes in round 31. Jill received the complete card in round 33, took the ingredients in round 34, and crafted in round 35. In the two-window run, Jill got the missing half at round 20, then kept trying to explore R01 and pursue a different recipe. She never collected the packed-mud kit. The alternating pair never received a packed-mud card. Terminal scores were 7/8 always open, 4/8 alternating, and 3/8 in two windows. The traces are in `2714-split-always/trace.json`, `2714-split-alternating/trace.json`, and `2714-split-blocks/trace.json` in the archive. [Recipe-level evidence](evidence.tar.gz)

### A prompt problem amplified the bottleneck

The shared system prompt listed `explore` and showed an example room, `R01`, for every task. Clue rooms existed only in the hidden-recipe task. In the split-card runs, bots selected a nonexistent room **730 times in 2,160 decision slots**. This occurred in all 30 split-card trials, with 229 attempts under always open, 234 under alternating, and 267 under two windows. The full-card runs had five such attempts across 1,116 slots.

Seed 2714 shows both causes. Its always-open pair repeatedly tried to inspect R01 at the start, despite receiving `no_such_room`. With open rounds still available, the pair began exchanging cupboard fragments and recovered to seven goals. The invalid option created wasted turns across all schedules. The logs cannot say how the rankings would change with that option removed.

The hidden recipe traces help separate information access from execution. Two windows exposed both codes for 128 of 160 targets and alternating for 127, compared with 124 under always open. Final completion was 113, 113, and 114 respectively. Once the bots could find full cards in the world, more chat made very little difference to how many recipes were finished.

## What the reversal supports

The two experiments changed the task and the communication interface together. The older result was sensitive to two individual recipes and included observable losses from interrupted responses. The newer split-card result measured an explicit information gate that rewarded more opportunities to exchange a fragment. Among the two schedules with the same nominal chat budget, alternating still unlocked more recipes than two longer windows.

The next comparison that would separate these effects would use the same recipes and action interface across all schedules. Give the bots only actions available in the current task. Keep message arrivals from interrupting the action already in progress, and match the number of transferable card fragments while varying when they can be sent.

## Reproduce the audit

The scorer reads the earlier repository outcomes and the raw MineCollab agent log archive, then reconstructs knowledge, collection, and craft stages from the newer trace archive. It makes no model calls.

```sh
raw=$(mktemp -d)
tar -xzf studies/common-hidden/evidence.tar.gz -C "$raw"
python3 -B studies/common-hidden/diagnose_reversal.py studies/timing-paper \
  /path/to/timing-long/raw-logs.tar.gz "$raw"
```
