# Reproduce the six-schedule comparison

Read the [protocol](PROTOCOL.md) for schedule definitions, the equal team-token ceiling, and metrics. The scripts use only Python’s standard library. No Minecraft server or generated-code execution is needed for these abstract puzzles.

## Run in Docker

Set `key_file` to the private mode-600 JSON configuration used by the earlier Luna runs. It contains `OPENAI_API_KEY` and may contain `OPENAI_ORG_ID`. Run from the repository root. The Docker container needs outbound access to the model endpoint. It has no host mounts or published ports.

```bash
study=studies/communication-schedules
container=minecollab-six-schedules
key_file=/absolute/path/to/private/keys.json
output=$(mktemp -d)
docker run -d --name "$container" --init --cap-drop=ALL \
  --security-opt=no-new-privileges --memory=1500m --cpus=2 --pids-limit=256 \
  --user "$(id -u):$(id -g)" --workdir /tmp python:3.12-slim sleep infinity
docker exec -i "$container" sh -c 'umask 077; cat > /tmp/private-config.json' < "$key_file"
docker cp "$study/study.py" "$container:/tmp/study.py"
docker exec "$container" python -B /tmp/study.py /tmp/fixed \
  --key-file /tmp/private-config.json --episodes 14 --requests 36
docker cp "$container:/tmp/fixed" "$output/fixed"
```

In a separate run, use the exploratory adaptive condition if desired:

```bash
docker exec "$container" python -B /tmp/study.py /tmp/adaptive \
  --key-file /tmp/private-config.json --adaptive --episodes 8 --requests 20
docker cp "$container:/tmp/adaptive" "$output/adaptive"
```

The runner skips saved trial files only when the design manifest agrees. A lost generation is accounted in its original budget slot. The runner does not reconstruct an unfinished episode’s work. If the process is interrupted, preserve its logs and treat any rerun of an unfinished episode as a fresh attempt. The final metrics compare completed, structurally verifiable episode records.

```bash
docker exec "$container" unlink /tmp/private-config.json
docker stop "$container"
docker rm "$container"
```

## Verify and analyze offline

```bash
python3 -B "$study/analyze.py" "$output/fixed" --adaptive "$output/adaptive" > "$output/results.json"
```

Omit `--adaptive` to analyze the fixed conditions alone. The verifier reconstructs every prompt from the initial problem and preceding attempts, checks the exact information visible to each agent, checks token ceilings, computes the exact optimum, and applies the same final-selection rule in every episode. It does not contact the model provider. Repeating live runs will usually produce different agent trajectories.

The locally recorded data are in `data/fixed` and `data/adaptive`. Rebuild the figure with Matplotlib after verifying the saved results.

```bash
python3 -B "$study/analyze.py" "$study/data/fixed" --adaptive "$study/data/adaptive" > "$output/regenerated.json"
cmp "$output/regenerated.json" "$study/results.json"
python3 -B "$study/plot.py" "$output/regenerated.json" "$output/quality-by-schedule"
```
