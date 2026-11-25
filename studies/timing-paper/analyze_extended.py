"""Verify and score the twelve-minute MineCollab follow-up."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import mean, median

from analyze import INVENTORY, ITEM, effect, sign_flip
from analyze_long import MANIFEST, NAMES, read
from run_extended import CHECKPOINTS, DURATION, SCHEDULES
from run_long import SCENARIOS, design

HORIZONS = (*CHECKPOINTS, DURATION)


def score(path):
    meta = read(path / "complete.json")
    if meta["probe"]:
        return None
    block = meta["block"]
    schedule = meta["schedule"]
    if block != MANIFEST[block["number"] - 1] or schedule not in block["order"]:
        raise ValueError(f"Invalid assignment: {path}")
    scenario = block["scenario"]
    targets = dict(zip(NAMES, map(set, SCENARIOS[scenario]["targets"])))

    def objectives(inventory):
        if set(inventory) != set(NAMES):
            raise ValueError(f"Inventory sample missing an agent: {path}")
        return sum(len(targets[name] & set(items)) for name, items in inventory.items())

    clock = read(path / "start.json")
    start, deadline = clock["startMs"], clock["deadlineMs"]
    windows = [[a * 1000, b * 1000] for a, b in SCHEDULES[schedule]]
    if deadline - start != DURATION * 1000 or clock["chatWindowsMs"] != windows or clock["mirror"] != block["mirror"]:
        raise ValueError(f"Invalid clock: {path}")
    finish = read(path / "finish.json")["verifiedCompletionMs"]
    if finish is not None and not start <= finish <= deadline:
        raise ValueError(f"Invalid finish: {path}")
    seconds = (finish - start) / 1000 if finish is not None else None
    events = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()]
    for row in events:
        ms = row["ms"] - start
        if not 0 <= ms <= DURATION * 1000:
            raise ValueError(f"Event outside episode: {path}")
        if row["event"] == "chat" and not any(a <= ms < b for a, b in windows):
            raise ValueError(f"Chat exceeded its scheduled window: {path}")

    server = (path / "minecraft.log").read_text(errors="replace")
    if "Done (" not in server or any(f"{name} joined the game" not in server for name in NAMES):
        raise ValueError(f"Server or agent did not start: {path}")
    terminal = {name: sorted(set(ITEM.findall(snbt))) for name, snbt in INVENTORY.findall(server)}
    terminal_count = objectives(terminal)
    goal_count = sum(map(len, targets.values()))
    snapshots = {}
    for horizon, filename in CHECKPOINTS.items():
        checkpoint_path = path / filename
        success = seconds is not None and seconds <= horizon
        snapshot = {"success": success, "objectives": goal_count if success else None, "lag_ms": None}
        if checkpoint_path.is_file():
            sample = read(checkpoint_path)
            due, asked, observed = (sample[key] for key in ("dueMs", "requestedMs", "observedMs"))
            if due != start + horizon * 1000 or not due <= asked <= observed <= deadline:
                raise ValueError(f"Invalid {horizon}s checkpoint: {path}")
            count = objectives(sample["inventory"])
            snapshot.update(objectives=goal_count if success else count, lag_ms=observed - due,
                            inventory=sample["inventory"])
        elif not success:
            raise ValueError(f"Missing {horizon}s checkpoint: {path}")
        snapshots[str(horizon)] = snapshot
    snapshots[str(DURATION)] = {"success": finish is not None or terminal_count == goal_count,
                                "objectives": terminal_count, "inventory": terminal}
    responses = [row for row in events if row["event"] == "model_response"]
    model_ids = sorted({row["model"] for row in responses})
    if model_ids != ["gpt-6-luna"]:
        raise ValueError(f"No GPT-6 Luna response or unexpected model: {path}")
    latency = [row["elapsedMs"] for row in responses if "elapsedMs" in row]
    runtime = read(path / "runtime.json")
    return {
        "episode": path.name, "block": block["number"], "scenario": scenario, "schedule": schedule,
        "first_verified_s": seconds, "capped_s": seconds if seconds is not None else DURATION,
        "endpoint_only_success": seconds is None and snapshots[str(DURATION)]["success"],
        "snapshots": snapshots, "model_ids": model_ids, "model_responses": len(responses),
        "median_model_latency_ms": median(latency) if latency else None,
        "model_errors": sum(row["event"] == "model_error" for row in events),
        "chat_count": sum(row["event"] == "chat" for row in events),
        "blocked_chat": sum(row["event"] == "chat_blocked" for row in events),
        "restarts": runtime["restarts"], "protocol_errors": runtime["protocol_errors"],
    }


def summarize(rows):
    success = {str(t): sum(row["snapshots"][str(t)]["success"] for row in rows) for t in HORIZONS}
    late = [row for row in rows if not row["snapshots"]["360"]["success"]
            and row["snapshots"][str(DURATION)]["success"]]
    times = sorted(row["first_verified_s"] for row in late if row["first_verified_s"] is not None)
    return {
        "n": len(rows), "success": success, "unfinished_at_360": len(rows) - success["360"],
        "finished_after_360": len(late), "late_times_s": times,
        "median_late_s": median(times) if times else None,
        "endpoint_only_successes": sum(row["endpoint_only_success"] for row in late),
        "mean_capped_s": {str(t): round(mean(min(row["capped_s"], t) for row in rows), 3) for t in HORIZONS},
    }


def report(root, partial=False):
    if design() != MANIFEST:
        raise ValueError("Design does not match the frozen order")
    rows = [score(marker.parent) for marker in sorted(root.glob("*/complete.json"))]
    rows = [row for row in rows if row is not None]
    blocks = defaultdict(dict)
    for row in rows:
        cells = blocks[row["block"]]
        key = row["schedule"]
        if key in cells:
            raise ValueError(f"Duplicate assignment: {row['episode']}")
        cells[key] = row
    if not partial and (len(rows) != 18 or len(blocks) != 6
                        or any(set(cells) != set(SCHEDULES) for cells in blocks.values())):
        raise ValueError(f"Expected 18 completed assigned episodes, found {len(rows)}")
    groups = {}
    for key in ("overall", *SCHEDULES):
        subset = [row for row in rows if key == "overall" or key == row["schedule"]]
        if subset:
            groups[key] = summarize(subset)
    contrasts = []
    for block, cells in sorted(blocks.items()):
        if {"alternating", "two_blocks"} <= cells.keys():
            alternating, longer = cells["alternating"], cells["two_blocks"]
            contrasts.append({"block": block, "scenario": alternating["scenario"],
                              "alternating_minus_longer_s": round(alternating["capped_s"] - longer["capped_s"], 3)})
    values = [row["alternating_minus_longer_s"] for row in contrasts]
    return {
        "horizons_s": HORIZONS, "groups": groups,
        "contrasts": contrasts, "paired_effect": {**effect(values), "sign_flip_p": sign_flip(values)} if values else None,
        "health": {key: sum(row[key] for row in rows) for key in
                   ("model_responses", "model_errors", "restarts", "protocol_errors", "chat_count", "blocked_chat")},
        "episodes": rows,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("evidence", type=Path)
    p.add_argument("--partial", action="store_true")
    args = p.parse_args()
    print(json.dumps(report(args.evidence, args.partial), indent=2))


if __name__ == "__main__":
    main()
