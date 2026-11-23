# When agents can start talking

This follows the bread and golden apple pilot. It asks whether opening chat later leads to more useful independent exploration and what that costs the team when everyone has the same deadline.

Each episode gives two GPT-6 Luna agents 180 seconds in a fresh Minecraft arena. Andy needs bread and a cookie. Jill needs a golden apple and paper. Each gets the other bot's recipe card. They may move, gather, craft, and transfer items throughout the episode. Chat is either available immediately or opens after 45 seconds. Minecraft public chat is off in both conditions. Bot-to-bot chat is gated at both the command and relay. The clock starts after both bots spawn and the console assigns positions and inventories. One loaf, one cookie, one golden apple, and one paper each count only in the assigned inventory.

There are two matched pairs. The first starts with immediate chat. The second reverses condition order and mirrors the arena on the x axis. Both conditions within a pair have the same layout, food, gold, tools, model, and deadline. The west/east stations are mirrored across pairs. The sides contain wheat and cocoa beans or sugar cane. Andy starts with the three ingots Jill needs. The delayed condition permits nonverbal coordination, including item transfers before chat opens.

The runner starts the repository's Mindcraft agents directly and sets up the world from the server console. This lets the study use a fixed arena and a shared task clock. The original evaluator, task JSON, and lockfiles are untouched. Changes to agent and relay code are active only when the study flag is set. Generated-code and Minecraft public chat are disabled. The server console and MindServer stay private to the Docker container. For live viewing, publish the bot-view ports to loopback only and pass `--viewer`. The viewer does not require the Minecraft game client.

## Run in Docker

The recorded runs reused the sandbox image from the first pilot, with Node 22, Temurin 21 and Python 3.11. For a fresh build, run these commands from the committed study branch. `git archive` leaves local credentials and world data out of the build context.

```sh
build_context=$(mktemp -d)
git archive --format=tar HEAD > "$build_context/source.tar"
docker build -f studies/communication-timing/Dockerfile -t minecollab-timing:local "$build_context"
```

If reusing the original pilot image, copy these source files into their matching paths in the container before running:

- `studies/communication-timing/`
- `src/agent/agent.js`
- `src/agent/commands/index.js`
- `src/mindcraft/mindserver.js`
- `src/models/prompter.js`

Copy the benchmark archive's extracted `server_data` to `/app/tasks/server_data`. Provide the credential at `/app/keys.json` inside the disposable container. Run unprivileged with a writable output directory and readable input files, then remove the container. The sandbox used `--cap-drop=ALL --security-opt=no-new-privileges --memory=6g --cpus=4 --pids-limit=512` with no mounts. For the cameras, add `-p 127.0.0.1:18300:3000 -p 127.0.0.1:18301:3001` and open those local ports during an episode. The camera may show sky until the bot moves. Run these commands inside the container:

```sh
python /app/studies/communication-timing/run.py /tmp/preflight --probe --viewer
python /app/studies/communication-timing/run.py /tmp/timing --pair 1 --viewer
python /app/studies/communication-timing/run.py /tmp/timing --pair 2 --viewer
python /app/studies/communication-timing/analyze.py /tmp/timing
```

The preflight is excluded from analysis. Keep each trial's `task.json`, `start.json`, `events.jsonl`, `agents.log`, and `minecraft.log`. The world copies and credential links are disposable. Score endpoint inventory from the server console and use one-second bot inventory snapshots for the first attainment of each goal. A missing server inventory is unknown. Count selected exploration and gathering commands in the first 45 seconds as attempts, since a command can fail, and report protocol errors and server timeouts separately.
