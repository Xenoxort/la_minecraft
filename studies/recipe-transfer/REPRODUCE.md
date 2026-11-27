# Reproduce the recipe transfer trials

Use the MineCollab benchmark archive and prepared Docker image from the [existing sandbox](../common-hidden/REPRODUCE.md). The archive has `server.jar`, `server.properties`, and the `Superflat` world. Keep the private mode-600 API-key JSON file outside the repository. Both configured models must be available on that OpenAI API project.

```bash
set -e -o pipefail
study=studies/recipe-transfer
container=minecollab-recipe-transfer
world_path=/absolute/path/to/server_data
key_path=/absolute/path/to/private/keys.json
docker run -d --name "$container" --init --cap-drop=ALL \
  --security-opt=no-new-privileges --memory=6400m --cpus=4 --pids-limit=768 \
  hells-kitchen-pilot:sandbox sleep infinity
docker exec "$container" mkdir -p /tmp/transfer-world /tmp/replay /app/"$study" \
  /app/studies/common-hidden /app/studies/communication-timing /app/studies/hells-kitchen-schedules
COPYFILE_DISABLE=1 tar -C "$world_path" -cf - server.jar server.properties Superflat |
  docker exec -i "$container" tar --no-same-owner -xf - -C /tmp/transfer-world
docker exec -i "$container" sh -c 'umask 077; cat >/tmp/transfer-keys.json' < "$key_path"
for file in "$study/run.py" "$study/scenario.py" "$study/bot.mjs" "$study/analyze.py" "$study/derive.py" \
  studies/common-hidden/run.py studies/communication-timing/run.py studies/hells-kitchen-schedules/warm_bundle.py; do
  docker cp "$file" "$container:/app/$file"
done
docker exec "$container" python -B /app/studies/hells-kitchen-schedules/warm_bundle.py /tmp/transfer-world
docker exec "$container" python -B "/app/$study/run.py" /tmp/probe --phase probe --servers 1 --lanes 2
docker exec "$container" python -B "/app/$study/analyze.py" /tmp/probe --phase probe
docker exec "$container" python -B "/app/$study/run.py" /tmp/calibration --phase calibration --servers 1 --lanes 3
docker exec "$container" python -B "/app/$study/analyze.py" /tmp/calibration --phase calibration

docker exec "$container" python -B "/app/$study/run.py" /tmp/replay/teacher --phase teacher
docker exec "$container" python -B "/app/$study/derive.py" /tmp/replay/teacher /tmp/replay/knowledge.json
docker exec "$container" python -B "/app/$study/run.py" /tmp/replay/students --phase students --material /tmp/replay/knowledge.json

output=$(mktemp -d)
docker cp "$container:/tmp/replay/." "$output"
python3 -B "$study/analyze.py" "$output" > "$output/results.json"
docker exec "$container" unlink /tmp/transfer-keys.json
docker stop "$container"
docker rm "$container"
```

The teacher decisions and derived playbook can vary on a live rerun. Fewer servers or lanes are supported. After inspecting an infrastructure failure, rerun the same command to fill the unfinished cells. Validated terminal records are reused.

## Verify the archived runs offline

```bash
study=studies/recipe-transfer
raw=$(mktemp -d)
tar -xzf "$study/evidence.tar.gz" -C "$raw"
python3 -B "$study/analyze.py" "$raw" > "$raw/regenerated.json"
cmp "$raw/regenerated.json" "$study/results.json"
```

The verifier reconstructs every prompt, independently checks each test and delivered item against the Minecraft evidence, verifies that teacher and novel recipe triples are disjoint, and reconstructs the cards from teacher deliveries. It checks all playbook references against logged training turns. Offline verification requires no credentials or model calls.
