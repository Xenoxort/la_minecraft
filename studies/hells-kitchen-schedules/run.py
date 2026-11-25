"""Run a real Minecraft Hell's Kitchen schedule study in the prepared sandbox."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
from itertools import product
import json
from pathlib import Path
import random
import re
import shutil
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("arena", HERE.parent / "communication-timing" / "run.py")
arena = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arena)

SCHEDULES = {
    "A": [],
    "B": list(range(1, 11)),
    "C": [2, 4, 7, 9],
    "D": [2, 3, 8, 9],
    "E": [1, 6, 9, 10],
    "F": [1, 2, 5, 10],
    "G": None,
}
NAMES = ("Andy", "Jill", "Alex", "Sam", "Taylor", "Morgan", "Casey", "Jamie")
GOALS = {
    "harvest": (
        ("bread", "3 wheat", {"wheat": 3}),
        ("pumpkin_pie", "pumpkin + egg + sugar", {"pumpkin": 1, "egg": 1, "sugar": 1}),
        ("hay_block", "9 wheat", {"wheat": 9}),
        ("melon_seeds", "1 melon slice", {"melon_slice": 1}),
        ("golden_apple", "apple surrounded by 8 gold ingots", {"apple": 1, "gold_ingot": 8}),
        ("paper", "3 sugar cane", {"sugar_cane": 3}),
        ("sugar", "1 sugar cane", {"sugar_cane": 1}),
        ("bone_meal", "1 bone", {"bone": 1}),
    ),
    "bakery": (
        ("bread", "3 wheat", {"wheat": 3}),
        ("cookie", "2 wheat + cocoa beans", {"wheat": 2, "cocoa_beans": 1}),
        ("hay_block", "9 wheat", {"wheat": 9}),
        ("packed_mud", "mud + wheat", {"mud": 1, "wheat": 1}),
        ("golden_apple", "apple surrounded by 8 gold ingots", {"apple": 1, "gold_ingot": 8}),
        ("paper", "3 sugar cane", {"sugar_cane": 3}),
        ("sugar", "1 sugar cane", {"sugar_cane": 1}),
        ("bone_meal", "1 bone", {"bone": 1}),
    ),
}


def design(recipes, adaptive):
    conditions = list(product(recipes, ("public", "split"), (2, 4, 8), SCHEDULES if adaptive else "ABCDEF"))
    random.Random(91527).shuffle(conditions)
    return conditions


def make_trial(recipes, info, n, schedule):
    cards, stations = [], []
    goals = GOALS[recipes]
    for i, name in enumerate(NAMES[:n]):
        width = len(goals) // n
        local = goals[i * width:(i + 1) * width]
        x, z = -12 + (i % 4) * 7, -7 + (i // 4) * 13
        supplies = {}
        for _, _, ingredients in local:
            for item, count in ingredients.items():
                supplies[item] = supplies.get(item, 0) + count
        cards.append({"owner": name, "goals": [{"item": item, "recipe": recipe} for item, recipe, _ in local]})
        stations.append({"spawn": [x + 0.5, 65, z + 0.5], "chest": [x + 1, 65, z],
                         "table": [x, 65, z + 1], "supplies": supplies})
    return {"recipes": recipes, "information": info, "agents": n, "schedule": schedule,
            "names": NAMES[:n], "cards": cards, "stations": stations, "windows": SCHEDULES[schedule]}


def position(xyz):
    return " ".join(map(str, xyz))


def commands(trial):
    zones = [c for c in arena.arena(1) if not (c.startswith("setblock ") and " chest" in c)
             and c != "say STUDY_ARENA_READY"]
    for station in trial["stations"]:
        slots = ",".join(f'{{Slot:{i}b,id:"minecraft:{item}",count:{count}}}'
                         for i, (item, count) in enumerate(station["supplies"].items()))
        zones += [f'setblock {position(station["chest"])} chest{{Items:[{slots}]}}',
                  f'setblock {position(station["table"])} crafting_table']
    return zones + ["say HK_ARENA_READY"]


def terminal(log, names):
    sample = log.split("[Server] HK_TERMINAL_BEGIN", 1)[1].split("[Server] HK_TERMINAL_END", 1)[0]
    terminal = {}
    for name in names:
        match = re.search(fr"\b{re.escape(name)} has the following entity data: (.*)", sample)
        if not match:
            raise ValueError(f"Server did not return an inventory for {name}")
        counts = {}
        for stack in re.findall(r"\{[^{}]*\}", match.group(1)):
            item = re.search(r'id: "minecraft:([a-z_]+)"', stack)
            count = re.search(r"count: (\d+)", stack)
            if item and count:
                counts[item[1]] = counts.get(item[1], 0) + int(count[1])
        terminal[name] = counts
    return terminal


def run(output, archive, key, trial, slot):
    label = f"{trial['recipes']}-{trial['information']}-{trial['agents']}-{trial['schedule']}"
    work = (output / label).resolve()
    attempt = 1
    while work.exists():
        if (work / "complete.json").is_file():
            return label
        attempt += 1
        work = (output / f"{label}-attempt{attempt}").resolve()
    work.mkdir()
    (work / "trial.json").write_text(json.dumps(trial, indent=2) + "\n")
    server_log, bot_log = work / "minecraft.log", work / "bots.jsonl"
    world = work / "server"
    world.mkdir()
    (world / "server.jar").symlink_to((archive / "server.jar").resolve())
    shutil.copytree(archive / "Superflat", world / "Superflat",
                    ignore=shutil.ignore_patterns("session.lock", "playerdata", "stats", "advancements"))
    props = {"server-port": 55916 + slot, "server-ip": "127.0.0.1", "level-name": "Superflat",
             "online-mode": "false", "enforce-secure-profile": "false", "difficulty": "peaceful",
             "view-distance": 3, "simulation-distance": 3, "spawn-protection": 0, "max-players": 12}
    default = (archive / "server.properties").read_text()
    lines = [line for line in default.splitlines() if line.split("=", 1)[0] not in props]
    (world / "server.properties").write_text("\n".join(lines + [f"{k}={v}" for k, v in props.items()]) + "\n")
    (world / "eula.txt").write_text("eula=true\n")
    server = bots = None
    try:
        bundle = (archive / "bundle").resolve()
        cache = [f"-DbundlerRepoDir={bundle}"] if bundle.is_dir() else []
        server = arena.start_process(["java", "-Xms200m", "-Xmx850m", "-XX:ActiveProcessorCount=2",
                                      *cache, "-jar", "server.jar", "nogui"], world, server_log)
        arena.wait_for(server, server_log, lambda s: 'For help, type "help"' in s, 110)
        arena.send(server, commands(trial))
        arena.wait_for(server, server_log, lambda s: "[Server] HK_ARENA_READY" in s, 35)
        bots = arena.start_process(["node", "--dns-result-order=ipv4first", str(HERE / "chef.mjs"),
                                    "trial.json", "start", str(55916 + slot), str(key.resolve()),
                                    "episodes.json"], work, bot_log)
        arena.wait_for(bots, bot_log, lambda s: all(
            re.search(r'"event":"bot_ready"[^\n]*"name":"' + re.escape(name) + '"', s)
            for name in trial["names"]), 50)
        setup = []
        for name, station in zip(trial["names"], trial["stations"]):
            setup += [f"clear {name}", f'tp {name} {position(station["spawn"])}']
        arena.send(server, setup + ["say HK_BEGIN"])
        arena.wait_for(server, server_log, lambda s: "[Server] HK_BEGIN" in s, 15)
        (work / "start").touch()
        print(f"START {label}", flush=True)
        arena.wait_for(bots, bot_log, lambda s: '"event":"ready_to_score"' in s, 360)
        # Allow the last Minecraft inventory update to settle on the server.
        time.sleep(1)
        arena.send(server, ["say HK_TERMINAL_BEGIN", *(f"data get entity {n} Inventory" for n in trial["names"]),
                            "say HK_TERMINAL_END"])
        arena.wait_for(server, server_log, lambda s: "[Server] HK_TERMINAL_END" in s, 20)
        observed = terminal(server_log.read_text(errors="replace"), trial["names"])
        trace = json.loads((work / "episodes.json").read_text())
        if trace["inventories"] != observed:
            raise ValueError(f"{label}: terminal inventories differ between clients and server")
        (work / "complete.json").write_text(json.dumps({"terminal": observed, "scored_at_ms": arena.stamp()},
                                                      indent=2) + "\n")
        print(f"DONE {label}", flush=True)
        return label
    finally:
        arena.stop_process(bots)
        arena.stop_process(server, minecraft=True)
        shutil.rmtree(world)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output", type=Path)
    ap.add_argument("--archive", type=Path, default=Path("/tmp/hk-world"))
    ap.add_argument("--key", type=Path, default=Path("/tmp/hk-keys.json"))
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--recipes", choices=tuple(GOALS), nargs="+", default=["harvest"])
    ap.add_argument("--adaptive", action="store_true")
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cells = [("harvest", "split", 8, "C")] if args.probe else design(args.recipes, args.adaptive)
    trials = [make_trial(*cell) for cell in cells]
    (args.output / "design.json").write_text(json.dumps(trials, indent=2) + "\n")

    def run_slot(i):
        failures = []
        for trial in trials[i::args.workers]:
            try:
                run(args.output, args.archive, args.key, trial, i)
            except (RuntimeError, ValueError, OSError) as error:
                print(f"FAIL {trial['recipes']}-{trial['information']}-{trial['agents']}-{trial['schedule']}: {error}",
                      flush=True)
                failures.append(trial)
        return failures

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = [pool.submit(run_slot, i) for i in range(args.workers)]
        failures = sum((job.result() for job in as_completed(jobs)), [])
    if failures:
        raise SystemExit(f"{len(failures)} trial(s) need review")


if __name__ == "__main__":
    main()
