# Swarm coordination and recipe ownership in Minecraft

Four GPT-6 Luna bots work on eight shared recipes in the MineCollab Hell’s Kitchen arena. Every bot knows the full recipes, has a stocked Minecraft chest and table, and can collect a kit, craft, or wait. A team earns a recipe once when any bot has crafted it and still holds it at the endpoint. The Minecraft server supplies the terminal inventories.

| Setup | How recipes are assigned |
| --- | --- |
| Swarm | Bots choose work as peers. The controller has no official roster. |
| Fixed roles | A roster assigns two recipes per bot. The roster stays fixed. |
| Orchestrator | The pairwise-matched fixed roster is used at the start. One designated cook can reassign one unfinished recipe per turn and still take a kitchen action. |

Assignments guide the models. Every bot keeps permission to craft any recipe and to help another bot. This makes duplicate crafting possible in every arm. In the orchestrator arm only the designated cook can change the roster. Every decision includes a snapshot of the previous turn’s progress, intentions, and short messages from all four bots. This channel is open in all conditions. Assignment changes take effect on the following turn. The orchestrator’s identity and the allocation of recipes are balanced across the ten seeds, with the same starting roster in the two role arms within each seed.

## Budget and assignment

There are ten matched seeds and one trial per condition, for 30 scored trials. The recipe menu, station layout rules, ingredient stocks, actor names, model, and action and chat permissions stay fixed. The experiment randomizes trial order. The orchestrator arm adds roster authority without replacing a worker.

Every episode has a 360-second deadline and at most one model decision per bot every ten seconds. There are up to 144 decisions at 960 input-plus-output tokens each, or a **138,240-token team ceiling**. The provider counts the input before generation and the runner caps the output at the balance of the slot. After all eight recipes are held, the runner stops and independently checks the inventories. Unfinished runs contribute the full time limit. Actual consumption is measured, since early finishes use fewer slots.

## Outcomes

Report mean verified recipes, pooled observed seconds per recipe, and finish time for each matched seed. Count duplicate crafts as successful crafts beyond the first for each recipe, including crafts by multiple bots on the same decision turn. Record extra kit collections and actual actions taken after another bot reported finishing the recipe. These diagnose duplicate work at different points.

Record every explicit wait action made while any team recipe was unfinished, including turns when all four chose to wait. Count waits attributed to instruction only when the bot’s own text mentions waiting or needing an assignment, direction, or instruction. The latter measure reflects the bot’s stated reason. Record attempted and accepted reassignments, the recipient’s response, and the orchestrator’s successful crafts. Review both role arms against the swarm, and compare fixed roles with the orchestrator to see whether dynamic authority is associated with an additional gain.

Three abbreviated preflight trials are excluded. Ten matched runs provide descriptive evidence on one recipe menu and model. The benefit of reassignment when resources fail or cooks become unavailable is a separate question.
