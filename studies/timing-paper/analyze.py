"""Validate, score, and reproduce the fixed-block MineCollab analysis."""
import argparse
from collections import Counter, defaultdict
import itertools
import json
from pathlib import Path
import random
import re
from statistics import mean

HERE = Path(__file__).resolve().parent
SCENARIOS = json.loads((HERE / "scenarios.json").read_text())
DESIGN = json.loads((HERE / "design.json").read_text())
NAMES = ("Andy_0", "Jill_0")
INVENTORY = re.compile(r'(Andy_0|Jill_0) has the following entity data: (.*)')
ITEM = re.compile(r'id: "minecraft:([a-z_]+)"')


def read_json(path):
    return json.loads(path.read_text())


def score(path, phase=False):
    assignment = read_json(path / "complete.json")
    if assignment["probe"]:
        return None
    block, cell = assignment["block"], assignment["cell"]
    schedule = None
    windows = None
    scenarios = SCENARIOS
    if phase:
        from run_phases import BLOCKS, SCENARIOS as PHASE_SCENARIOS, SCHEDULES
        schedule = assignment["schedule"]
        if block != BLOCKS[block["number"] - 1] or schedule not in block["order"]:
            raise ValueError(f"Unexpected phase assignment in {path}")
        windows = [[a * 1000, b * 1000] for a, b in SCHEDULES[schedule]]
        scenarios = PHASE_SCENARIOS
    else:
        expected = DESIGN[block["number"] - 1]
        if block != expected or cell not in expected["order"]:
            raise ValueError(f"Unexpected block assignment in {path}")
    targets = dict(zip(NAMES, scenarios[block["scenario"]]["targets"]))
    clock = read_json(path / "start.json")
    start, deadline, delay = (clock[key] for key in ("startMs", "deadlineMs", "delayMs"))
    if deadline - start != 180000 or delay != cell["delay"] * 1000 or clock["mirror"] != block["mirror"]:
        raise ValueError(f"Wrong schedule in {path}")
    if clock.get("chatWindowsMs") != windows:
        raise ValueError(f"Wrong chat windows in {path}")
    start_seconds = lambda ms: round((ms - start) / 1000, 3)
    rows = sorted((json.loads(line) for line in (path / "events.jsonl").read_text()
                   .splitlines()), key=lambda r: r["ms"])
    if any(not start <= r["ms"] <= deadline for r in rows):
        raise ValueError(f"Event outside the trial window in {path}")
    chat = [r for r in rows if r["event"] == "chat"]
    def in_chat(ms):
        elapsed = ms - start
        return elapsed >= delay if windows is None else any(a <= elapsed < b for a, b in windows)

    if any(not in_chat(r["ms"]) for r in chat):
        raise ValueError(f"Message delivered while chat closed in {path}")
    seen = set()
    supplied = {n: set() for n in NAMES}
    states = Counter()
    for event in rows:
        if event["event"] == "state":
            name = event["agent"]
            states[name] += 1
            if event["ms"] <= start + 45000:
                inventory = event["inventory"]
                seen.update((name, item) for item in targets[name] if inventory.get(item))
                supplied[name].update(item for item in inventory
                                      if item in scenarios[block["scenario"]]["chests"][NAMES.index(name)])
    last_inventory = {}
    server_log = (path / "minecraft.log").read_text(errors="replace")
    for name, snbt in INVENTORY.findall(server_log):
        last_inventory[name] = sorted(ITEM.findall(snbt))
    objectives = {name: {item: item in last_inventory[name] if name in last_inventory else None
                         for item in items} for name, items in targets.items()}
    confirmed = read_json(path / "finish.json")["verifiedCompletionMs"]
    if confirmed is not None and not start <= confirmed <= deadline:
        raise ValueError(f"Invalid completion timestamp for {path}")
    final_success = all(v is True for group in objectives.values() for v in group.values())
    calls = [r for r in rows if r["event"] == "model_response"]
    model_errors = [r for r in rows if r["event"] == "model_error"]
    log = (path / "runtime.json").read_text() if (path / "runtime.json").exists() else None
    if log is None:
        raw = (path / "agents.log").read_text(errors="replace")
        health = {"restarts": raw.count("Restarting agent..."),
                  "protocol_errors": len(re.findall(r"^PartialReadError:", raw, re.MULTILINE))}
    else:
        health = json.loads(log)
    return {
        "episode": path.name, "block": block["number"], "scenario": block["scenario"],
        "mirror": block["mirror"], "information": cell["info"], "delay_s": cell["delay"],
        **({"schedule": schedule, "chat_in_later_window": any(
            r["ms"] - start >= 60000 for r in chat)} if phase else {}),
        "capped_completion_s": start_seconds(confirmed if confirmed is not None else deadline),
        "success": confirmed is not None or final_success,
        "first_verified_s": start_seconds(confirmed) if confirmed is not None else None,
        "endpoint_inventory": last_inventory, "endpoint_objectives": objectives,
        "goals_seen_by_45s": sorted(f"{agent}:{item}" for agent, item in seen),
        "chest_supplies_seen_by_45s": {n: sorted(supplied[n]) for n in NAMES},
        "first_chat_s": start_seconds(chat[0]["ms"]) if chat else None,
        "blocked_chat": sum(r["event"] == "chat_blocked" for r in rows),
        "chat_count": len(chat), "state_samples": dict(states),
        "model_responses": len(calls), "model_errors": len(model_errors),
        "model_ids": sorted({r["model"] for r in calls if r.get("model")}),
        "model_elapsed_ms": [r["elapsedMs"] for r in calls],
        "input_tokens": sum(r.get("inputTokens", 0) for r in calls),
        "output_tokens": sum(r.get("outputTokens", 0) for r in calls),
        "server_timeouts": server_log.count("lost connection: Timed out"),
        **health,
    }


