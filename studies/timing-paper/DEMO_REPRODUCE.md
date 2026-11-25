# MineCollab demo recordings

The live clips come from fresh 240-second Harvest runs with separate Minecraft servers and the same eight-goal setup. The overhead Prismarine Viewer camera follows the live Minecraft scene from a fixed position. The text overlay shows the current relay phase and last delivered message. It stays on screen until a later message arrives. The published clips start after the terrain has loaded. Demo runs are separate from the archived study.

## Recreate the Woodwork comparison video

The split-screen video is a 3× replay of the actual recorded Woodwork trajectories, inventories, and delivered chat from the 12-minute cohort. The colors identify the same two agents across both panels. The map is schematic. The panels freeze at the server-verified completion times, 187.9 seconds for always-open chat and 73.7 seconds for 20/40 chat. This is one matched recipe set.

With Pillow, FFmpeg with libx264, and Arial Regular and Bold installed, run:

```sh
python3 -B studies/timing-paper/render_chat_replay.py studies/timing-paper \
  MineCollab-Communication-Replay.mp4 --font-dir /path/to/arial-fonts
```

Set `FFMPEG` to the full path to another encoder binary if needed. On macOS the Arial fonts are in `/System/Library/Fonts/Supplemental`.

## Record a fresh run

Prepare a disposable sandbox using the image, world, and credential setup in the [twelve-minute guide](EXTENDED_REPRODUCE.md#build-and-start-the-sandbox). Use one of the two schedule names below. When starting the sandbox, name it `minecollab-demo-$schedule` and add `-p "127.0.0.1:$port:3000"` to the Docker options. Only the camera needs a published port. Leave game code execution disabled. Load the frozen study source and copy in the demo runner.

```bash
schedule=alternating   # or always
port=18400             # use 18402 for always
container="minecollab-demo-$schedule"
run_root=/tmp/chat-demo
docker cp studies/timing-paper/run_demo.py "$container:/app/studies/timing-paper/run_demo.py"
docker exec "$container" install -d -m 1777 "$run_root"
```

Enable the overhead camera in the disposable container. This selects one viewer and gives new subscribers the arena center as their initial camera target.

```bash
docker exec -i -u 0 "$container" python - <<'PY'
from pathlib import Path
p = Path("/app/src/agent/vision/browser_viewer.js")
s = p.read_text()
assert "firstPerson: true" in s
p.write_text(s.replace("if (settings.render_bot_view)", "if (settings.render_bot_view && count_id === 0)")
              .replace("firstPerson: true", "firstPerson: false, viewDistance: 3"))
p = Path("/app/node_modules/prismarine-viewer/lib/mineflayer.js")
s = p.read_text()
move = "    bot.on('move', botPosition)"
assert s.count(move) == 1
p.write_text(s.replace(move, '    socket.emit("position", { pos: { x: 0, y: 65, z: 0 }, addMesh: false })\n'
                            '    botPosition()\n' + move))
PY
```

Install Playwright in a temporary directory (or use an existing installation). Copy the viewer’s static files to the recorder locally to avoid sending large assets across the container’s published port. The camera still takes live position, chunk, and entity updates from the sandbox.

```bash
recording=$(mktemp -d)
mkdir -p "$recording/cache/textures" "$recording/cache/blocksStates"
npm install --prefix "$recording" playwright
cp studies/timing-paper/record_demo.mjs "$recording/"
for file in index.js worker.js textures/1.21.1.png blocksStates/1.21.1.json; do
  docker cp "$container:/app/node_modules/prismarine-viewer/public/$file" "$recording/cache/$file"
done
"$recording/node_modules/.bin/playwright" install chromium
DEMO_VIEWER_CACHE="$recording/cache" node "$recording/record_demo.mjs" \
  "$schedule" "$port" "$recording/capture" "$run_root" > "$recording/recorder.log" 2>&1 &
recorder=$!
docker exec -u "$(id -u):$(id -g)" "$container" python -B \
  /app/studies/timing-paper/run_demo.py "$run_root" "$schedule"
wait "$recorder"
docker cp "$container:$run_root/$schedule" "$recording/trial"
```

On macOS, set `DEMO_CHROME` to the installed Chrome executable if using it in place of Playwright’s Chromium. The recorder uses a dedicated headless browser against the loopback camera. Real gameplay begins once the arena is visible. Inspect the WebM, then trim to the first frame showing terrain. Example for a capture where terrain appears at file timestamp 89 seconds:

```bash
ffmpeg -ss 89 -i "$recording/capture/capture.webm" -c:v libx264 \
  -pix_fmt yuv420p -movflags +faststart "$recording/MineCollab-Live.mp4"
```

The camera overlay timer is trial time. The trim point is file time. Review `capture.json` and the exported logs for the trial outcome. Remove the credential from the disposable container, then stop and remove the container using the sandbox guide.

## Recorded examples

The always-open excerpt comes from a run in which both bots stayed connected and the server verified four of eight items at the deadline. The 20/40 excerpt comes from a run in which Jill’s Minecraft connection timed out and the server could not obtain her terminal inventory. Both bots joined and made model calls in both runs. These clips illustrate the environment and schedules. The schedule comparison uses the archived 36 episodes.
