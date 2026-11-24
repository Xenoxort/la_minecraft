# Reproduce the six-minute extension

The [protocol](LONG_PROTOCOL.md) fixes the question, schedule and outcomes. The [recipe sets](long_scenarios.json) and [assignment manifest](long_design.json) fix all 18 episodes. The published 33-episode study is the parent of this extension, with separate evidence and analysis.

## Prepare the sandbox

Use the Minecraft server archive and private OpenAI key from the [original sandbox setup](README.md#prepare-the-sandbox). Set `world_path` to the extracted `server_data` directory and `key_path` to the mode-600 private JSON file. Run these commands as a regular user with Docker. The image supplies Node 22, Java 21 and Python 3.11. The container has no host mounts or published ports.

```bash
git clone --branch codex/minecollab-long-deadline https://github.com/Xenoxort/la_minecraft.git
cd la_minecraft
revision=95f3db8f63dbf7befb74d1659607aba5afb992b0
build_context=$(mktemp -d)
git archive --format=tar "$revision" > "$build_context/source.tar"
docker build -f studies/communication-timing/Dockerfile -t minecollab-long:local "$build_context"
container=minecollab-long-deadline
docker run -d --name "$container" --init --cap-drop=ALL \
  --security-opt=no-new-privileges --memory=6500m --cpus=4 --pids-limit=768 \
  minecollab-long:local sleep infinity
docker cp -a "$world_path" "$container:/app/tasks/server_data"
docker cp -a "$key_path" "$container:/app/keys.json"
docker exec "$container" install -d -m 1777 /tmp/long-runs
study_uid="$(id -u):$(id -g)"
docker exec -u "$study_uid" "$container" test -r /app/keys.json
```

If reusing the earlier sandbox image, start a fresh container and load the frozen source with `bash studies/timing-paper/container_source.sh "$container" "$revision"` before running the episodes.

## Run the episodes

The preflight exercises an abbreviated checkpoint and re-opening gate. Check the preflight has a checkpoint file with both agent inventories and at least one model response before collecting the assigned episodes. Probe output is excluded from scoring.

```bash
docker exec -u "$study_uid" "$container" python /app/studies/timing-paper/run_long.py /tmp/long-runs --probe
pids=()
for worker in 0 1 2; do
  docker exec -u "$study_uid" "$container" python /app/studies/timing-paper/run_long.py /tmp/long-runs --worker "$worker" > "worker-$worker.log" 2>&1 &
  pids+=("$!")
done
status=0
for pid in "${pids[@]}"; do wait "$pid" || status=1; done
test "$status" -eq 0
```

If a worker fails to start or loses the endpoint to setup infrastructure, inspect its log before resuming that same worker. The runner skips completed assignments and leaves failed attempts visible. Run each worker at most once concurrently.

## Export and recompute

```bash
docker cp studies/timing-paper/export.py "$container:/app/studies/timing-paper/export.py"
docker exec "$container" python /app/studies/timing-paper/export.py /tmp/long-runs /tmp/long-evidence
docker cp "$container:/tmp/long-evidence" ./long-evidence
python3 -B studies/timing-paper/analyze_long.py ./long-evidence > long-results.json
docker exec "$container" unlink /app/keys.json
docker stop "$container"
docker rm "$container"
```

Regenerate the published analysis offline from the committed evidence. The second command checks that the published numbers match. The optional third command uses Matplotlib to regenerate the figure.

```bash
python3 -B studies/timing-paper/analyze_long.py studies/timing-paper/data/long > regenerated-long-results.json
cmp regenerated-long-results.json studies/timing-paper/long-results.json
python3 -B studies/timing-paper/plot_long.py regenerated-long-results.json deadline-curve
```
