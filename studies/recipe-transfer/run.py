"""Run separate teacher and student Minecraft cohorts with hidden recipes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
from queue import Empty, Queue
import re
import shutil
from tempfile import TemporaryDirectory

from scenario import SHELVES, cases, datapack, dump, trial_spec

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("common_kitchen", HERE.parent / "common-hidden" / "run.py")
kitchen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kitchen)
arena = kitchen.arena


def pos(coords):
    return " ".join(map(str, coords))


def snapshot(raw, trial):
    coords = pos(trial["positions"]["outbox"]).replace(" ", ", ")
    line = re.search(rf"\b{re.escape(coords)} has the following block data: (\[.*\])", raw)
    if not line:
        raise ValueError("Missing actual Minecraft delivery chest")
    stock = {}
    for stack in re.findall(r"\{[^{}]*\}", line[1]):
        item = re.search(r'id: "minecraft:([a-z_]+)"', stack)
        count = re.search(r"count: (\d+)", stack)
        if not item or not count:
            raise ValueError("Unexpected chest item layout")
        stock[item[1]] = stock.get(item[1], 0) + int(count[1])
    return stock


def preparation(trial):
    positions = trial["positions"]
    x, _, z = positions["home"]
    return [
        f"forceload add {x-5} {z-5} {x+5} {z+5}",
        f"fill {x-4} 64 {z-4} {x+4} 64 {z+4} smooth_stone",
        f"fill {x-4} 65 {z-4} {x+4} 70 {z+4} air",
        f'setblock {pos(positions["table"])} crafting_table',
        f'setblock {pos(positions["outbox"])} chest[type=single]',
    ]


def episode(root, server, lane, case, args, material):
    name = "-".join(map(str, case))
    attempt = 1
    while True:
        folder = root / (name if attempt == 1 else f"{name}-attempt{attempt}")
        if (folder / "complete.json").is_file():
            return
        if not folder.exists():
            break
        attempt += 1
    folder.mkdir()
    trial = trial_spec(*case, lane, attempt, args.phase, material)
    dump(folder / "trial.json", trial)
    player = trial["player"]
    log = folder / "agents.log"
    child = None
    try:
        server.send(preparation(trial) + [f"say READY_{player}"])
        server.mark(f"READY_{player}")
        child = arena.start_process(["node", "--dns-result-order=ipv4first", str(HERE / "bot.mjs"),
                                     str(server.port), str(args.key.resolve()), "trial.json"], folder, log)
        arena.wait_for(child, log, lambda text: '"event":"ready"' in text, 70)
        x, y, z = trial["positions"]["home"]
        give = [f"give {player} minecraft:{item} 12" for shelf in SHELVES for item in shelf]
        give += [f'give {player} minecraft:{row["ticket"]} 2' for row in trial["orders"].values()]
        server.send([f"clear {player}", f"gamemode survival {player}", f"tp {player} {x+.5} {y} {z+.5}",
                     *give, f"say START_{player}"])
        server.mark(f"START_{player}")
        start = arena.stamp() + 2200
        dump(folder / "start.json", {"start": start})
        print(f"START {folder.name}", flush=True)
        arena.wait_for(child, log, lambda text: '"event":"ready_to_score"' in text, trial["duration"] + 50)
        outbox = pos(trial["positions"]["outbox"])
        server.send([f"say TERMINAL_{player}", f"data get block {outbox} Items", f"say END_{player}"])
        server.mark(f"END_{player}")
        raw = server.log.read_text(errors="replace")
        join = [line for line in raw.splitlines() if f"{player} joined the game" in line]
        terminal = raw.split(f"[Server] TERMINAL_{player}", 1)[1].split(f"[Server] END_{player}", 1)[0]
        (folder / "server-sample.txt").write_text("\n".join(join) + "\n" + terminal)
        stock = snapshot(terminal, trial)
        trace = json.loads((folder / "trace.json").read_text())
        expected = {trial["orders"][id]["food"]: 1 for id in trace["done"]}
        if len(join) != 1 or stock != expected:
            raise ValueError("Server inventory or player join disagrees with the trace")
        if not trial["scripted"] and not any(row["decision"]["status"] == "completed" for row in trace["history"]):
            raise ValueError("No completed model request reached the trial")
        elapsed = (trace["finish"] - start) / 1000 if trace["finish"] else trial["duration"]
        dump(folder / "complete.json", {"stock": stock, "done": trace["done"], "elapsed": elapsed})
        print(f"DONE {folder.name} {len(trace['done'])}/{len(trial['orders'])}", flush=True)
    finally:
        arena.stop_process(child)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--phase", required=True, choices=("probe", "calibration", "teacher", "students"))
    parser.add_argument("--material", type=Path)
    parser.add_argument("--archive", type=Path, default=Path("/tmp/transfer-world"))
    parser.add_argument("--key", type=Path, default=Path("/tmp/transfer-keys.json"))
    parser.add_argument("--servers", type=int, default=3)
    parser.add_argument("--lanes", type=int, default=4)
    args = parser.parse_args()
    if (args.phase == "students") != (args.material is not None):
        parser.error("The student cohort requires its verified knowledge material")
    material = json.loads(args.material.read_text()) if args.material else {}
    plan = cases(args.phase)
    args.root.mkdir(parents=True, exist_ok=True)
    manifest = {"phase": args.phase, "cases": [list(case) for case in plan]}
    plan_path = args.root / "design.json"
    if plan_path.exists() and json.loads(plan_path.read_text()) != manifest:
        raise ValueError("Output folder belongs to a different experiment")
    dump(plan_path, manifest)
    queue = Queue()
    for case in plan:
        queue.put(case)

    def worker(server, lane):
        failures = []
        while True:
            try:
                case = queue.get_nowait()
            except Empty:
                return failures
            try:
                episode(args.root, server, lane, case, args, material)
            except (RuntimeError, ValueError, OSError) as error:
                print(f"FAIL {case[0]}-{case[1]} {error}", flush=True)
                failures.append(case)

    with TemporaryDirectory(prefix="recipe-transfer-") as workspace:
        archive = Path(workspace)
        for item in ("server.jar", "server.properties", "bundle"):
            (archive / item).symlink_to((args.archive / item).resolve())
        shutil.copytree(args.archive / "Superflat", archive / "Superflat",
                        ignore=shutil.ignore_patterns("session.lock", "playerdata", "stats", "advancements"))
        datapack(archive, plan)
        def start_server(index):
            server = kitchen.Server(args.root, archive, index, args.lanes)
            try:
                server.send(["gamerule doLimitedCrafting false", "datapack list enabled", "say RECIPES_READY"])
                server.mark("RECIPES_READY")
                if "file/hells-kitchen-recipes" not in server.log.read_text(errors="replace"):
                    raise RuntimeError("Minecraft did not enable the hidden recipe data pack")
                return server
            except Exception:
                server.close()
                raise

        with ThreadPoolExecutor(max_workers=args.servers) as startup:
            server_jobs = [startup.submit(start_server, index) for index in range(args.servers)]
            try:
                servers = [job.result() for job in server_jobs]
                with ThreadPoolExecutor(max_workers=args.servers * args.lanes) as pool:
                    jobs = [pool.submit(worker, server, lane) for server in servers for lane in range(args.lanes)]
                    failures = [case for result in jobs for case in result.result()]
                if failures:
                    raise SystemExit(f"{len(failures)} trials need retry after inspection")
            finally:
                for job in server_jobs:
                    if job.done() and not job.exception():
                        job.result().close()


if __name__ == "__main__":
    main()
