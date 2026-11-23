# Hell’s Kitchen pilot: GPT-6 Luna

One trial completed with two agents and one parallel world. The evaluator recorded total=1, successful=0; Andy’s terminal memory recorded score 0. The cooking task timed out after approximately 300 seconds (task start 20:37:01.980 UTC). Evaluator startup began at 20:32:55 UTC; startup time is separate from task duration.

## Source and command

Repository: https://github.com/Xenoxort/la_minecraft.git
Branch: develop
Commit: 2e2d31b062f7f251cd772a6502efab4170c85289

```sh
python tasks/evaluation_script.py \
  --task_path tasks/cooking_tasks/require_collab_test_2_items/hells_kitchen_smoke_test.json \
  --template_profile profiles/tasks/cooking_profile.json \
  --num_agents 2 --num_exp 1 --num_parallel 1 \
  --exp_name hells_kitchen_smoke --api openai --model gpt-6-luna
```

Run inside Docker with Node 22.23.5, Java 21.0.13.1, Python 3.11.2 and tmux 3.3a. Dependencies installed with npm ci and pip in a virtual environment. NODE_OPTIONS=--dns-result-order=ipv4first. Generated-code execution disabled. Runtime had no host mounts or published ports, dropped all capabilities, and ran the evaluator as an unprivileged UID. Credential copied into container, excluded from this evidence, and removed afterward. Container stopped.

## Observed behavior

- Minecraft 1.21.1 loaded Superflat and both bots joined.
- Both bots made successful GPT-6 Luna calls.
- Andy obtained one bread, confirmed by the successful crafting action output.
- Jill did not obtain a golden apple. She reported having five gold ingots and needing three more.
- Recipes were exchanged. In Andy_0/histories/11-23-2026_8-37-49PM.json, turns 3 and 4 (one-based array positions) contain Andy’s golden-apple recipe and Jill’s bread recipe respectively.
- Andy said he had five ingots but could only guide Jill with recipe steps, and declined ingredient sharing. Jill searched for gold instead.
- Protocol PartialReadError messages and Jill connection timeouts/reconnects occurred during the trial.

## Interpretation and limits

The run demonstrates functioning recipe communication and partial task completion, followed by a terminal task failure. The initial inventory gives each agent five ingots, while the golden apple requires eight. The per-agent prompt says agents may only guide the partner and cannot help ingredient collection or cooking. Andy interpreted this as prohibiting a transfer despite the profile’s generic advice to share resources. That interaction is a plausible major blocker; it does not prove the world contains no alternative gold source. Protocol errors and disconnects are an additional confounder, not a proven sole cause. One trial is insufficient to estimate a success rate or compare models.

This reproduces the existing task with the user-selected Luna model; Greg’s original model choice was not established. No application code, task definitions, or lockfiles were changed. Preserve this baseline before considering a separate experiment that clarifies whether transfers are allowed or changes the resource allocation.

## Setup interventions

Setup failures are distinct from the completed cooking trial. Java was absent from tmux’s login-shell PATH; an in-container symlink fixed discovery. Output directory permissions required adjustment for the unprivileged evaluator. Operator setup initially granted only Jill; explicit server operator commands granted both bots permission. Repeated debug operator-setup processes were stopped before launching the generated cooking script once. Logs include this setup history; two cooking task-start messages correspond to the two bots, not two trials.

## Evidence

- evaluation/: evaluator results and terminal agent snapshots.
- Andy_0/ and Jill_0/: saved memories, histories, model request logs, and profiles.
- agents.log: console output including setup and the cooking trial.
- evaluator.log: orchestration and aggregate terminal result.
- minecraft-logs/latest.log: Minecraft startup, joins, messages, and disconnects.

Archive-era compressed Minecraft logs were excluded. Credential-value scan passed before staging.
