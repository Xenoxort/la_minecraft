# Transferring recipe knowledge in Hell’s Kitchen

Can a low-cost student deliver more food or discover a recipe sooner with experience from a stronger teacher? Compare the same student directly against independent discovery on the exact same puzzles.

## Task and conditions

One Minecraft cook must deliver four orders. Every order has a custom shapeless recipe with one ingredient from each of three shelves and its own order ticket. Each shelf has five possibilities. The cook sees a clue giving the sum of the three correct shelf ranks. The cook gets one crafting test per turn and observes how many picks were correct in their own shelf. It can test any triple, including one outside the rank-sum clue, and can consult its full test history. Minecraft’s own recipe engine rejects wrong attempts. On a correct craft the cook deposits the output in the delivery chest, which the server reads independently at the endpoint.

The study uses one cook per world to isolate information transfer. Both OpenAI models use low reasoning effort. The teacher is GPT-6.2 Astra and the student is GPT-6 Luna. [Official OpenAI model catalog](https://developers.openai.com/api/docs/models)

| Cohort | Recipe family | What the cook receives |
| --- | --- | --- |
| Teacher discovery | Reuse | Clues and its own test feedback. |
| Student independent discovery | Reuse | The same clues, tools, and layout as the student receiving cards. |
| Student with recipe cards | Reuse | The same clues and tools, plus the teacher-verified ingredients for each order solved in the matched teacher trial. |
| Student independent discovery | Held out | The same clues, tools, and layout as the student receiving the playbook. |
| Student with playbook | Held out | The same clues and tools, plus three procedural tips selected by Astra from its training ledger. |

There are ten teacher runs, twenty student reuse runs, and twenty student held-out runs. Trials use ten matched seeds. Both student arms within a recipe family see exactly the same puzzle. Reuse students see the same ingredient combinations the teacher discovered, with a new shelf ordering and the crafting table and outbox on opposite sides. Cards give ingredient names, so students still map them to the new shelf ranks. One card is included per independently verified teacher delivery. Any recipes the teacher missed remain hidden in the card arm and all matched runs stay in the analysis.

The held-out family contains forty unique ingredient triples disjoint from all forty training triples. Teacher worlds load only the training custom recipes for the main run. Astra sees only abstract training ledgers during synthesis. It selects three general procedures from an approved set and points to a training turn for each. Only the corresponding fixed procedure text is added to the held-out student prompt. Recipe names, specific rank triples, ingredient names, and the ledgers stay outside that playbook. The independent students see the same task description and their own results from scratch.

## Budget and analysis

Each trial has a 360-second wall-clock deadline and at most twenty decisions, one every eighteen seconds. Each decision has the same 2,500-token input-plus-output ceiling, which includes the clue board and transferred notes. Actual token consumption varies with decision length and early completion. Student runs are shuffled together. Calibration uses a separate seed and is excluded.

The two primary contrasts are the mean orders delivered at the deadline with recipe cards minus independent discovery on reuse puzzles, and playbook minus independent discovery on held-out puzzles. Report paired differences across the ten seeds and descriptive 95% matched-seed bootstrap intervals. Count trial completion and report terminal order fractions for unfinished runs. Secondary outcomes include the time to first correct craft, full completion time among full finishes, time through finish or cutoff, attempted and duplicate combinations, API errors, and tokens. For a time contrast across all matches, count the full observation window for a first craft or full completion that never occurred. Timing at this fixed cadence is largely determined by how many decisions a cook needs. Both comparisons use the same student and tool access under the same ceiling.

Evidence for direct procedural transfer is a positive held-out contrast that is consistent across matched seeds or a clear secondary reduction in decisions with no delivery penalty. A benefit on known recipes alone demonstrates direct reuse of verified solutions. The study tests one teacher, one student, and one hidden-recipe rule family.
