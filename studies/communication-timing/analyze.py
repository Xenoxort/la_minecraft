"""Summarize outcomes and explain how much active play preceded chat."""
import argparse
import json
import math
from pathlib import Path
import re

TARGETS = {"Andy_0": ("bread", "cookie"), "Jill_0": ("golden_apple", "paper")}
FIND = {"!nearbyBlocks", "!searchForBlock", "!goToCoordinates", "!goToRememberedPlace", "!viewChest",
        "!collectBlocks", "!takeFromChest"}
INVENTORY = re.compile(r'(Andy_0|Jill_0) has the following entity data: (.*)')
ITEM_ID = re.compile(r'id: "minecraft:([a-z_]+)"')


def summarize(path):
    clock = json.loads((path / "start.json").read_text())
    events = sorted((json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()),
                    key=lambda row: row["ms"])
    start, delay, deadline = (clock[k] for k in ("startMs", "delayMs", "deadlineMs"))
    seconds = lambda row: round((row["ms"] - start) / 1000, 1)
    states = {agent: None for agent in TARGETS}
    first_items = {}
    joint_time = None
    for row in events:
        if row["event"] != "state":
            continue
        states[row["agent"]] = row
        for item in TARGETS[row["agent"]]:
            if row["inventory"].get(item, 0):
                first_items.setdefault(item, seconds(row))
        # Require contemporaneous observations from both agents.
        if joint_time is None and all(
            state and abs(state["ms"] - row["ms"]) < 1500
            and all(state["inventory"].get(item, 0) for item in TARGETS[agent])
            for agent, state in states.items()
        ):
            joint_time = seconds(row)
    first_45 = {name: [] for name in TARGETS}
    for row in events:
        if row["event"] == "state" and row["position"] and row["ms"] < start + 45000:
            first_45[row["agent"]].append(row)
    early_distance = {
        name: round(sum(math.hypot(b["position"][0] - a["position"][0],
                                   b["position"][2] - a["position"][2])
                        for a, b in zip(samples, samples[1:])), 1)
        for name, samples in first_45.items()
    }
    early_supplies = {
        name: sorted({item for row in samples for item in ("wheat", "cocoa_beans", "sugar_cane")
                      if row["inventory"].get(item, 0)})
        for name, samples in first_45.items()
    }
    server_log = (path / "minecraft.log").read_text(errors="replace")
    agents_log = (path / "agents.log").read_text(errors="replace")
    terminal_inventory = {name: ITEM_ID.findall(value) for name, value in INVENTORY.findall(server_log)}
    final_items = {
        item: (item in terminal_inventory[agent] if agent in terminal_inventory else None)
        for agent, targets in TARGETS.items() for item in targets
    }
    delivered = [r for r in events if r["event"] == "chat"]
    messages = [r for r in delivered if r.get("message", "").strip()]
    blocked = [r for r in events if r["event"] == "chat_blocked"]
    return {
        "trial": path.name,
        "delay_s": delay // 1000,
        "duration_s": (deadline - start) // 1000,
        "first_chat_s": seconds(messages[0]) if messages else None,
        "messages": len(messages),
        "blocked_chat_attempts": len(blocked),
        "chat_gate_violations": sum(r["ms"] < start + delay for r in delivered),
        "exploration_commands_first_45s": sum(
            r["event"] == "command" and r["command"] in FIND and r["ms"] < start + 45000
            for r in events
        ),
        "first_45s_sampled_distance_blocks": early_distance,
        "first_45s_supplies_observed": early_supplies,
        "first_45s_state_samples": {name: len(samples) for name, samples in first_45.items()},
        "objectives_observed_by_45s": [item for item, observed in first_items.items() if observed < 45],
        "first_possession_s": first_items,
        "final_objectives": final_items,
        "terminal_server_inventory": terminal_inventory,
        "first_joint_completion_s": joint_time,
        "server_timeouts": len(re.findall(r"lost connection: Timed out", server_log)),
        "protocol_read_errors": len(re.findall(r"^PartialReadError:", agents_log, re.M)),
        "agent_restarts": agents_log.count("Restarting agent..."),
        "api_connection_errors": agents_log.count("APIConnectionError:"),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    args = p.parse_args()
    rows = [summarize(path) for path in sorted(args.root.glob("pair*")) if (path / "events.jsonl").exists()]
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
