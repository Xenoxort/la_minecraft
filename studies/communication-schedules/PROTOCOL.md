# Communication schedules under a matched team token budget

This pilot adapts the timing manipulation in Bernstein, Shore, and Lazer’s 2018 human experiment. Its task is a capacity-constrained project-selection puzzle with exact evaluation, run in the existing MineCollab repository. The simulator runs GPT-6 Luna against the puzzle directly. Live Minecraft is a separate environment. [2018 PNAS study](https://www.pnas.org/doi/10.1073/pnas.1802407115)

## Conditions

Each team has ten execution periods. An open period shares constraint cards and peers’ latest candidate plans before the first attempt wave and before subsequent waves within that period. A closed period does not receive new peer data. Already received candidates and cards remain visible. Each agent’s latest attempt, strongest currently legal private attempt, and editable 88-character private note persist. Cards and canonical plans are the only packet fields. Private notes are never relayed. Agents have no access to a shared filesystem, tool execution, or shared scratchpad. Agent responses are treated as data.

| ID | Configuration | Open periods |
| --- | --- | --- |
| A | Fully isolated | None |
| B | Always communicating | 1–10 |
| C | Frequent synchronization | 2, 4, 7, 9 |
| D | Infrequent synchronization | 2–3, 8–9 |
| E | Increasing synchronization frequency | 1, 6, 9, 10 |
| F | Decreasing synchronization frequency | 1, 2, 5, 10 |

C and D have the same first and last open periods and four open periods each. E and F are exact time reversals with matching first and last exposures. C through F have the same number of open periods. A and B give the boundary cases. With simultaneous attempts, B agents learn about peers’ new candidates before their next attempt. Messages use the same automatic packet policy in every open period.

Each schedule is run with 2, 4, and 8 agents. There are two fixed puzzle seeds. For each seed the exact same item values, resource limits, and conflict and prerequisite rules are presented under two information regimes:

- **Public.** All agents start with every rule. The coordination opportunity is exchanging candidate solutions.
- **Distributed.** Eight rules are evenly distributed as private cards. A team learns the complete constraint set on its first open period. Fully isolated agents can solve without sharing if their choices happen to satisfy unseen constraints.

The resulting fixed design has 72 episodes and two matched seeds per schedule, size, and information combination. Each episode has eight attempts per period. A 2-agent team gets four sequential waves, a 4-agent team gets two, and an 8-agent team gets one. Within a wave, agents make independent API calls. This holds team work opportunities constant while changing the amount of sequential search each agent gets. The design randomizes execution order with a fixed recorded seed. API generations are stochastic.

## Token accounting and selection

Every team reserves exactly 76,800 input-plus-output tokens across 80 slots of 960 tokens each. The provider’s input-token endpoint counts the structured prompt and response schema before dispatch. The generation output ceiling is 960 minus the input count. The runner checks the returned usage against the reservation. Tokens unused in one slot are not transferred. Actual usage, including any difference from the budget, is reported separately. For a response lost after dispatch, the full slot is reserved and the call is not repeated. A rejected rate-limited call may be retried. Generation uses the same configured GPT-6 Luna alias and reasoning effort setting across all conditions.

The terminal selector chooses the agent candidate with the highest public-resource-feasible benefit. Ties use the lexically first canonical plan, then the first actor. The selector is identical in every condition and never sees undisclosed rule violations or the exact optimum. The scorer separately enumerates all subsets, checks both resource limits and all eight rules, and computes the optimum. A feasible plan’s quality is its benefit divided by the optimum. An infeasible plan scores zero.

## Outcome definitions

| Outcome | Computation |
| --- | --- |
| Task success | Selected terminal plan is feasible and reaches exact optimum |
| Near-optimal success | Selected terminal plan reaches at least 90% of the optimum |
| Best individual solution | Best true quality across all private attempts across the episode |
| Average solution quality | Mean true quality of agents’ retained plans at episode end |
| Knowledge diffusion | Rule coverage, received-plan reuse, and mean individual quality |
| Solution diversity | Mean pairwise fraction of the 16 letters on which two retained plans differ |
| Wall-clock time | Time from episode start through period 10, including API queue waits |
| Total token consumption | Measured input and output tokens, with ambiguous transport slots tracked separately |
| Error correlation | Symmetric binary phi for co-occurrence of the same rule or resource violation across simultaneous agent pairs |
| Improvement after synchronization | Change in mean true quality on a reopening period from its previous closed period |
| Duplicate work | Share of valid-format attempts previously submitted by another agent, plus same-wave duplicates |

Frequencies and quality are descriptive at this sample size. Comparisons use matched seed, team size, and information regime. A repeated proposal can represent useful exploitation after learning. Reported wall-clock time includes concurrent scheduling and provider variation. The primary comparison matches token limits. An equal-deadline comparison would need an independent run with an enforced common deadline.

## Exploratory adaptive policy

G uses the same four open periods and token budget as C–F. For distributed puzzles it exchanges complementary cards in period 1. After that, if the previous period was closed, public candidate benefit has stopped increasing and the team still has at least two different candidates, it opens the channel. It otherwise stays closed unless all remaining periods are needed to meet the four-period constraint. It never looks at the exact optimum or undisclosed validation rules. This is an exploratory policy alongside the fixed six conditions.
