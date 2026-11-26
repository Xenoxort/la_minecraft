# Reproduce the role comparison

Use the Minecraft archive and Docker image from the [common-goal kitchen setup](../common-hidden/REPRODUCE.md). The archive must contain `server.jar`, `server.properties`, and `Superflat`. Use the private Luna API configuration from the existing studies. The container has no host mounts or published ports.

```sh
study=studies/swarm-roles
container=minecollab-swarm-roles
world_path=/absolute/path/to/server_data
key_path=/absolute/path/to/private/keys.json
docker run -d --name "$container" --init --cap-drop=ALL \
  --security-opt=no-new-privileges --memory=6400m --cpus=4 --pids-limit=768 \
  hells-kitchen-pilot:sandbox sleep infinity
docker exec "$container" mkdir -p /tmp/roles-world /app/studies/swarm-roles \
  /app/studies/common-hidden /app/studies/hells-kitchen-schedules /app/studies/communication-timing
tar -C "$world_path" -cf - server.jar server.properties Superflat |
  docker exec -i "$container" tar -xf - -C /tmp/roles-world
docker exec -i "$container" sh -c 'umask 077; cat >/tmp/roles-keys.json' < "$key_path"
for file in "$study/run.py" "$study/agents.mjs" studies/common-hidden/run.py \
  studies/hells-kitchen-schedules/warm_bundle.py studies/communication-timing/run.py; do
  docker cp "$file" "$container:/app/$file"
done
docker exec "$container" python -B /app/studies/hells-kitchen-schedules/warm_bundle.py /tmp/roles-world
docker exec "$container" python -B "/app/$study/run.py" /tmp/roles-probe --probe --servers 1 --lanes 3
docker exec "$container" python -B "/app/$study/run.py" /tmp/roles-study --servers 3 --lanes 3
output=$(mktemp -d)
docker cp "$container:/tmp/roles-study" "$output/trials"
python3 -B "$study/analyze.py" "$output/trials" > "$output/results.json"
docker exec "$container" unlink /tmp/roles-keys.json
docker stop "$container"
docker rm "$container"
```

If the runner reports a setup failure, review the attempt’s bot log before rerunning in the same sandbox. Completed conditions are reused. Earlier failed attempts are kept. Runs are stochastic even with matched assignments and layouts.

## Verify the recorded trials offline

```sh
study=studies/swarm-roles
raw=$(mktemp -d)
tar -xzf "$study/evidence.tar.gz" -C "$raw"
python3 -B "$study/analyze.py" "$raw" > "$raw/regenerated.json"
cmp "$raw/regenerated.json" "$study/results.json"

# With Matplotlib, rebuild the paired figure.
python3 -B "$study/plot.py" "$raw/regenerated.json" "$raw/role-comparison"
```

The verifier checks all four joins, reconstructs the roster and public progress in each prompt, checks legal assignment changes, verifies craft provenance and token accounting, and independently scores raw server inventories. This uses no model calls.
