"""Run matched kitchen handoffs with a verified Minecraft workstation outage."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from itertools import product
import json
from pathlib import Path
from queue import Empty, Queue
import random
import re
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("common_kitchen", HERE.parent / "common-hidden" / "run.py")
kitchen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kitchen)
arena = kitchen.arena

NAMES = ("Andy", "Jill", "Alex", "Sam")
MODES = ("fixed", "peer", "leader")
ENVIRONMENTS = ("normal", "outage")
SEEDS = tuple(range(6140, 6150))
MENU = (
    ("bread", 1, 1, 2, {"wheat": 3}),
    ("cookie", 1, 8, 2, {"wheat": 2, "cocoa_beans": 1}),
    ("pumpkin_pie", 1, 1, 2, {"pumpkin": 1, "egg": 1, "sugar": 1}),
    ("mushroom_stew", 1, 1, 2, {"red_mushroom": 1, "brown_mushroom": 1, "bowl": 1}),
    ("golden_apple", 2, 2, 3, {"gold_ingot": 16, "apple": 2}),
    ("bread", 4, 4, 3, {"wheat": 12}),
    ("beetroot_soup", 2, 2, 3, {"beetroot": 12, "bowl": 2}),
    ("rabbit_stew", 2, 2, 4, {"cooked_rabbit": 2, "carrot": 2, "baked_potato": 2,
                             "brown_mushroom": 2, "bowl": 2}),
    ("cake", 1, 1, 4, {"milk_bucket": 3, "sugar": 2, "wheat": 3, "egg": 1}),
    ("cookie", 3, 24, 4, {"wheat": 6, "cocoa_beans": 3}),
)


def design(kind):
    if kind in ("probe", "calibration"):
        return [(SEEDS[0], mode, "outage") for mode in MODES]
    if kind == "dispatch":
        return [(seed, "dispatch", "outage") for seed in SEEDS]
    cases = list(product(SEEDS, MODES, ENVIRONMENTS))
    random.Random(87564).shuffle(cases)
    return cases


def fixture(seed, mode, environment, lane, attempt, kind):
    rng = random.Random(seed)
    index = seed - SEEDS[0]
    affected = NAMES[index % 4]
    leader = NAMES[(3 * index + index // 4 + 1) % 4]
    choices = list(range(len(MENU)))
    rng.shuffle(choices)
    affected_orders = set(choices[:4])
    others = [name for name in NAMES if name != affected]
    open_owners = [name for name in others for _ in range(2)]
    rng.shuffle(open_owners)
    x = 64 + lane * 84
    orders = {}
    source_loads = Counter()
    for i, (item, crafts, quantity, bins, ingredients) in enumerate(MENU):
        owner = affected if i in affected_orders else open_owners.pop()
        # Partition actual ingredients across two source cooks. Larger orders have more batches.
        units = [ingredient for ingredient, count in ingredients.items() for _ in range(count)]
        rng.shuffle(units)
        candidates = [name for name in NAMES if name != owner]
        rng.shuffle(candidates)
        source = sorted(candidates, key=source_loads.__getitem__)[:2]
        parts = {}
        for j in range(bins):
            who = source[j % 2]
            source_loads[who] += 1
            parts[str(j + 1)] = {"cook": who, "items": dict(Counter(units[j::bins]))}
        orders[f"o{i+1}"] = {"item": item, "crafts": crafts, "quantity": quantity, "owner": owner,
                              "parts": parts, "chest": [x + i % 5 - 2, 65, -2 if i < 5 else 2]}
    benches = {}
    for i, name in enumerate(NAMES):
        side = -1 if i < 2 else 1
        z = -1 if i % 2 == 0 else 1
        benches[name] = {"supply": [x + side * 3, 65, z], "table": [x + side, 65, z]}
    code = (MODES + ("dispatch",)).index(mode)
    label = f"H{seed}{code}{ENVIRONMENTS.index(environment)}{attempt}"
    return {"seed": seed, "mode": mode, "environment": environment, "affected": affected, "leader": leader,
            "players": {name: label + name[0] + str(i) for i, name in enumerate(NAMES)},
            "home": [x, 65, 0], "benches": benches, "orders": orders,
            "duration": 156 if kind in ("probe", "calibration") else 360, "step": 12,
            "close": 24 if kind in ("probe", "calibration") else 48, "reopen": 132 if kind in ("probe", "calibration") else 336,
            "scripted": kind == "probe"}


def position(coords):
    return " ".join(map(str, coords))


def chest(coords, items):
    stacks = [(item, 1) for item, amount in items.items() if item in ("milk_bucket", "mushroom_stew",
               "beetroot_soup", "rabbit_stew", "cake") for _ in range(amount)]
    stacks.extend((item, amount) for item, amount in items.items()
                  if item not in ("milk_bucket", "mushroom_stew", "beetroot_soup", "rabbit_stew", "cake"))
    if len(stacks) > 27 or any(amount > (16 if item == "egg" else 64) for item, amount in stacks):
        raise ValueError("Supply exceeds valid chest slots")
    nbt = ",".join(f'{{Slot:{i}b,id:"minecraft:{item}",count:{count}}}'
                   for i, (item, count) in enumerate(stacks))
    return f"setblock {position(coords)} chest[type=single]{{Items:[{nbt}]}}"


def setup(trial):
    x, _, z = trial["home"]
    commands = [
        f"forceload add {x-7} {z-7} {x+7} {z+7}",
        f"fill {x-5} 64 {z-5} {x+5} 64 {z+5} smooth_stone",
        f"fill {x-5} 65 {z-5} {x+5} 69 {z+5} air",
    ]
    supply = {name: Counter() for name in NAMES}
    for order in trial["orders"].values():
        commands.append(chest(order["chest"], {}))
        for part in order["parts"].values():
            supply[part["cook"]].update(part["items"])
    for name, bench in trial["benches"].items():
        commands.extend([chest(bench["supply"], supply[name]), f'setblock {position(bench["table"])} crafting_table'])
    return commands


def snapshot(sample, trial):
    contents = {}
    for id, order in trial["orders"].items():
        coords = position(order["chest"]).replace(" ", ", ")
        line = re.search(rf"\b{re.escape(coords)} has the following block data: (\[.*\])", sample)
        if not line:
            raise ValueError(f"Missing Minecraft chest data for {id}")
        items = Counter()
        for stack in re.findall(r"\{[^{}]*\}", line[1]):
            item = re.search(r'id: "minecraft:([a-z_]+)"', stack)
            count = re.search(r"count: (\d+)", stack)
            if item and count:
                items[item[1]] += int(count[1])
        contents[id] = dict(items)
    return contents


def storage(data, path):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)


def phase(server, trial, folder, label, elapsed, start, bot):
    tag = next(iter(trial["players"].values()))
    target = start + elapsed * 1000
    while arena.stamp() < target:
        if bot.poll() is not None:
            raise RuntimeError(f"Bot controller exited before {label}")
        if '"event":"ready_to_score"' in (folder / "agents.log").read_text(errors="replace"):
            return
        time.sleep(min(0.12, max(0, (target - arena.stamp()) / 1000)))
    table = position(trial["benches"][trial["affected"]]["table"])
    block = "air" if trial["environment"] == "outage" and label == "close" else "crafting_table"
    marker = f"PHASE_{tag}_{label}_{block}"
    commands = [f"setblock {table} {block}"] if trial["environment"] == "outage" else []
    sent = arena.stamp()
    server.send([*commands, f"execute if block {table} {block} run say {marker}"])
    server.mark(marker)
    log = server.log.read_text(errors="replace")
    evidence = next(line for line in log.splitlines() if f"[Server] {marker}" in line)
    storage({"target": target, "sent": sent, "ack": arena.stamp(), "block": block, "evidence": evidence},
            folder / f"{label}.json")


def episode(root, server, lane, case, args):
    tag = "-".join(map(str, case))
    attempt = 1
    while True:
        folder = root / (tag if attempt == 1 else f"{tag}-attempt{attempt}")
        if (folder / "complete.json").exists():
            return
        if not folder.exists():
            break
        attempt += 1
    folder.mkdir()
    trial = fixture(*case, lane, attempt, args.kind)
    label = next(iter(trial["players"].values()))
    storage(trial, folder / "trial.json")
    logs = folder / "agents.log"
    bot = None
    try:
        server.send(setup(trial) + [f"say READY_{label}"])
        server.mark(f"READY_{label}")
        bot = arena.start_process(["node", "--dns-result-order=ipv4first", str(HERE / "agents.mjs"),
                                   str(server.port), str(args.key.resolve()), "trial.json"], folder, logs)
        arena.wait_for(bot, logs, lambda log: all(re.search(r'"event":"ready"[^\n]*"name":"' + name + '"', log)
                                                for name in trial["players"].values()), 75)
        x, y, z = trial["home"]
        positioning = [command for player in trial["players"].values()
                       for command in (f"gamemode survival {player}", f"clear {player}", f"team join hk_cooks {player}",
                                       f"tp {player} {x + .5} {y} {z + .5}")]
        server.send(positioning + [f"say START_{label}"])
        server.mark(f"START_{label}")
        start = arena.stamp() + 1700
        storage({"start": start}, folder / "start.json")
        print(f"START {folder.name}", flush=True)
        phase(server, trial, folder, "close", trial["close"], start, bot)
        phase(server, trial, folder, "reopen", trial["reopen"], start, bot)
        arena.wait_for(bot, logs, lambda log: '"event":"ready_to_score"' in log, trial["duration"] + 40)
        server.send([f"say TERMINAL_{label}", *(f'data get block {position(order["chest"])} Items'
                                               for order in trial["orders"].values()), f"say END_{label}"])
        server.mark(f"END_{label}")
        log = server.log.read_text(errors="replace")
        marker = f"[Server] TERMINAL_{label}"
        evidence = log.split(marker, 1)[1].split(f"[Server] END_{label}", 1)[0]
        player_lines = [line for line in log.splitlines() if any(f"{name} joined the game" in line
                                                                 for name in trial["players"].values())]
        (folder / "server-sample.txt").write_text("\n".join(player_lines) + "\n" + marker + evidence)
        terminal = snapshot(evidence, trial)
        trace = json.loads((folder / "trace.json").read_text())
        done = sorted(id for id, order in trial["orders"].items()
                      if terminal[id] == {order["item"]: order["quantity"]})
        if not trial["scripted"] and not any(
            row["decision"]["status"] == "completed" for turn in trace["turns"] for row in turn["attempts"]
        ):
            raise ValueError("No completed model responses during trial")
        if done != sorted(trace["done"]) or bool(trace["finish"]) != (len(done) == len(trial["orders"])):
            raise ValueError("Craft and delivery logs disagree with the server's end state")
        storage({"done": done, "elapsed": (trace["finish"] - start) / 1000 if trace["finish"] else trial["duration"],
                 "terminal": terminal}, folder / "complete.json")
        print(f"DONE {folder.name} {len(done)}/{len(trial['orders'])}", flush=True)
    finally:
        arena.stop_process(bot)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--archive", type=Path, default=Path("/tmp/handoff-world"))
    parser.add_argument("--key", type=Path, default=Path("/tmp/handoff-keys.json"))
    parser.add_argument("--servers", type=int, default=3)
    parser.add_argument("--lanes", type=int, default=3)
    parser.add_argument("--kind", choices=("main", "probe", "calibration", "dispatch"), default="main")
    args = parser.parse_args()
    cases = design(args.kind)
    args.root.mkdir(parents=True, exist_ok=True)
    manifest = {"kind": args.kind, "cases": [list(case) for case in cases]}
    path = args.root / "design.json"
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise ValueError("Output folder has a different design")
    storage(manifest, path)
    queue = Queue()
    for case in cases:
        queue.put(case)

    def worker(server, lane):
        misses = []
        while True:
            try:
                case = queue.get_nowait()
            except Empty:
                return misses
            try:
                episode(args.root, server, lane, case, args)
            except (RuntimeError, ValueError, OSError) as error:
                print(f"FAIL {'-'.join(map(str, case))} {error}", flush=True)
                misses.append(case)

    with ThreadPoolExecutor(max_workers=args.servers) as setup_pool:
        futures = [setup_pool.submit(kitchen.Server, args.root, args.archive, i, 2 * args.lanes)
                   for i in range(args.servers)]
        try:
            for future in futures:
                server = future.result()
                server.send(["team add hk_cooks", "team modify hk_cooks collisionRule never"])
            with ThreadPoolExecutor(max_workers=args.servers * args.lanes) as pool:
                jobs = [pool.submit(worker, server, lane) for server in (future.result() for future in futures)
                        for lane in range(args.lanes)]
                failures = [case for job in jobs for case in job.result()]
            if failures:
                raise SystemExit(f"{len(failures)} episodes require inspection")
        finally:
            for future in futures:
                if future.done() and not future.exception():
                    future.result().close()


if __name__ == "__main__":
    main()
