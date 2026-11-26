# A coordinator sped up recovery in Hell’s Kitchen

When one assembly bench closed, both flexible setups finished all ten orders on every trial. Cooks who claimed work themselves and cooks with a designated orchestrator each delivered **1.4 more orders** than fixed-handoff teams by the six-minute cutoff. The orchestrated teams finished **35.4 seconds sooner on average** than the self-organizing teams during the outage. This is a secondary timing result from ten matched layouts.

## What ran

Four GPT-6 Luna cooks handled ten distinct orders in each Minecraft trial. Each order needed two cooks to stage ingredients in the order’s chest, then an authorized cook to assemble and deposit the food. The study used the same menu, quantities, action budget, open chat, starting ownership plan, and public board in all six cells within each layout. The six cells crossed three assignment rules with two bench conditions. In the disrupted kitchen the cook assigned four of the ten orders lost their assembly bench from 48 to 336 seconds. That cook could still stage ingredients and, when designated, coordinate.

All 60 scored trials passed independent replay against real chest contents. There were 240 bot joins across three Minecraft servers, 4,132 model responses, and 2,518,097 recorded model tokens. One response was incomplete. There were no recorded HTTP or transport failures and no scored-cell retries. The 60-trial runner took 25 minutes and 55 seconds in the Docker sandbox on November 26, 2026. The scripted and model preflights are outside those totals.

## Deliveries and finishing times

Each cell contains ten matched trials. The mean orders column includes every trial. The median finish column describes trials that finished every order. The final column averages each successful finish time and counts six minutes for a trial still working at the cutoff.

| Kitchen | Assignment rule | Mean orders by 6 min | All orders delivered | Median finish | Mean through finish or cutoff |
| --- | --- | ---: | ---: | ---: | ---: |
| All benches open | Fixed handoffs | 10.0/10 | 10/10 | 135.5 s | 141.0 s |
| All benches open | Self-organizing | 10.0/10 | 10/10 | 134.7 s | 135.2 s |
| All benches open | Orchestrated | 10.0/10 | 10/10 | 134.5 s | 134.0 s |
| Assembly outage | Fixed handoffs | 8.6/10 | 1/10 | 350.0 s | 359.0 s |
| Assembly outage | Self-organizing | 10.0/10 | 10/10 | 195.9 s | 230.3 s |
| Assembly outage | Orchestrated | 10.0/10 | 10/10 | 183.2 s | 194.9 s |

In the primary outcome, the two flexible arms tied on every matched layout in both kitchens. For each flexible arm, the mean advantage over fixed handoffs during the outage was 1.4 orders, or 14 percentage points of the ten-order menu. The 95% matched-layout bootstrap interval was 1.0 to 1.8 orders. All ten outage matches between the flexible arms tied at the maximum delivery score. The protocol’s rule-dispatch follow-up required an orchestrated lead of at least half an order during the outage and a positive interaction. The observed lead was zero.

The orchestrated team finished faster than its self-organizing match in eight of ten outages. The mean paired advantage was 35.4 seconds, with a descriptive 95% bootstrap interval of 5.4 to 68.3 seconds. In the open kitchen the mean advantage was 1.2 seconds, with an interval from 4.4 seconds slower to 7.6 seconds faster. The additional timing advantage associated with an outage was 34.2 seconds, with a descriptive interval of 3.3 to 68.7 seconds. Both arms finished every trial, so these timing comparisons include all matches. The time contrast was secondary to deliveries and the intervals reflect the ten observed layouts.

## What delayed recovery

| During the assembly outage | Fixed handoffs | Self-organizing | Orchestrated |
| --- | ---: | ---: | ---: |
| Batches staged, out of 290 | 290 | 290 | 290 |
| Median time from ready and affected to assembly, capped at six minutes | 284.9 s | 119.0 s | 81.6 s |
| Ready affected orders delivered before the bench reopened | 0/33 | 29/30 | 28/29 |
| Accepted ownership changes during the trial | 0 | 29 | 32 |

A ready affected order is one originally assigned to the cook whose bench closed, with all ingredients staged before the bench reopened. Its clock starts when it is both ready and affected. Orders never assembled contribute time through the cutoff. The fixed arm had 14 such cases. The different denominators reflect which orders were ready and still open when disruption affected each team.

Every team staged every ingredient batch. The bottleneck was getting a ready order onto an open assembly bench. Peer claims and orchestrated assignments solved that in almost every case. The orchestrated teams generally moved sooner, although they also had a late miss in routing. Two large paired advantages of roughly 121 seconds each influence the mean. Across the other eight pairs, the mean orchestrated advantage was 13.9 seconds.

- In layout **6141**, Jill’s bench closed. The self-organizing team began claiming her ready orders on turn 18 and finished at 291.8 seconds. The orchestrator started rerouting on turn 8, assigning Jill’s mushroom stew to Andy. All ten arrived by 170.3 seconds. See the `6141-peer-outage` and `6141-leader-outage` traces.
- In layout **6147**, Sam’s bench closed while he was coordinating. Jill and Andy staged four cake batches by 63.7 seconds. Sam assigned Jill the cake on turn 13, and her delivery at 158.5 seconds finished the trial. The self-organizing Jill claimed the cake herself on turn 14 and deposited it at 170.7 seconds. The fixed team had the ingredients ready at 76.1 seconds and ended with that cake unfinished.
- In layout **6143**, the orchestrator rerouted three ready orders. A cookie order still assigned to Sam sat ready from 86.1 seconds to 337.5 seconds and was assembled after his bench reopened. The peer team claimed that order earlier and finished the trial 34.2 seconds sooner. See order `o10` in both outage traces.

## What the result supports

Flexible ownership increased delivery when the original plan broke. A designated coordinator also sped up recovery in this menu, with the clearest difference in how long staged ingredients sat waiting for assembly. This extends the earlier independent-cooking study by requiring transfers between cooks even under fixed ownership.

The result comes from one model, one menu with varied batch sizes, a shared board that makes readiness and ownership explicit, and a long, visible outage. It estimates recovery under those conditions. The experiment varied coordination authority while keeping the coordinator among the four cooks. The early server logs show six tick-lag warnings during startup and the first wave. All 72 observed bench checks and changes were acknowledged within 255 ms of the scheduled wall clock. An exploratory check dropping the five layouts represented in that first wave left a 45.6-second timing interaction in the same direction.

[Figure](workstation-outage.pdf) · [Protocol](PROTOCOL.md) · [Reproduction](REPRODUCE.md) · [Machine-readable results](results.json) · [Raw evidence](evidence.tar.gz)

The evidence archive contains a folder for each trial with the scenario, timestamped decisions and team chat in `trace.json`, bot stdout in `agents.log`, the terminal chest reads in `server-sample.txt`, and applicable bench acknowledgments. The three `world-*.log` files contain the server startup, joins, phase markers, and terminal reads.
