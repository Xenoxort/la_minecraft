# Reproduce the live handoff study

The live run used the experiment source at `55ffb8e2cc0f1290aa865a5a95cb97b3e17ea6db`, GPT-6 Luna, seed 42, five repetitions, and a 300-second deadline. Use Java 21, Node 22, Python 3.11+, and Minecraft Java 1.21.6. The official server JAR used in the run had SHA-256 `08abf384c48afb9e822144ad8a99166482857994389269e26c6a04c6c91d9171`.

## Run fresh episodes

Use a checkout at the recorded source revision with dependencies installed via `npm ci`. The [setup README](README.md#run) describes the local OpenAI credential and Minecraft EULA flag. The published run used the previous Node/Java Docker image with the pinned source copied in, no host mounts or published ports, dropped capabilities, and an unprivileged user. The runner disables generated-code execution and rendering. Use a fresh application instance per parallel worker so bot files stay isolated.

```bash
server=/absolute/path/to/server-1.21.6.jar
practice=/absolute/path/to/handoff-practice
python3 -B tasks/handoff_experiment/run.py \
  --model gpt-6-luna --seed 42 --repetitions 5 \
  --server-jar "$server" --accept-minecraft-eula \
  --practice-only --output "$practice"
```

The eight practice episodes run sequentially. Each episode saves a note update and the eighth freezes the note. To reproduce the parallel assignment, make the practice manifest, practice JSON and frozen note available to each of three separate instances. Run the following once per instance, using `worker=0`, `worker=1` and `worker=2` and a distinct output directory.

```bash
python3 -B tasks/handoff_experiment/run.py \
  --model gpt-6-luna --seed 42 --repetitions 5 \
  --server-jar "$server" --accept-minecraft-eula \
  --evaluation-from "$practice" --workers 3 --worker "$worker" \
  --output "/absolute/path/to/handoff-evidence/eval-$worker"
```

Each worker gets five whole pairs and preserves the assigned order within a pair. Evaluation requires the practice manifest to match the pinned source, model, JAR, scenarios, and planned order. On an infrastructure interruption, reissue the same command with `--resume` after inspecting the logs. It reuses scoreable episodes, keeps prior errors and interrupted directories, and refuses to change the manifest. Run each worker only once at a time. Keep game timeouts as valid results.

## Replay the recorded results

The evidence directory contains `practice`, `eval-0`, `eval-1`, and `eval-2` subdirectories. It records the task and profile for each episode, the score, Minecraft console log, and event trace. The analysis verifies the schedule, note placement, provider model, joins, and scoring, then aggregates all 15 pairs. It can run offline without Docker or a credential.

```bash
python3 -B tasks/handoff_experiment/analyze_live.py tasks/handoff_experiment/data/luna > regenerated.json
cmp regenerated.json tasks/handoff_experiment/luna-results.json
# With Matplotlib installed, recreate the figure.
python3 -B tasks/handoff_experiment/plot_live.py regenerated.json handoff-completion
```

Fresh model calls can produce a different note and different outcomes. The offline replay uses the exact recorded note and evidence.
