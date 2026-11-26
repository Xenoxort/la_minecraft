# Reproduce the common goal and hidden recipe study

Use the MineCollab server archive and the Docker image from the [six-schedule kitchen study](../hells-kitchen-schedules/REPRODUCE.md). The image contains Java 21, Node 22, Python 3 and the pinned Mineflayer packages. Set `world_path` to the folder containing `server.jar`, `server.properties`, and `Superflat`. Use a private mode-600 JSON key file with the existing Luna API configuration.

```sh
study=studies/common-hidden
container=minecollab-common-hidden
world_path=/absolute/path/to/server_data
key_path=/absolute/path/to/private/keys.json
docker run -d --name "$container" --init --cap-drop=ALL \
  --security-opt=no-new-privileges --memory=6400m --cpus=4 --pids-limit=768 \
  hells-kitchen-pilot:sandbox sleep infinity
docker exec "$container" mkdir -p /tmp/ch-world /app/studies/common-hidden \
  /app/studies/communication-timing /app/studies/hells-kitchen-schedules
tar -C "$world_path" -cf - server.jar server.properties Superflat |
  docker exec -i "$container" tar -xf - -C /tmp/ch-world
docker exec -i "$container" sh -c 'umask 077; cat >/tmp/ch-keys.json' < "$key_path"
docker cp studies/communication-timing/run.py "$container:/app/studies/communication-timing/run.py"
docker cp studies/hells-kitchen-schedules/warm_bundle.py "$container:/app/studies/hells-kitchen-schedules/warm_bundle.py"
docker exec "$container" python -B /app/studies/hells-kitchen-schedules/warm_bundle.py /tmp/ch-world
for file in run.py agents.mjs; do
  docker cp "$study/$file" "$container:/app/$study/$file"
done
docker exec "$container" python -B "/app/$study/run.py" /tmp/ch-probe --probe --servers 1 --lanes 3
docker exec "$container" python -B "/app/$study/run.py" /tmp/ch-study --servers 3 --lanes 5
output=$(mktemp -d)
docker cp "$container:/tmp/ch-study" "$output/trials"
python3 -B "$study/analyze.py" "$output/trials" > "$output/results.json"
docker exec "$container" unlink /tmp/ch-keys.json
docker stop "$container"
docker rm "$container"
```

The preflight is excluded from the reported comparisons. Start with fewer lanes or servers on a smaller machine. Execution cadence, chat windows, and token limits do not depend on worker count. After inspecting an infrastructure failure, rerun the same command to fill cells with no verified terminal record. Earlier attempt directories remain available.

## Verify the archived results

```sh
study=studies/common-hidden
raw=$(mktemp -d)
tar -xzf "$study/evidence.tar.gz" -C "$raw"
python3 -B "$study/analyze.py" "$raw" > "$raw/regenerated.json"
cmp "$raw/regenerated.json" "$study/results.json"

# With Matplotlib, rebuild the figure.
python3 -B "$study/plot.py" "$raw/regenerated.json" "$raw/common-hidden-results"
```

The verifier independently reads both Minecraft inventories, reconstructs the cards and peer reports seen on each decision, validates the time gates and token ceilings, and recalculates group metrics. This takes no provider calls. Repeating the live experiment can produce different trajectories.
