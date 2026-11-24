"""Score six-minute runs and compare matched policies at two horizons."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import mean, median

from analyze import INVENTORY, ITEM, effect, sign_flip
from run_long import CHECKPOINT, DURATION, SCENARIOS, SCHEDULES, design

MANIFEST = json.loads(Path(__file__).with_name("long_design.json").read_text())
NAMES = ("Andy_0", "Jill_0")


def read(path):
    return json.loads(path.read_text())


def score(path):
    meta = read(path / "complete.json")
    if meta["probe"]:
        return None
    block = meta["block"]
    schedule = meta["schedule"]
    if block != MANIFEST[block["number"] - 1] or schedule not in block["order"]:
        raise ValueError(f"Invalid assignment: {path}")
    scenario = SCENARIOS[block["scenario"]]
    targets = dict(zip(NAMES, map(set, scenario["targets"])))
    clock = read(path / "start.json")
    start, deadline = clock["startMs"], clock["deadlineMs"]
    windows = [[a * 1000, b * 1000] for a, b in SCHEDULES[schedule]]
    if deadline - start != DURATION * 1000 or clock["chatWindowsMs"] != windows or clock["mirror"] != block["mirror"]:
        raise ValueError(f"Invalid clock: {path}")
    events = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()]
    for row in events:
        ms = row["ms"] - start
        if not 0 <= ms <= DURATION * 1000:
            raise ValueError(f"Event outside episode: {path}")
        if row["event"] == "chat" and not any(a <= ms < b for a, b in windows):
            raise ValueError(f"Chat was delivered in an exploration window: {path}")
    finish = read(path / "finish.json")["verifiedCompletionMs"]
    if finish is not None and not start <= finish <= deadline:
        raise ValueError(f"Invalid finish: {path}")
    terminal = {}
    server = (path / "minecraft.log").read_text(errors="replace")
    for name, snbt in INVENTORY.findall(server):
        terminal[name] = sorted(set(ITEM.findall(snbt)))
    terminal_count = sum(len(targets[n] & set(terminal[n])) for n in targets if n in terminal)
    terminal_success = all(n in terminal and targets[n] <= set(terminal[n]) for n in targets)
    early = finish is not None and finish <= start + CHECKPOINT * 1000
    checkpoint = read(path / "checkpoint.json") if (path / "checkpoint.json").exists() else None
    if not early and checkpoint is None:
        raise ValueError(f"Missing three-minute checkpoint: {path}")
    if checkpoint is not None and checkpoint["dueMs"] != start + CHECKPOINT * 1000:
        raise ValueError(f"Mistimed checkpoint: {path}")
    if early:
        checkpoint_count = sum(map(len, targets.values()))
        checkpoint_missing = []
    else:
        items = checkpoint["inventory"]
        checkpoint_count = sum(len(targets[n] & set(items[n])) for n in targets if n in items)
        checkpoint_missing = sorted(targets.keys() - items.keys())
    actual = round((finish - start) / 1000, 3) if finish is not None else None
    ok = finish is not None or terminal_success
    runtime = read(path / "runtime.json")
    return {
        "episode": path.name, "block": block["number"], "scenario": block["scenario"],
        "schedule": schedule, "success_180": early, "success_360": ok,
        "late_completion": ok and not early, "first_verified_s": actual,
        "capped_180_s": min(actual if actual is not None else DURATION, CHECKPOINT),
        "capped_360_s": actual if actual is not None else DURATION,
        "checkpoint_objectives": checkpoint_count, "checkpoint_missing_agents": checkpoint_missing,
        "checkpoint_lag_ms": checkpoint["requestedMs"] - checkpoint["dueMs"] if checkpoint else None,
        "terminal_objectives": terminal_count, "terminal_inventory": terminal,
        "chat_count": sum(r["event"] == "chat" for r in events),
        "blocked_chat": sum(r["event"] == "chat_blocked" for r in events),
        "model_responses": sum(r["event"] == "model_response" for r in events),
        "model_errors": sum(r["event"] == "model_error" for r in events),
        "model_ids": sorted({r["model"] for r in events if r["event"] == "model_response"}),
        "restarts": runtime["restarts"], "protocol_errors": runtime["protocol_errors"],
    }


def report(path, partial=False):
    if design() != MANIFEST:
        raise ValueError("Design does not match its manifest")
    rows = [score(marker.parent) for marker in sorted(path.glob("*/complete.json"))]
    episodes = [row for row in rows if row is not None]
    by_block = defaultdict(dict)
    for row in episodes:
        block = by_block[row["block"]]
        if row["schedule"] in block:
            raise ValueError(f"Duplicate designated episode: {row['episode']}")
        block[row["schedule"]] = row
    if not partial and (len(episodes) != 18 or len(by_block) != 6
                        or any(set(b) != set(SCHEDULES) for b in by_block.values())):
        raise ValueError(f"Expected 18 completed assigned episodes, found {len(episodes)}")
    contrasts = []
    for block, cells in sorted(by_block.items()):
        if set(cells) != set(SCHEDULES):
            continue
        a, b, c = [cells[k] for k in ("alternating", "two_blocks", "always")]
        contrasts.append({"block": block, "scenario": a["scenario"],
                          "alternating_minus_two_blocks_360_s": round(a["capped_360_s"]-b["capped_360_s"], 3),
                          "alternating_minus_always_360_s": round(a["capped_360_s"]-c["capped_360_s"], 3)})
    groups = {}
    for name in SCHEDULES:
        subset = [r for r in episodes if r["schedule"] == name]
        if not subset:
            continue
        elapsed = [r["first_verified_s"] for r in subset if r["first_verified_s"] is not None]
        early = sum(r["success_180"] for r in subset)
        groups[name] = {
            "n": len(subset), "success_180": early,
            "success_360": sum(r["success_360"] for r in subset),
            "late_completions": sum(r["late_completion"] for r in subset),
            "unfinished_at_180": len(subset) - early,
            "mean_capped_180_s": round(mean(r["capped_180_s"] for r in subset), 3),
            "mean_capped_360_s": round(mean(r["capped_360_s"] for r in subset), 3),
            "median_verification_s_successes_only": median(elapsed) if elapsed else None,
        }
    values = [r["alternating_minus_two_blocks_360_s"] for r in contrasts]
    return {
        "episodes": episodes, "groups": groups, "contrasts": contrasts,
        "primary": {**effect(values), "sign_flip_p": sign_flip(values)} if values else None,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("evidence", type=Path)
    p.add_argument("--partial", action="store_true")
    args = p.parse_args()
    print(json.dumps(report(args.evidence, args.partial), indent=2))


if __name__ == "__main__":
    main()
