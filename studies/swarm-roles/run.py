"""Run a matched swarm, fixed-role and orchestrator comparison in Minecraft."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from itertools import product
import json
from pathlib import Path
from queue import Empty, Queue
import random
import re

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("common_kitchen", HERE.parent / "common-hidden" / "run.py")
kitchen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kitchen)
arena = kitchen.arena
MODES = ("swarm", "fixed", "orchestrator")
NAMES = ("Andy", "Jill", "Alex", "Sam")
SEEDS = tuple(range(3211, 3221))


def design():
    cases = list(product(SEEDS, MODES))
    random.Random(58427).shuffle(cases)
    return cases


def fixture(seed, mode, duration, step, lane, attempt):
    recipes = list(kitchen.COMMON)
    cards = {item: {"ingredients": kitchen.INGREDIENTS[item]} for item in recipes}
    menu_order = recipes[:]
    random.Random(seed).shuffle(menu_order)
    owner_index = [(i + seed - SEEDS[0]) % len(NAMES) for i in range(len(NAMES))]
    base_owners = {item: NAMES[owner_index[i // 2]] for i, item in enumerate(menu_order)}
    center = 64 + lane * 86
    stations = [{"home": [x, 65, z], "chest": [x + 1, 65, z], "table": [x - 1, 65, z], "rooms": {}}
                for x, z in ((center - 12, -13), (center + 12, -13), (center - 12, 13), (center + 12, 13))]
    label = f"R{seed}{MODES.index(mode)}{attempt}"
    return {"seed": seed, "mode": mode, "duration": duration, "step": step, "aliases": list(NAMES),
            "players": [label + n[0] + str(i) for i, n in enumerate(NAMES)], "ids": recipes, "cards": cards,
            "leader": NAMES[(seed - SEEDS[0]) % len(NAMES)] if mode == "orchestrator" else None,
            "initial_owners": {} if mode == "swarm" else base_owners, "stations": stations}


def episode(root, server, slot, case, args):
    seed, mode = case
    label = f"{seed}-{mode}"
    attempt = 1
    while True:
        folder = root / (label if attempt == 1 else f"{label}-attempt{attempt}")
        if (folder / "complete.json").is_file():
            return
        if not folder.exists():
            break
        attempt += 1
    folder.mkdir()
    trial = fixture(*case, args.duration, args.step, slot, attempt)
    tag = trial["players"][0]
    (folder / "trial.json").write_text(json.dumps(trial, indent=2) + "\n")
    agents_log = folder / "agents.log"
    bot = None
    try:
        server.send(kitchen.setup(trial) + [f"say READY_{tag}"])
        server.mark(f"READY_{tag}")
        bot = arena.start_process(["node", "--dns-result-order=ipv4first", str(HERE / "agents.mjs"),
                                   str(server.port), str(args.key.resolve()), "trial.json"], folder, agents_log)
        arena.wait_for(bot, agents_log, lambda s: all(re.search(r'"event":"ready"[^\n]*"name":"' + n + '"', s)
                                                     for n in trial["players"]), 80)
        preparation = []
        for player, station in zip(trial["players"], trial["stations"]):
            x, y, z = station["home"]
            preparation.extend([f"clear {player}", f"tp {player} {x + .5} {y} {z + .5}"])
        server.send(preparation + [f"say START_{tag}"])
        server.mark(f"START_{tag}")
        clock = arena.stamp() + 2300
        (folder / "start.json").write_text(json.dumps({"start": clock}) + "\n")
        print(f"START {folder.name}", flush=True)
        arena.wait_for(bot, agents_log, lambda s: '"event":"ready_to_score"' in s, args.duration + 50)
        server.send([f"say TERMINAL_{tag}", *(f"data get entity {n} Inventory" for n in trial["players"]),
                     f"say END_{tag}"])
        server.mark(f"END_{tag}")
        full_log = server.log.read_text(errors="replace")
        snapshot = full_log.split(f"[Server] TERMINAL_{tag}", 1)[1].split(f"[Server] END_{tag}", 1)[0]
        joins = [line for line in full_log.splitlines() if any(f"{n} joined the game" in line for n in trial["players"])]
        (folder / "server-sample.txt").write_text("\n".join(joins) + "\n" + snapshot)
        server_stock = {alias: kitchen.inventory(snapshot, name) for alias, name in zip(NAMES, trial["players"])}
        trace = json.loads((folder / "trace.json").read_text())
        verified = sorted({recipe for alias in NAMES for recipe in trace["crafted"][alias]
                           if server_stock[alias].get(recipe)})
        if trace["finish"] is not None and len(verified) != len(trial["ids"]):
            raise ValueError("Early finish failed the server inventory check")
        elapsed = (trace["finish"] - clock) / 1000 if trace["finish"] else args.duration
        (folder / "complete.json").write_text(json.dumps({"inventories": server_stock, "verified": verified,
            "elapsed": elapsed, "full": len(verified) == len(trial["ids"]),
            "client_match": server_stock == trace["clients"]}, indent=2) + "\n")
        print(f"DONE {folder.name} {len(verified)}/{len(trial['ids'])}", flush=True)
    finally:
        arena.stop_process(bot)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--archive", type=Path, default=Path("/tmp/roles-world"))
    parser.add_argument("--key", type=Path, default=Path("/tmp/roles-keys.json"))
    parser.add_argument("--servers", type=int, default=3)
    parser.add_argument("--lanes", type=int, default=3)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    args.duration, args.step = (100, 5) if args.probe else (360, 10)
    cases = [(SEEDS[0], mode) for mode in MODES] if args.probe else design()
    args.root.mkdir(parents=True, exist_ok=True)
    manifest = {"duration": args.duration, "step": args.step, "cases": cases}
    path = args.root / "design.json"
    encoded = json.dumps(manifest, indent=2) + "\n"
    if path.exists() and path.read_text() != encoded:
        raise ValueError("Output folder has a different experiment manifest")
    path.write_text(encoded)
    queue = Queue()
    for case in cases:
        queue.put(case)
    with ThreadPoolExecutor(max_workers=args.servers) as setup:
        servers = list(setup.map(lambda i: kitchen.Server(args.root, args.archive, i, 2 * args.lanes),
                                 range(args.servers)))

    def worker(server, lane):
        misses = []
        while True:
            try:
                case = queue.get_nowait()
            except Empty:
                return misses
            try:
                episode(args.root, server, lane, case, args)
            except (RuntimeError, OSError, ValueError) as error:
                print(f"FAIL {case[0]}-{case[1]}: {error}", flush=True)
                misses.append(case)

    try:
        with ThreadPoolExecutor(max_workers=args.servers * args.lanes) as pool:
            jobs = [pool.submit(worker, srv, lane) for srv in servers for lane in range(args.lanes)]
            failures = [case for job in jobs for case in job.result()]
        if failures:
            raise SystemExit(f"{len(failures)} episodes require inspection")
    finally:
        for server in servers:
            server.close()


if __name__ == "__main__":
    main()
