# Reproduce the twelve-minute MineCollab follow-up

The [fixed protocol](EXTENDED_PROTOCOL.md) retains the eight objectives, six recipe sets and assignment order of the six-minute study. [The sandbox guide](LONG_REPRODUCE.md#prepare-the-sandbox) lists the Minecraft archive, Java and Node runtimes, and local credential setup. Use a fresh container and the original server archive for each reproduction batch.

## Build and start the sandbox

Set `world_path` to the extracted `server_data` directory and `key_path` to the mode-600 private JSON configuration. The container has no host mounts or published ports.

```bash
git clone --branch codex/minecollab-long-deadline https://github.com/Xenoxort/la_minecraft.git
cd la_minecraft
revision=1f230d0983c77e1a346c96e1ff9742dff6c9898c
build_context=$(mktemp -d)
git archive --format=tar "$revision" > "$build_context/source.tar"
docker build -f studies/communication-timing/Dockerfile -t minecollab-extended:local "$build_context"
container=minecollab-twelve-minute
docker run -d --name "$container" --init --cap-drop=ALL \
  --security-opt=no-new-privileges --memory=6500m --cpus=4 --pids-limit=768 \
  minecollab-extended:local sleep infinity
docker cp -a "$world_path" "$container:/app/tasks/server_data"
docker cp -a "$key_path" "$container:/app/keys.json"
docker exec "$container" install -d -m 1777 /tmp/extended-runs
study_uid="$(id -u):$(id -g)"
docker exec -u "$study_uid" "$container" test -r /app/keys.json
```

If reusing the earlier local sandbox image, start a fresh container from it and load the frozen source with `bash studies/timing-paper/container_source.sh "$container" "$revision"`.

## Run and export

The probe checks both abbreviated checkpoints and a reopening of chat. Verify both checkpoint files contain Andy and Jill and that the events include a GPT-6 Luna response. The published analysis excludes the probe.

```bash
docker exec -u "$study_uid" "$container" python /app/studies/timing-paper/run_extended.py /tmp/extended-runs --probe
pids=()
for worker in 0 1 2; do
  docker exec -u "$study_uid" "$container" python /app/studies/timing-paper/run_extended.py /tmp/extended-runs --worker "$worker" > "extended-worker-$worker.log" 2>&1 &
  pids+=("$!")
done
status=0
for pid in "${pids[@]}"; do wait "$pid" || status=1; done
test "$status" -eq 0
docker exec "$container" python /app/studies/timing-paper/export.py /tmp/extended-runs /tmp/extended-evidence
docker cp "$container:/tmp/extended-evidence" ./extended-evidence
python3 -B studies/timing-paper/analyze_extended.py ./extended-evidence > new-extended-results.json
docker exec "$container" unlink /app/keys.json
docker stop "$container"
docker rm "$container"
```

If a worker fails before a trial is scoreable, examine the bot and server log, then rerun the affected worker. The runner skips completed assignments and preserves earlier incomplete directories. Fresh model calls can produce different trajectories.

## Regenerate the published numbers offline

```bash
python3 -B studies/timing-paper/analyze_extended.py studies/timing-paper/data/extended > regenerated-extended-results.json
cmp regenerated-extended-results.json studies/timing-paper/extended-results.json
# With Matplotlib installed, regenerate the figure.
python3 -B studies/timing-paper/plot_extended.py regenerated-extended-results.json extended-deadline-curve
```
