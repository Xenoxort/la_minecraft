"""Run a locked MineCollab block in the disposable sandbox."""
import argparse
import importlib.util
import json
from pathlib import Path
import random
import re
import sys
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("timing_arena", HERE.parent / "communication-timing" / "run.py")
arena = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arena)
SCENARIOS = json.loads((HERE / "scenarios.json").read_text())
DESIGN_SEED = 692121
DURATION = 180
DELAY = 45
INVENTORY = re.compile(r'(Andy_0|Jill_0) has the following entity data: (.*)')
ITEM = re.compile(r'id: "minecraft:([a-z_]+)"')


def design():
    rng = random.Random(DESIGN_SEED)
    blocks = [(name, mirror) for name in SCENARIOS for mirror in (1, -1)]
    rng.shuffle(blocks)
    out = []
    for number, (name, mirror) in enumerate(blocks, 1):
        cells = [(information, delay) for information in ("known", "partner") for delay in (0, DELAY)]
        rng.shuffle(cells)
        out.append({
            "number": number, "scenario": name, "mirror": mirror,
            "order": [{"info": info, "delay": delay} for info, delay in cells],
        })
    return out


def configure(work, delay, duration, scenario, info, phase_override=None):
    total = {4: "four", 6: "six", 8: "eight"}[sum(map(len, scenario["targets"]))]
    general = (
        f"The team has {total} assigned Minecraft crafting objectives. Each item counts only in "
        "the assigned agent's inventory. Both agents may gather, craft, and share items. "
        "Keep the target items once obtained. There are supply chests around the arena and "
        "a crafting table at the center. Gather what you can while working on the shared goals. "
        f"There are {duration} seconds from the start. "
    )
    phase = (f"Bot chat opens after {delay} seconds. You can work independently until then. "
             if delay else "Bot chat is available from the start. ")
    if phase_override is not None:
        phase = phase_override
    goal = {}
    for i in range(2):
        other = scenario["cards"][1 - i]
        own = scenario["cards"][i]
        knowledge = (
            f"Your objective card: {own} "
            if info == "known"
            else "Your partner has your objective card. Ask them to tell you what items you must hold. "
        )
        goal[str(i)] = general + phase + knowledge + f"Your partner's objective card: {other}"
    data = {
        "type": "cooking", "agent_count": 2, "timeout": duration, "goal": goal,
        "target": [{item: 1 for item in targets} for targets in scenario["targets"]],
    }
    (work / "task.json").write_text(json.dumps({arena.TASK_ID: data}, indent=2))
    template = json.loads((arena.APP / "profiles/tasks/cooking_profile.json").read_text())
    for name in arena.NAMES:
        profile = dict(template, name=name, model="openai/gpt-6-luna", embedding="word-overlap")
        (work / f"{name}.json").write_text(json.dumps(profile))
    (work / "keys.json").symlink_to(arena.APP / "keys.json")


def observed_inventory(log, offset):
    with log.open() as reader:
        reader.seek(offset)
        return {name: set(ITEM.findall(data)) for name, data in INVENTORY.findall(reader.read())}


def monitor(scenario):
    latest = {}
    last_byte = 0
    last_check = 0
    targets = dict(zip(arena.NAMES, (set(items) for items in scenario["targets"])))

    def observe(server, server_log, bot_log, start, deadline):
        nonlocal last_byte, last_check
        with bot_log.open() as reader:
            reader.seek(last_byte)
            while line := reader.readline():
                if not line.endswith("\n"):
                    break
                last_byte = reader.tell()
                if line.startswith("STUDY "):
                    row = json.loads(line.removeprefix("STUDY "))
                    if row["event"] == "state":
                        latest[row["agent"]] = row
                    if row["event"] == "model_error" and row.get("status") in (400, 401, 403, 404):
                        raise RuntimeError(f"Non-retriable model error in {bot_log}")
        now = arena.stamp()
        if now - last_check < 2000 or not all(
            name in latest and latest[name]["ms"] >= max(start, now - 2200)
            and items <= set(latest[name]["inventory"]) for name, items in targets.items()
        ):
            return None
        last_check = now
        offset = server_log.stat().st_size
        arena.send(server, [f"data get entity {name} Inventory" for name in arena.NAMES])
        for _ in range(10):
            data = observed_inventory(server_log, offset)
            if all(items <= data.get(name, set()) for name, items in targets.items()):
                when = arena.stamp()
                return when if when <= deadline else None
            time.sleep(0.05)
        return None
    return observe


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--worker", type=int, choices=(0, 1), default=0)
    p.add_argument("--probe", action="store_true")
    p.add_argument("--design-only", action="store_true")
    args = p.parse_args()
    if args.design_only:
        print(json.dumps(design(), indent=2))
        return
    args.out.mkdir(parents=True, exist_ok=True)
    if args.probe:
        blocks = [{"number": 0, "scenario": "bakery", "mirror": 1,
                   "order": [{"info": "partner", "delay": 12}]}]
    else:
        blocks = design()[args.worker::2]
    for block in blocks:
        scenario = SCENARIOS[block["scenario"]]
        for cell in block["order"]:
            delay, info = cell["delay"], cell["info"]
            label = f"b{block['number']:02d}-{block['scenario']}-{info}-{delay:02d}"
            if (args.out / label / "complete.json").exists():
                continue
            attempt = 1
            while (args.out / label).exists():
                attempt += 1
                label = f"{label.split('-attempt')[0]}-attempt{attempt}"
                if (args.out / label / "complete.json").exists():
                    break
            if (args.out / label / "complete.json").exists():
                continue
            duration = 65 if args.probe else DURATION
            base_port = args.worker * 20
            arena.run(args.out, label, delay, duration, block["mirror"],
                      55916 + base_port, 8080 + base_port, False, study=scenario,
                      configure_trial=lambda work, d, s: configure(work, d, s, scenario, info),
                      observe=monitor(scenario))
            marker = args.out / label / "complete.json"
            temp = marker.with_suffix(".tmp")
            temp.write_text(json.dumps({"block": block, "cell": cell, "probe": args.probe}))
            temp.rename(marker)


if __name__ == "__main__":
    main()
