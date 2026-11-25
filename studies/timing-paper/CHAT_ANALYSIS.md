# What the MineCollab agents said and where they got stuck

Across 36 archived GPT-6 Luna episodes, always-open chat produced more concrete coordination messages and more repetition than either limited-chat schedule. The judge found **zero clearly off-task turns**. Under the 12-minute deadline, the four unfinished pairs showed confusion about who needed which item, late goal clarification, or claims of completion that conflicted with observed inventories.

## What the judge measured

Two agents each held their partner’s goal card. A team succeeded when the server verified all eight goals in the assigned inventories. Each cohort contained six matched recipe sets and one trial per schedule within each set. We scored the six- and twelve-minute cohorts separately.

GPT-6 Luna labeled each delivered natural-language turn as actionable coordination, task support, redundant, clearly off-task, or unclear. Actionable covered concrete requests, instructions, plans, and task information. A recipe or inventory claim could qualify even when factually wrong. The judge saw one ordered transcript at a time, anonymized to speakers A and B, without timing, schedule, recipe-set metadata, or outcomes. The transcripts could still contain clues about the chat schedule.

We extracted 1,344 relay events. Preprocessing removed 570 command-only or blank entries and collapsed 117 near-simultaneous matching relay echoes. Later repeated messages stayed in the transcript. The judge independently repeated its own labels on one randomly selected episode from each cohort and schedule, matching 151 of 162 labels (93.2%). This measures same-model repeatability. Human agreement remains unmeasured. [Coding script](judge_chat.py) · [Turn-level judgments and event line numbers](chat-judgments.json)

## Chat volume and informational content

Percentages use the number of delivered natural-language turns in each row. Each row has six trials. “Finished” counts server-verified success at that cohort’s deadline.

| Deadline | Chat schedule | Turns | Actionable | Redundant | Finished |
| --- | --- | ---: | ---: | ---: | ---: |
| 6 min | Always open | 193 | 164 (85.0%) | 26 (13.5%) | 3/6 |
| 6 min | First 60 s of every 3 min | 65 | 56 (86.2%) | 8 (12.3%) | 5/6 |
| 6 min | 20 s open, 40 s closed | 46 | 40 (87.0%) | 6 (13.0%) | 5/6 |
| 12 min | Always open | 208 | 153 (73.6%) | 52 (25.0%) | 4/6 |
| 12 min | First 60 s of every 3 min | 84 | 73 (86.9%) | 11 (13.1%) | 5/6 |
| 12 min | 20 s open, 40 s closed | 61 | 55 (90.2%) | 3 (4.9%) | 5/6 |

Of the 657 turns, 541 were actionable, 106 redundant and 10 task support. In the twelve-minute cohort, always-open chat had a higher redundant share than 20/40 chat in all six matched recipe sets. It did so in four of six sets under the six-minute deadline. Giving every episode equal weight yielded redundant shares of **20.0% versus 2.8%** at twelve minutes, and **13.0% versus 7.1%** at six minutes. Retaining only the first of consecutive deliveries in the same direction within 400 ms reduced the twelve-minute pooled rates to **16.9% versus 0%** and the six-minute rates to **6.9% versus 2.5%**. This check can also remove distinct messages sent in quick succession.

Always-open chat supplied more judged-actionable turns in absolute numbers in every matched recipe set. At twelve minutes, a smaller fraction of its messages added concrete coordination. Completion ends chat collection and restricted modes cap speaking opportunities. Total messages reflect both factors. Each recipe set has one trial per schedule per cohort, so these are descriptive results for Luna in this arena. They do not establish whether repetition caused failures or whether another model would be more prone to off-task conversation. The trace only includes delivered chat. [Six-minute outcomes](LONG_RESULTS.md) · [Twelve-minute outcomes](EXTENDED_RESULTS.md)

## Four unfinished twelve-minute trials

| Trial | Goals at 3 → 6 → 12 min | What the trace shows |
| --- | --- | --- |
| Harvest, 20/40 | 3 → 5 → 6 | At 11:16, Andy asked Jill to supply an apple and gold for his targets. The golden apple was Jill’s goal. Jill then issued a command to give Andy the apple. Jill still lacked sugar and a golden apple at the deadline. [Request](data/extended/b03-harvest-alternating/events.jsonl#L1812) · [Transfer command](data/extended/b03-harvest-alternating/events.jsonl#L1820) |
| Dyes, always open | 3 → 4 → 4 | At 11:53 Andy still asked what he should hold. Jill gave the correct four dye objectives at 11:55. The server found none of the four dyes in Andy’s final inventory. [Question](data/extended/b04-dyes-always/events.jsonl#L1654) · [Reply](data/extended/b04-dyes-always/events.jsonl#L1661) |
| Bakery, always open | 3 → 7 → 7 | At 5:24 Andy claimed that both agents had finished and issued an indefinite wait. Jill also claimed completion and waited at 5:32. Andy still lacked packed mud at the deadline. [Andy’s claim](data/extended/b06-bakery-always/events.jsonl#L919) · [Jill’s claim](data/extended/b06-bakery-always/events.jsonl#L939) |
| Bakery, 60 s per 3 min | 3 → 3 → 6 | Jill incorrectly said sugar required a honey bottle at 9:49. At 9:58 she claimed all four of her items were present, while adjacent inventory snapshots show neither sugar nor bone meal. Both items were still missing at the deadline. [Recipe claim](data/extended/b06-bakery-two_blocks/events.jsonl#L1633) · [Completion claim and inventory](data/extended/b06-bakery-two_blocks/events.jsonl#L1661-L1662) |

The same message can be task-relevant and operationally harmful. A follow-up can measure correctness and uptake separately from relevance by checking recipe claims against game rules, checking inventory claims against nearby snapshots, and tracing goal disclosures and handoffs to subsequent actions. For a new schedule comparison, matching total chat time across limited schedules and preselecting a blind human-coded sample would help distinguish the effect of window placement from judge disagreement.

## Reproduce the chat analysis

The archived inputs are `data/long/*/events.jsonl` and `data/extended/*/events.jsonl`, with `start.json` and `complete.json` in each episode directory. The saved [judgments](chat-judgments.json) contain every label and the original one-based event line.

Run the judge from the repository root using a private key file with the existing `OPENAI_API_KEY` field. The command makes one provider call per episode plus six repeat calls. Keep the credential outside version control.

```sh
python3 studies/timing-paper/judge_chat.py \
  studies/timing-paper /path/to/private/judgment-output \
  --key-file /path/to/private/keys.json
```

Use a fresh output directory for a new independent judge pass. In-progress runs can resume from episode files in their own output directory. To repeat the original gameplay rather than recode it, see the [six-minute protocol](LONG_REPRODUCE.md) and the [twelve-minute protocol](EXTENDED_REPRODUCE.md).

Verify the committed turn extraction and aggregates without an API call.

```sh
python3 -B studies/timing-paper/judge_chat.py \
  studies/timing-paper studies/timing-paper/chat-judgments.json --verify
```

See [demo reproduction](DEMO_REPRODUCE.md) for the Woodwork trace replay and for live recording.
