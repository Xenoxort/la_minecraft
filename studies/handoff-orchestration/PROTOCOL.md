# Coordination during a Hell’s Kitchen workstation outage

**Question.** Does giving one of four cooks authority to redirect work improve recovery when the original plan breaks, compared with cooks who can claim work themselves?

## Kitchen and schedule

Four GPT-6 Luna cooks complete ten Minecraft food orders. Small orders have two ingredient batches and larger orders have three or four. Two different cooks have exclusive access to each order’s supplies. They can stage the batches independently in a shared order chest. The current owner assembles the ingredients at their own bench, crafts the order, and deposits the result in the same chest. The server verifies the food and quantity in that order’s chest, so two orders for the same food still count separately.

For each of ten matched menu seeds, run all six cells formed by the three decision rules and two kitchen environments. Every cell starts with the same batches, assignments, and actor names for that seed. One cook starts with four orders, and the others get two each. The four-order cook and coordinator identities rotate. Each cook sees the same progress board, including completed batches, ownership, station availability, prior actions, and short chat messages. Each prompt also lists the cook’s legal actions, calculated from the shared board. Supply access, kitchen actions, the deadline, and the token ceiling are identical.

| Rule | Who can change the owner of a ready order? |
| --- | --- |
| Fixed handoffs | Ownership stays fixed. |
| Self-organizing | Any cook can claim a ready order for themself. |
| Orchestrated | A designated cook can assign a ready order to any cook. The designated cook can also prep and assemble. |

In the two flexible arms, the board accepts at most one ownership change per turn and applies it the following turn. It resolves simultaneous claims in a deterministic rotating order. Ownership and source permissions are enforced on the actions. The controllers only expose bounded kitchen actions to the bots.

In the predictable kitchen every bench stays open. In the disrupted kitchen the four-order cook loses their personal assembly bench from 48 seconds through 336 seconds of the six-minute trial. This cook can continue staging ingredients at their separate supply chest. The outage starts before all four orders could be assembled at the original bench. This long interruption tests whether a team uses the backup bench when restoring the original plan would leave little time. Both conditions have server-verified markers at those times when play is still active.

The 60 trials run in a seeded shuffled order. A turn starts every 12 seconds, with at most one decision per cook and one physical action on each decision. The provider counts input tokens before generation. Each operation has a fixed ceiling of 1,450 input-plus-output tokens, or **174,000 tokens per team per trial**. Early completion stops the trial and can reduce actual model use.

## Decision and measurement

The primary outcome is the fraction of the ten orders delivered by 360 seconds. For each seed estimate orchestrated minus self-organizing in each environment, then subtract the predictable contrast from the outage contrast. Report all ten paired differences, their means, and descriptive 95% intervals from matched-seed bootstrap samples. The sample covers one model and one menu family.

Report observed completion times among complete runs and mean time through finish or cutoff across all runs. The latter measures time spent within the experimental window. Record each ready affected order’s time until its cook starts assembly, with unresolved orders capped at the horizon and explicitly marked. Also report accepted reassignments, completed rerouted orders, model and action errors, and token use. Distinguish infrastructure interruptions from valid outcomes at the cutoff. Re-run only cells that lack a validated end state and keep any failed-attempt evidence.

A practically encouraging lead would be at least half an additional order on average during outages and a positive interaction with the outage. If both appear, run ten matched outage trials with the same models and a simple rule that sends the oldest ready blocked order to an open cook who has no ready work of their own. The secondary rule comparison is descriptive and triggered by the main results.

Scripted smoke tests exercise physical handoffs, permissions, and the station outage before any scored run. A short model preflight checks live responses and is also separate from the 60 trials.

The first live preflight produced 57 wrong-source actions in 156 decisions. The shared interface was clarified before scoring by listing each cook’s legal jobs and the ready orders. This clarification adds no private information and leaves handoff rules and endpoints unchanged.