def sign_flip(values):
    observed = abs(sum(values))
    return sum(abs(sum(sign * value for sign, value in zip(signs, values))) >= observed - 1e-9
               for signs in itertools.product((-1, 1), repeat=len(values))) / (2 ** len(values))


def effect(values):
    rng = random.Random(42018)
    n = len(values)
    boot = sorted(mean(rng.choices(values, k=n)) for _ in range(20000))
    return {"mean_s": round(mean(values), 3), "range_s": [round(min(values), 3), round(max(values), 3)],
            "bootstrap_95_s": [round(boot[499], 3), round(boot[19499], 3)]}


def report(root, partial=False):
    records = []
    assigned = defaultdict(dict)
    for marker in sorted(root.glob("*/complete.json")):
        trial = score(marker.parent)
        if trial is None:
            continue
        key = trial["information"], trial["delay_s"]
        block = assigned[trial["block"]]
        if key in block:
            raise ValueError(f"Duplicate assigned episode at {marker}")
        block[key] = trial
        records.append(trial)
    records.sort(key=lambda r: (r["block"], r["information"], r["delay_s"]))
    if len(records) != 24 and not partial:
        raise ValueError(f"Expected 24 completed episodes, found {len(records)}")
    contrasts = []
    for b, cells in sorted(assigned.items()):
        if len(cells) < 4:
            continue
        penalties = {name: cells[name, 45]["capped_completion_s"] - cells[name, 0]["capped_completion_s"]
                     for name in ("known", "partner")}
        contrasts.append({"block": b, "scenario": DESIGN[b - 1]["scenario"],
                          "known_delay_penalty_s": round(penalties["known"], 3),
                          "partner_delay_penalty_s": round(penalties["partner"], 3),
                          "interaction_s": round(penalties["partner"] - penalties["known"], 3)})
    if not contrasts:
        return {"episodes": records, "contrasts": []}
    overall = {}
    for name in ("known", "partner"):
        values = [c[f"{name}_delay_penalty_s"] for c in contrasts]
        overall[name] = {**effect(values), "sign_flip_p": sign_flip(values)}
    overall["interaction"] = effect([c["interaction_s"] for c in contrasts])
    return {"episodes": records, "contrasts": contrasts, "effects": overall}


def phase_report(root, partial=False):
    rows = [score(marker.parent, phase=True) for marker in sorted(root.glob("*/complete.json"))]
    assigned = defaultdict(dict)
    records = []
    for row in rows:
        if row is None:
            continue
        records.append(row)
        block = assigned[row["block"]]
        if row["schedule"] in block:
            raise ValueError(f"Duplicate phase episode: {row['episode']}")
        block[row["schedule"]] = row
    if len(records) != 9 and not partial:
        raise ValueError(f"Expected nine phase episodes, found {len(records)}")
    contrasts = []
    for block, cells in sorted(assigned.items()):
        if len(cells) < 3:
            continue
        times = {name: r["capped_completion_s"] for name, r in cells.items()}
        contrasts.append({"block": block, "scenario": cells["alternating"]["scenario"],
                          "alternating_minus_always_s": round(times["alternating"] - times["always"], 3),
                          "alternating_minus_upfront_s": round(times["alternating"] - times["upfront"], 3)})
    return {"episodes": records, "contrasts": contrasts}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("--partial", action="store_true")
    p.add_argument("--phases", action="store_true")
    args = p.parse_args()
    analyze = phase_report if args.phases else report
    print(json.dumps(analyze(args.root, args.partial), indent=2))


if __name__ == "__main__":
    main()
