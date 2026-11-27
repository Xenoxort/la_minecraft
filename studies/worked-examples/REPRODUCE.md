# Reproduce the worked-example comparison

Use the [MineCollab runtime and archive](../recipe-transfer/REPRODUCE.md) with a fresh sandbox container named `minecollab-worked-examples`. Use that document’s setup commands with `/tmp/examples-world` and `/tmp/examples-keys.json` as the container archive and private key paths. Copy `studies/worked-examples/study.py` and the four shared recipe-transfer files listed below. The two configured OpenAI models are GPT-6 Luna and GPT-6.2 Astra.

```bash
set -e -o pipefail
study=studies/worked-examples
container=minecollab-worked-examples
docker exec "$container" mkdir -p /tmp/examples-run /app/"$study" /app/studies/recipe-transfer
for file in "$study/study.py" studies/recipe-transfer/{bot.mjs,run.py,scenario.py,analyze.py}; do
  docker cp "$file" "$container:/app/$file"
done
docker exec "$container" python -B "/app/$study/study.py" run /tmp/examples-probe --phase probe --servers 1 --lanes 3
docker exec "$container" python -B "/app/$study/study.py" run /tmp/examples-run/calibration --phase calibration
docker exec "$container" python -B "/app/$study/study.py" calibrate /tmp/examples-run/calibration /tmp/examples-run/difficulty.json
docker exec "$container" python -B "/app/$study/study.py" run /tmp/examples-run/donors --phase donors --difficulty /tmp/examples-run/difficulty.json --lanes 6
docker exec "$container" python -B "/app/$study/study.py" derive /tmp/examples-run/donors /tmp/examples-run/difficulty.json /tmp/examples-run/material.json
docker exec "$container" python -B "/app/$study/study.py" run /tmp/examples-run/students --phase students --difficulty /tmp/examples-run/difficulty.json --material /tmp/examples-run/material.json --lanes 6
output=$(mktemp -d)
docker cp "$container:/tmp/examples-run/." "$output"
python3 -B "$study/report.py" "$output" > "$output/results.json"
docker exec "$container" unlink /tmp/examples-keys.json
docker stop "$container"
docker rm "$container"
```

Live decisions vary. Each stage can reuse verified terminal records after an infrastructure retry. Donor and student trial outputs, calibration, and the matched example packs are in the archive. The scripted probe checks both rejection and success with the real recipe engine.

## Verify the archived evidence

```bash
study=studies/worked-examples
raw=$(mktemp -d)
tar -xzf "$study/evidence.tar.gz" -C "$raw"
python3 -B "$study/report.py" "$raw" > "$raw/regenerated.json"
cmp "$raw/regenerated.json" "$study/results.json"
# With Matplotlib installed
python3 -B "$study/plot.py" "$raw/regenerated.json" "$raw/worked-examples"
```

The offline verifier reconstructs the selected width, the example packs, each student prompt, and each final delivery. It uses the captured Minecraft inventory reads and makes no model calls.
