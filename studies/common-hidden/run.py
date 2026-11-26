"""Run matched six-minute common-goal and hidden-recipe trials in Minecraft."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from itertools import product
import json
from pathlib import Path
from queue import Empty, Queue
import random
import re
import shutil
from threading import Lock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("kitchen_arena", HERE.parent / "communication-timing" / "run.py")
arena = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arena)
MODES = ("public", "split", "hidden")
SCHEDULES = ("always", "blocks", "alternating")
INGREDIENTS = {
    "bread": {"wheat": 3},
    "paper": {"sugar_cane": 3},
    "bone_meal": {"bone": 1},
    "melon_seeds": {"melon_slice": 1},
    "pumpkin_pie": {"pumpkin": 1, "egg": 1, "sugar": 1},
    "cookie": {"wheat": 2, "cocoa_beans": 1},
    "golden_apple": {"gold_ingot": 8, "apple": 1},
    "hay_block": {"wheat": 9},
    "packed_mud": {"mud": 1, "wheat": 1},
    "crafting_table": {"oak_planks": 4},
    "chest": {"oak_planks": 8},
    "oak_button": {"oak_planks": 1},
    "stick": {"oak_planks": 2},
    "stone_button": {"stone": 1},
    "white_wool": {"string": 4},
    "carrot_on_a_stick": {"fishing_rod": 1, "carrot": 1},
}
COMMON = ("bread", "pumpkin_pie", "cookie", "golden_apple", "paper", "bone_meal", "hay_block", "packed_mud")
SEEDS = tuple(range(2711, 2721))


def fixture(seed, mode, schedule, duration, step, lane, attempt):
    rng = random.Random(seed)
    ids = list(INGREDIENTS) if mode == "hidden" else list(COMMON)
    cards = {}
    for id, ingredients in INGREDIENTS.items():
        left, right = rng.sample(range(1111, 9999), 2)
        if id in ids:
            cards[id] = {"left": left, "right": right, "ingredients": ingredients}
    recipe_rooms = ids[4:] + [None] * 4 if mode == "hidden" else []
    rng.shuffle(recipe_rooms)
    x = 64 + lane * 80
    stations = []
    for z in (-13, 13):
        rooms = {f"R{i + 1:02}": {"marker": [x + (-6, -2, 2, 6)[i % 4], 65,
                                              z + (-6, -3, 3, 6)[i // 4]], "id": recipe}
                 for i, recipe in enumerate(recipe_rooms)}
        stations.append({"home": [x, 65, z], "chest": [x + 1, 65, z],
                         "table": [x - 1, 65, z], "rooms": rooms})
    label = f"{seed}-{mode}-{schedule}"
    stub = f"K{seed}{MODES.index(mode)}{SCHEDULES.index(schedule)}{attempt}"
    return {"label": label, "seed": seed, "mode": mode, "schedule": schedule, "duration": duration, "step": step,
            "ids": ids, "cards": cards, "seeded": ids[:4] if mode == "hidden" else ids,
            "players": [stub + "A", stub + "J"], "stations": stations}


def xyz(pos):
    return " ".join(map(str, pos))


def setup(trial):
    items = {}
    for card in trial["cards"].values():
        for item, count in card["ingredients"].items():
            items[item] = items.get(item, 0) + count
    slots = ",".join(f'{{Slot:{i}b,id:"minecraft:{item}",count:{count}}}'
                     for i, (item, count) in enumerate(items.items()))
    commands = []
    for station in trial["stations"]:
        x, _, z = station["home"]
        commands += [
            f"forceload add {x - 9} {z - 9} {x + 9} {z + 9}",
            f"fill {x - 8} 64 {z - 8} {x + 8} 64 {z + 8} minecraft:smooth_stone",
            f"fill {x - 8} 65 {z - 8} {x + 8} 70 {z + 8} air",
            f'setblock {xyz(station["chest"])} chest{{Items:[{slots}]}}',
            f'setblock {xyz(station["table"])} crafting_table',
        ]
        commands += [f'setblock {xyz(room["marker"])} {"lime_carpet" if room["id"] else "gray_carpet"}'
                     for room in station["rooms"].values()]
    return commands


def inventory(log, player):
    m = re.search(fr"\b{re.escape(player)} has the following entity data: (.*)", log)
    if not m:
        raise ValueError(f"Missing Minecraft inventory for {player}")
    result = {}
    for stack in re.findall(r"\{[^{}]*\}", m[1]):
        item = re.search(r'id: "minecraft:([a-z_]+)"', stack)
        count = re.search(r"count: (\d+)", stack)
        if item and count:
            result[item[1]] = result.get(item[1], 0) + int(count[1])
    return result


class Server:
    def __init__(self, output, archive, index, lanes):
        self.world = output / f"world-{index}"
        self.world.mkdir()
        self.log = output / f"world-{index}.log"
        self.port = 55925 + index
        self.lock = Lock()
        (self.world / "server.jar").symlink_to((archive / "server.jar").resolve())
        shutil.copytree(archive / "Superflat", self.world / "Superflat",
                        ignore=shutil.ignore_patterns("session.lock", "playerdata", "stats", "advancements"))
        overrides = {"server-ip": "127.0.0.1", "server-port": self.port, "level-name": "Superflat",
                     "online-mode": "false", "enforce-secure-profile": "false", "difficulty": "peaceful",
                     "view-distance": 3, "simulation-distance": 3, "spawn-protection": 0,
                     "enable-rcon": "false", "enable-query": "false", "max-players": 2 * lanes + 5}
        args = [line for line in (archive / "server.properties").read_text().splitlines()
                if line.split("=", 1)[0] not in overrides]
        (self.world / "server.properties").write_text("\n".join(args + [f"{k}={v}" for k, v in overrides.items()]) + "\n")
        (self.world / "eula.txt").write_text("eula=true\n")
        args = ["java", "-Xms180m", "-Xmx1150m", "-XX:ActiveProcessorCount=2",
                f"-DbundlerRepoDir={(archive / 'bundle').resolve()}", "-jar", "server.jar", "nogui"]
        self.proc = arena.start_process(args, self.world, self.log)
        try:
            arena.wait_for(self.proc, self.log, lambda line: 'For help, type "help"' in line, 120)
            self.send(["gamerule spawnRadius 0", "gamerule doMobSpawning false", "gamerule doDaylightCycle false",
                       "gamerule doWeatherCycle false", "difficulty peaceful", "time set noon", "weather clear",
                       "setworldspawn 0 65 0", "say KITCHEN_SERVER_READY"])
            self.mark("KITCHEN_SERVER_READY")
        except Exception:
            self.close()
            raise

    def send(self, commands):
        with self.lock:
            arena.send(self.proc, commands)

    def mark(self, label):
        arena.wait_for(self.proc, self.log, lambda s: f"[Server] {label}" in s, 35)

    def close(self):
        arena.stop_process(self.proc, minecraft=True)
        shutil.rmtree(self.world)


def episode(root, server, lane, case, args):
    seed, mode, schedule = case
    tag = f"{seed}-{mode}-{schedule}"
    attempt = 1
    while True:
        work = root / (tag if attempt == 1 else f"{tag}-attempt{attempt}")
        if (work / "complete.json").exists():
            return
        if not work.exists():
            break
        attempt += 1
    work.mkdir()
    trial = fixture(*case, args.duration, args.step, lane, attempt)
    label = trial["players"][0]
    (work / "trial.json").write_text(json.dumps(trial, indent=2) + "\n")
    logs = work / "agents.log"
    bot = None
    try:
        server.send(setup(trial) + [f"say READY_{label}"])
        server.mark(f"READY_{label}")
        bot = arena.start_process(["node", "--dns-result-order=ipv4first", str(HERE / "agents.mjs"),
                                   str(server.port), str(args.key.resolve()), "trial.json"], work, logs)
        arena.wait_for(bot, logs, lambda s: all(re.search(r'"event":"ready"[^\n]*"name":"' + n + '"', s)
                                                for n in trial["players"]), 60)
        positioning = []
        for player, station in zip(trial["players"], trial["stations"]):
            x, y, z = station["home"]
            positioning += [f"clear {player}", f"tp {player} {x + .5} {y} {z + .5}"]
        server.send(positioning + [f"say START_{label}"])
        server.mark(f"START_{label}")
        start = arena.stamp() + 1800
        (work / "start.json").write_text(json.dumps({"start": start}) + "\n")
        print(f"START {work.name}", flush=True)
        arena.wait_for(bot, logs, lambda s: '"event":"ready_to_score"' in s, args.duration + 45)
        server.send([f"say TERMINAL_{label}", *(f"data get entity {n} Inventory" for n in trial["players"]),
                     f"say END_{label}"])
        server.mark(f"END_{label}")
        full = server.log.read_text(errors="replace")
        evidence = full.split(f"[Server] TERMINAL_{label}", 1)[1].split(f"[Server] END_{label}", 1)[0]
        trace = json.loads((work / "trace.json").read_text())
        counts = {alias: inventory(evidence, n) for alias, n in zip(("Andy", "Jill"), trial["players"])}
        verified = sorted({target for alias, v in counts.items() for target in trace["crafted"][alias] if v.get(target)})
        joins = [line for line in full.splitlines() if any(f"{n} joined the game" in line for n in trial["players"])]
        (work / "server-sample.txt").write_text("\n".join(joins) + "\n" + evidence)
        if trace["finish"] is not None and len(verified) != len(trial["ids"]):
            raise ValueError(f"{work.name}: early-stop inventory mismatch")
        elapsed = min(args.duration, (trace["finish"] - start) / 1000) if trace["finish"] else args.duration
        (work / "complete.json").write_text(json.dumps({"inventories": counts, "goals": verified,
            "elapsed": elapsed, "success": len(verified) == len(trial["ids"]),
            "client_match": counts == trace["clients"]}, indent=2) + "\n")
        print(f"DONE {work.name} {len(verified)}/{len(trial['ids'])}", flush=True)
    finally:
        arena.stop_process(bot)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--archive", type=Path, default=Path("/tmp/ch-world"))
    parser.add_argument("--key", type=Path, default=Path("/tmp/ch-keys.json"))
    parser.add_argument("--servers", type=int, default=3)
    parser.add_argument("--lanes", type=int, default=5)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    args.duration, args.step = (100, 5) if args.probe else (360, 10)
    cases = [(SEEDS[0], m, s) for m, s in zip(MODES, SCHEDULES)] if args.probe else list(product(SEEDS, MODES, SCHEDULES))
    random.Random(1907).shuffle(cases)
    args.out.mkdir(parents=True, exist_ok=True)
    plan = {"duration": args.duration, "step": args.step, "cases": cases}
    (args.out / "design.json").write_text(json.dumps(plan, indent=2) + "\n")
    queue = Queue()
    for case in cases:
        queue.put(case)
    with ThreadPoolExecutor(max_workers=args.servers) as startup:
        servers = list(startup.map(lambda i: Server(args.out, args.archive, i, args.lanes), range(args.servers)))

    def lane_worker(server, lane):
        while True:
            try:
                case = queue.get_nowait()
            except Empty:
                return
            try:
                episode(args.out, server, lane, case, args)
            except (RuntimeError, OSError, ValueError) as error:
                print("FAIL " + "-".join(map(str, case)) + " " + str(error), flush=True)

    try:
        with ThreadPoolExecutor(max_workers=args.servers * args.lanes) as pool:
            for future in [pool.submit(lane_worker, srv, lane) for srv in servers for lane in range(args.lanes)]:
                future.result()
    finally:
        for server in servers:
            server.close()


if __name__ == "__main__":
    main()
