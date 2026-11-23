"""Run the paired MineCollab timing pilot inside the prepared Docker image."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

APP = Path(__file__).resolve().parents[2]
NAMES = ("Andy_0", "Jill_0")
TARGETS = {"Andy_0": ("bread", "cookie"), "Jill_0": ("golden_apple", "paper")}
TASK_ID = "two_station_timing_hells_kitchen"
RECIPES = (
    "Jill's golden apple needs 1 apple surrounded by 8 gold ingots at a crafting table. "
    "Jill's paper uses 3 sugar cane in a row.",
    "Andy's bread uses 3 wheat. Andy's cookies use 2 wheat and 1 cocoa bean at a crafting table.",
)
INITIAL = ({"gold_ingot": 3}, {"gold_ingot": 5, "apple": 1})


def stamp():
    return time.time_ns() // 1_000_000


def start_process(args, cwd, out, env=None):
    with out.open("wb") as log:
        return subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)


def wait_for(process, log, predicate, seconds):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if process.poll() is not None:
            raise RuntimeError(f"Child exited ({process.returncode}); inspect {log}")
        if predicate(log.read_text(errors="replace")):
            return
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {log}")


def send(server, commands):
    server.stdin.write(("\n".join(commands) + "\n").encode())
    server.stdin.flush()


def stop_process(process, minecraft=False):
    if process is None or process.poll() is not None:
        return
    if minecraft:
        try:
            send(process, ["stop"])
            process.wait(15)
            return
        except (OSError, subprocess.TimeoutExpired):
            pass
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def arena(sign):
    def chest(x, z, items):
        slots = ",".join(
            f'{{Slot:{i}b,id:"minecraft:{item}",count:{count}}}'
            for i, (item, count) in enumerate(items.items())
        )
        return f"setblock {x} 65 {z} chest{{Items:[{slots}]}}"

    return [
        "gamerule spawnRadius 0", "gamerule doMobSpawning false", "gamerule doDaylightCycle false",
        "gamerule doWeatherCycle false", "difficulty peaceful", "time set noon", "weather clear",
        "setworldspawn 0 65 0",
        "forceload add -32 -32 31 31",
        "fill -24 64 -20 24 64 20 smooth_stone",
        "fill -24 65 -20 24 70 20 air",
        "fill -24 65 -20 24 66 -20 glass",
        "fill -24 65 20 24 66 20 glass",
        "fill -24 65 -19 -24 66 19 glass",
        "fill 24 65 -19 24 66 19 glass",
        "setblock 0 65 0 crafting_table",
        f"setblock {sign * -10} 64 0 blue_concrete",
        f"setblock {sign * 10} 64 0 red_concrete",
        chest(sign * -15, -7, {"wheat": 12, "cocoa_beans": 4}),
        chest(sign * 15, 7, {"sugar_cane": 12}),
        "say STUDY_ARENA_READY",
    ]


def configure(work, delay, duration):
    briefing = (
        "Complete all four team goals before time runs out. Andy must end holding bread and a cookie. "
        "Jill must end holding a golden apple and paper. You may share both items and information. "
        "A craft only counts when the assigned bot holds it. Keep all finished dishes. "
        "Walk the arena to discover supply chests. The shared crafting table is in the middle. "
        "Prepare ingredients or craft independently whenever you can. "
        "Use search ranges of 32 blocks in this small arena. "
    )
    phase = (
        f"Bot chat opens {delay} seconds after the episode starts. Explore or gather until it opens. "
        if delay else "Bot chat is available from the start. "
    )
    task = {
        "type": "cooking", "agent_count": 2, "timeout": duration,
        "target": [{item: 1 for item in TARGETS[name]} for name in NAMES],
        "goal": {str(i): briefing + phase + "Your private recipe card: " + RECIPES[i]
                 for i in range(2)},
    }
    (work / "task.json").write_text(json.dumps({TASK_ID: task}, indent=2))
    template = json.loads((APP / "profiles/tasks/cooking_profile.json").read_text())
    for name in NAMES:
        profile = dict(template, name=name, model="openai/gpt-6-luna")
        (work / f"{name}.json").write_text(json.dumps(profile))
    # The secret stays outside the output tree. Only the container has this link.
    (work / "keys.json").symlink_to(APP / "keys.json")


def events(log):
    for line in log.read_text(errors="replace").splitlines():
        if line.startswith("STUDY "):
            try:
                yield json.loads(line.removeprefix("STUDY "))
            except json.JSONDecodeError:
                continue  # The writer may still be appending the last line.


def run(root, label, delay, duration, sign, server_port, mind_port, viewer):
    work = root / label
    work.mkdir()
    configure(work, delay, duration)
    world = work / "server"
    shutil.copytree(APP / "tasks/server_data", world,
                    ignore=shutil.ignore_patterns("logs", "crash-reports", "session.lock", "playerdata",
                                                 "stats", "advancements", "Forest", "server_data"))
    props = world / "server.properties"
    values = {"server-port": server_port, "server-ip": "127.0.0.1", "level-name": "Superflat",
              "view-distance": 5, "simulation-distance": 4, "spawn-protection": 0}
    lines = [line for line in props.read_text().splitlines() if line.split("=", 1)[0] not in values]
    props.write_text("\n".join(lines + [f"{k}={v}" for k, v in values.items()]) + "\n")
    env = os.environ.copy()
    env.pop("INSECURE_CODING", None)
    env.update(NODE_OPTIONS="--dns-result-order=ipv4first", MINECOLLAB_TIMING_STUDY="1",
               SETTINGS_JSON=json.dumps({
                   "auto_open_ui": False, "render_bot_view": viewer, "allow_vision": False,
                   "allow_insecure_coding": False, "chat_ingame": False, "chat_bot_messages": False,
                   "init_message": None, "load_memory": False, "log_all_prompts": True,
                   "host": "127.0.0.1", "port": server_port, "mindserver_port": mind_port,
                   "profiles": [f"./{name}.json" for name in NAMES],
                   "max_messages": 15, "num_examples": 2,
                   "blocked_actions": ["!newAction", "!searchForEntity"],
               }))
    server_log = work / "minecraft.log"
    bot_log = work / "agents.log"
    server = bot = None
    try:
        server = start_process(["java", "-Xms256m", "-Xmx1100m", "-XX:ActiveProcessorCount=2",
                                "-jar", "server.jar", "nogui"], world, server_log)
        wait_for(server, server_log, lambda s: 'For help, type "help"' in s, 100)
        send(server, arena(sign))
        wait_for(server, server_log, lambda s: "[Server] STUDY_ARENA_READY" in s, 20)
        bot = start_process(["node", str(APP / "main.js"), "--task_path", "task.json",
                             "--task_id", TASK_ID], work, bot_log, env)
        wait_for(bot, bot_log,
                 lambda s: all(f'"event":"ready","ms":' in s and
                               re.search(r'STUDY .*"event":"ready".*"agent":"' + n + '"', s)
                               for n in NAMES), 60)
        setup = []
        for i, name in enumerate(NAMES):
            setup += [f"clear {name}", f"tp {name} {sign * (-10 + 20 * i) + 0.5} 65 0.5"]
            setup += [f"give {name} {item} {count}" for item, count in INITIAL[i].items()]
        send(server, setup + ["say STUDY_INVENTORIES_READY"])
        wait_for(server, server_log, lambda s: "[Server] STUDY_INVENTORIES_READY" in s, 20)
        start = stamp() + 1800
        deadline = start + duration * 1000
        clock = {"startMs": start, "delayMs": delay * 1000, "deadlineMs": deadline, "mirror": sign}
        temp = work / "start.tmp"
        temp.write_text(json.dumps(clock, indent=2))
        temp.rename(work / "start.json")
        print(f"{label}: {duration}s trial started, chat opens at +{delay}s", flush=True)
        while stamp() < deadline:
            if bot.poll() is not None or server.poll() is not None:
                raise RuntimeError(f"Trial process exited early: {work}")
            if "Error during message generation or file writing" in bot_log.read_text(errors="replace")[-24000:]:
                raise RuntimeError(f"Agent prompt pipeline failed: {bot_log}")
            time.sleep(0.4)
        with (work / "terminal-inventory-request.txt").open("w") as f:
            f.write(str(stamp()))
        send(server, [f"data get entity {name} Inventory" for name in NAMES])
        time.sleep(0.8)
        rows = [r for r in events(bot_log) if start <= r["ms"] <= deadline]
        (work / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        early = [r for r in rows if r["event"] == "chat" and r["ms"] < start + delay * 1000]
        if early:
            raise RuntimeError(f"{label}: chat crossed the gate before it opened")
        print(f"{label}: terminal inventory sampled; events saved", flush=True)
    finally:
        stop_process(bot)
        stop_process(server, minecraft=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--probe", action="store_true")
    p.add_argument("--viewer", action="store_true")
    p.add_argument("--pair", type=int, choices=(1, 2))
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.probe:
        run(args.out, "probe", 12, 28, 1, 55916, 8080, args.viewer)
        return
    plan = {
        1: [("pair1-immediate", 0, 1), ("pair1-delayed", 45, 1)],
        2: [("pair2-delayed", 45, -1), ("pair2-immediate", 0, -1)],
    }
    for label, delay, mirror in plan[args.pair]:
        run(args.out, label, delay, 180, mirror, 55916, 8080, args.viewer)


if __name__ == "__main__":
    main()
