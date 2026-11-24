# Reproduce the MineCollab communication studies

The [timing pilot](../communication-timing/RESULTS.md) motivated two studies. The [fixed protocol](PROTOCOL.md) specifies 24 episodes on chat onset and objective-card access. The [phase protocol](PHASES.md) specifies nine episodes on Greg’s 20-second chat, 40-second exploration cycle. Their units of analysis are matched world blocks. The two engineering preflights are excluded.

The goals, recipe cards, and supplies are in [scenarios.json](scenarios.json) for the four-objective study and [phase_scenarios.json](phase_scenarios.json) for the six-objective study. Each episode exports the exact task presented to the bots in its `task.json`. The pinned [schedule](design.json) determines the onset study order.

## Prepare the sandbox

Clone the study branch. The original work used Node 22.23.5, Java Temurin 21.0.13.1, Python 3.11.2, the stock Mindcraft lockfile, and the 1.21.1 MineCollab server. The model ID returned during calls is recorded per episode. The remote model and network are stochastic.

```bash
git clone --branch codex/minecollab-timing-study https://github.com/Xenoxort/la_minecraft.git
cd la_minecraft
base=d86e4d77177f0869c0ad21e8afb7719c91f4376a
phases=4f99a792a7199720328c1a6a943d548ad2d1755c
build_context=$(mktemp -d)
git archive --format=tar "$base" > "$build_context/source.tar"
docker build -f studies/communication-timing/Dockerfile -t minecollab-study:local "$build_context"
```

Get `server_data.zip` from the [MineCollab archive folder](https://drive.google.com/drive/folders/1XygbitBBTsNO6q_doEiZHmdETpnyRmCS) linked by the repository guide. Extract it outside the source tree. Point `world_path` at the extracted `server_data` directory. Check it has `server.jar`, `server.properties`, and `Superflat/level.dat`. The JAR used in these trials has SHA-256 `e3bc55693e93cda0188f2e60aea28113fc647c5e85a15fa3d1b347349231b4bb`.

Set `key_path` to a private local JSON file containing `OPENAI_API_KEY`. Protect it with `chmod 600`. The commands transfer it only to the sandbox and remove the container after export. Do not add the key or archive to the checkout. Run as a regular user. Leave several gigabytes free for Docker and the image build.

```bash
world_path=/absolute/path/to/server_data
key_path=/absolute/path/to/private/keys.json
container=minecollab-paper-reproduction
docker run -d --name "$container" --init --cap-drop=ALL \
  --security-opt=no-new-privileges --memory=6500m --cpus=4 --pids-limit=512 \
  minecollab-study:local sleep infinity
docker cp -a "$world_path" "$container:/app/tasks/server_data"
docker cp -a "$key_path" "$container:/app/keys.json"
docker exec "$container" install -d -m 1777 /tmp/onset /tmp/phases
study_uid="$(id -u):$(id -g)"
docker exec -u "$study_uid" "$container" test -r /app/keys.json
```

## Run the episodes

The onset study runs at the base revision. Run this preflight and ensure it records Luna responses, chat, and server inventories. The worker commands can run together as shown. Preserve worker order and assigned conditions. Re-entering a worker command skips completed cells and gives prior incomplete attempts a new directory.

```bash
docker exec -u "$study_uid" "$container" python /app/studies/timing-paper/run_study.py /tmp/onset --probe
docker exec -u "$study_uid" "$container" python /app/studies/timing-paper/run_study.py /tmp/onset --worker 0 > onset-worker-0.log 2>&1 &
onset_0=$!
docker exec -u "$study_uid" "$container" python /app/studies/timing-paper/run_study.py /tmp/onset --worker 1 > onset-worker-1.log 2>&1 &
onset_1=$!
wait "$onset_0"
wait "$onset_1"
```

Load the phase revision only after both onset workers finish. This preserves the original app source in every onset trial. The phase preflight uses abbreviated windows, then the full runs use the scheduled 180-second episodes.

```bash
bash studies/timing-paper/container_source.sh "$container" "$phases"
docker exec -u "$study_uid" "$container" python /app/studies/timing-paper/run_phases.py /tmp/phases --probe
docker exec -u "$study_uid" "$container" python /app/studies/timing-paper/run_phases.py /tmp/phases --worker 0 > phase-worker-0.log 2>&1 &
phase_0=$!
docker exec -u "$study_uid" "$container" python /app/studies/timing-paper/run_phases.py /tmp/phases --worker 1 > phase-worker-1.log 2>&1 &
phase_1=$!
wait "$phase_0"
wait "$phase_1"
```

## Export evidence and verify numbers

These exports retain chat, action and inventory observations, server logs, task files, the exact clock, and runtime error counts. The export excludes the key, world copies, and unrestricted prompt logs. The analysis validates assignment, time limits, and chat gates and refuses to produce the full report for an incomplete study.

```bash
# Install the analysis/export code from the results revision.
for file in analyze.py export.py; do
  docker cp "studies/timing-paper/$file" "$container:/app/studies/timing-paper/$file"
done
docker exec "$container" python /app/studies/timing-paper/export.py /tmp/onset /tmp/onset-evidence
docker exec "$container" python /app/studies/timing-paper/export.py /tmp/phases /tmp/phase-evidence
docker cp "$container:/tmp/onset-evidence" ./onset-evidence
docker cp "$container:/tmp/phase-evidence" ./phase-evidence
docker exec "$container" python /app/studies/timing-paper/analyze.py /tmp/onset-evidence > onset-results.json
docker exec "$container" python /app/studies/timing-paper/analyze.py /tmp/phase-evidence --phases > phase-results.json
docker exec "$container" unlink /app/keys.json
docker stop "$container"
docker rm "$container"
```

To regenerate the published summaries without running Luna, point the analysis script at the corresponding evidence directory with Python 3.11. The exact design and raw evidence define the reproducible record. A new run evaluates the same hypotheses with new model samples.

```bash
python3 studies/timing-paper/analyze.py studies/timing-paper/data/onset > onset-results.json
python3 studies/timing-paper/analyze.py studies/timing-paper/data/phases --phases > phase-results.json
cmp onset-results.json studies/timing-paper/onset-results.json
cmp phase-results.json studies/timing-paper/phase-results.json
# With Matplotlib available, also regenerate the PNG and PDF figure.
python3 studies/timing-paper/plot.py onset-results.json phase-results.json minecollab-timing
```

The [manuscript draft](PAPER.md) contains the methods, results, and limits. The `data` directory contains the evidence used to produce all numerical comparisons. An exact-repeat audit is supplied separately and does not label which messages are off topic.
