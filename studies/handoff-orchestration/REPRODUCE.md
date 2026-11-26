# Reproduce the workstation-outage study

Use the archive and prepared image from the [existing Hell’s Kitchen sandbox](../common-hidden/REPRODUCE.md). The archive must contain `server.jar`, `server.properties`, and `Superflat`. Point `key_path` at a private mode-600 JSON file with the existing Luna API configuration. Keep the file outside the worktree. Use a fresh Docker container with no host mounts or published ports.

```bash
set -e -o pipefail
study=studies/handoff-orchestration
container=minecollab-handoff-orchestration
world_path=/absolute/path/to/server_data
key_path=/absolute/path/to/private/keys.json
docker run -d --name "$container" --init --cap-drop=ALL \
  --security-opt=no-new-privileges --memory=6400m --cpus=4 --pids-limit=768 \
  hells-kitchen-pilot:sandbox sleep infinity
docker exec "$container" mkdir -p /tmp/handoff-world /app/"$study" \
  /app/studies/common-hidden /app/studies/communication-timing /app/studies/hells-kitchen-schedules
COPYFILE_DISABLE=1 tar -C "$world_path" -cf - server.jar server.properties Superflat |
  docker exec -i "$container" tar --no-same-owner -xf - -C /tmp/handoff-world
docker exec -i "$container" sh -c 'umask 077; cat >/tmp/handoff-keys.json' < "$key_path"
for file in "$study/run.py" "$study/agents.mjs" studies/common-hidden/run.py \
  studies/communication-timing/run.py studies/hells-kitchen-schedules/warm_bundle.py; do
  docker cp "$file" "$container:/app/$file"
done
docker exec "$container" python -B /app/studies/hells-kitchen-schedules/warm_bundle.py /tmp/handoff-world

docker exec "$container" python -B "/app/$study/run.py" /tmp/handoff-probe --kind probe --servers 1 --lanes 3
docker exec "$container" python -B "/app/$study/run.py" /tmp/handoff-calibration --kind calibration --servers 1 --lanes 3
docker exec "$container" python -B "/app/$study/run.py" /tmp/handoff-study --servers 3 --lanes 3

output=$(mktemp -d)
docker cp "$container:/tmp/handoff-study" "$output/trials"
python3 -B "$study/analyze.py" "$output/trials" > "$output/results.json"
# If the reported dispatch_trigger is true, run the pre-specified follow-up.
# docker exec "$container" python -B "/app/$study/run.py" /tmp/handoff-dispatch --kind dispatch --servers 3 --lanes 3
docker exec "$container" unlink /tmp/handoff-keys.json
docker stop "$container"
docker rm "$container"
```

The preflight runs are separate from the sixty scored trials. If a setup error leaves a cell without a verified terminal record, inspect its logs and rerun the same command in the same container. The runner keeps completed records and writes retry attempts to new directories. GPT-6 Luna responses vary across live replicates.

## Verify the archived numbers without model calls

```bash
study=studies/handoff-orchestration
raw=$(mktemp -d)
tar -xzf "$study/evidence.tar.gz" -C "$raw"
python3 -B "$study/analyze.py" "$raw" > "$raw/regenerated.json"
cmp "$raw/regenerated.json" "$study/results.json"
python3 -B "$study/plot.py" "$raw/regenerated.json" "$raw/workstation-outage"
```

The verifier replays every staged ingredient and reassignment, checks the closed bench against the server’s marker and client observation, and compares the result at the six-minute cutoff against the actual Minecraft chest contents. Matplotlib is only needed to redraw the figure.
