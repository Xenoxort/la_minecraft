# Reproduce the Minecraft cooking study

Use the MineCollab archive and the Java 21, Node 22, Python 3.11 sandbox image described in the [original timing setup](../timing-paper/LONG_REPRODUCE.md#prepare-the-sandbox). The sandbox has no host mounts or published ports. The study runner starts and stops each local Minecraft server and uses the pinned Mineflayer installation in the image.

Set `world_path` to the extracted folder containing `server.jar`, `server.properties`, and `Superflat`. Set `key_path` to your mode-600 private Luna API configuration. Run from the repository root.

```sh
study=studies/hells-kitchen-schedules
container=minecollab-hells-kitchen-schedules
world_path=/path/to/server_data
key_path=/path/to/private/keys.json
output=$(mktemp -d)

docker run -d --name "$container" --init --cap-drop=ALL \
  --security-opt=no-new-privileges --memory=6000m --cpus=4 --pids-limit=512 \
  hells-kitchen-pilot:sandbox sleep infinity
docker exec "$container" mkdir -p /tmp/hk-world /app/studies/hells-kitchen-schedules \
  /app/studies/communication-timing
tar -C "$world_path" -cf - server.jar server.properties Superflat |
  docker exec -i "$container" tar -C /tmp/hk-world -xf -
docker exec -i "$container" sh -c 'umask 077; cat > /tmp/hk-keys.json' < "$key_path"
docker cp studies/communication-timing/run.py "$container:/app/studies/communication-timing/run.py"
for file in run.py chef.mjs warm_bundle.py; do
  docker cp "$study/$file" "$container:/app/$study/$file"
done
docker exec "$container" python -B "/app/$study/warm_bundle.py" /tmp/hk-world

docker exec "$container" python -B "/app/$study/run.py" /tmp/hk-probe --probe --workers 1
docker exec "$container" python -B "/app/$study/run.py" /tmp/hk-study \
  --recipes harvest bakery --adaptive --workers 4
docker cp "$container:/tmp/hk-study" "$output/trials"
python3 -B "$study/analyze.py" "$output/trials" > "$output/results.json"

docker exec "$container" unlink /tmp/hk-keys.json
docker stop "$container"
docker rm "$container"
```

The probe is excluded from the comparison. Omit `--adaptive` for only A–F. To retry unfinished trials, run the same command in the same sandbox before cleanup. The runner reuses completed records and keeps failed attempts in their own directories. The analyzer requires one terminal record per condition. It reads the final inventory directly from the saved server log, checks each game result, reconstructs the recipe and progress information supplied to every bot, and validates the slot and episode budget arithmetic. The experiment has stochastic model outputs.

## Verify the recorded cohort offline

The evidence archive contains the design, bot event and action traces, final inventory records, and Minecraft server logs for all scored trials. Extract it into an empty directory. No model, Minecraft server, or credential is needed to verify the recorded results.

```sh
study=studies/hells-kitchen-schedules
raw=$(mktemp -d)
tar -xzf "$study/evidence.tar.gz" -C "$raw"
python3 -B "$study/analyze.py" "$raw" > "$raw/regenerated.json"
cmp "$raw/regenerated.json" "$study/results.json"

# With Matplotlib, rebuild the trajectory figure.
python3 -B "$study/plot.py" "$raw/regenerated.json" "$raw/kitchen-progress"
```
