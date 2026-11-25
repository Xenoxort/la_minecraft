"""Run matched six-minute MineCollab chat policies."""
import argparse
import json
from pathlib import Path
import random

from run_study import arena, configure, monitor, observed_inventory

SCENARIOS = json.loads(Path(__file__).with_name("long_scenarios.json").read_text())
DURATION = 360
CHECKPOINT = 180
SCHEDULES = {
    "always": [[0, DURATION]],
    "two_blocks": [[0, 60], [180, 240]],
    "alternating": [[t, t + 20] for t in range(0, DURATION, 60)],
}


def design():
    rng = random.Random(904307)
    cases = list(SCENARIOS)
    rng.shuffle(cases)
    orders = [tuple(SCHEDULES), ("two_blocks", "alternating", "always"),
              ("alternating", "always", "two_blocks")]
    base = orders + [tuple(reversed(order)) for order in orders]
    rng.shuffle(base)
    return [{"number": i + 1, "scenario": name, "mirror": (-1) ** i, "order": list(base[i])}
            for i, name in enumerate(cases)]


def checkpoint_monitor(work, scenario, checkpoints):
    observe = monitor(scenario)
    pending = iter(sorted(checkpoints.items()))
    next_checkpoint = next(pending, None)

    def check(server, server_log, bot_log, start, deadline):
        nonlocal next_checkpoint
        if next_checkpoint and arena.stamp() >= start + next_checkpoint[0] * 1000:
            checkpoint, filename = next_checkpoint
            due = start + checkpoint * 1000
            offset = server_log.stat().st_size
            asked = arena.stamp()
            marker = f"STUDY_CHECKPOINT_{checkpoint}_END"
            arena.send(server, [*(f"data get entity {name} Inventory" for name in arena.NAMES),
                                f"say {marker}"])
            arena.wait_for(server, server_log, lambda s: f"[Server] {marker}" in s, 4)
            inventory = observed_inventory(server_log, offset)
            if set(inventory) != set(arena.NAMES):
                raise RuntimeError(f"Checkpoint at {checkpoint}s lacks an agent inventory: {work}")
            (work / filename).write_text(json.dumps(
                {"dueMs": due, "requestedMs": asked, "observedMs": arena.stamp(),
                 "inventory": {k: sorted(v) for k, v in inventory.items()}}, indent=2))
            next_checkpoint = next(pending, None)
        return observe(server, server_log, bot_log, start, deadline)

    return check


def main(*, duration=DURATION, schedules=None, checkpoints=None, probe_checkpoints=None):
    if schedules is None:
        schedules = SCHEDULES
    if checkpoints is None:
        checkpoints = {CHECKPOINT: "checkpoint.json"}
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--worker", type=int, choices=range(3), default=0)
    p.add_argument("--probe", action="store_true")
    p.add_argument("--design-only", action="store_true")
    args = p.parse_args()
    if args.design_only:
        print(json.dumps(design(), indent=2))
        return
    args.out.mkdir(parents=True, exist_ok=True)
    blocks = design()[args.worker::3]
    trial_duration = duration
    if args.probe:
        blocks = [{"number": 0, "scenario": "metalwork", "mirror": 1, "order": ["alternating"]}]
        trial_duration = 65
        checkpoints = probe_checkpoints if probe_checkpoints is not None else {30: "checkpoint.json"}
    for block in blocks:
        scenario = SCENARIOS[block["scenario"]]
        for schedule in block["order"]:
            prefix = f"b{block['number']:02d}-{block['scenario']}-{schedule}"
            label = prefix
            attempt = 1
            while (args.out / label).exists() and not (args.out / label / "complete.json").exists():
                attempt += 1
                label = f"{prefix}-attempt{attempt}"
            work = args.out / label
            marker = work / "complete.json"
            if marker.exists():
                continue
            windows = [[0, 12], [30, 50]] if args.probe else schedules[schedule]
            times = ", ".join(f"{a}–{b}" for a, b in windows)
            briefing = (f"Bot chat is open during these seconds after the episode starts: {times}. "
                        "Use open windows to exchange objective cards and coordinate handoffs. "
                        "When chat is closed, explore, gather, craft, or physically transfer items.")
            base_port = 100 + args.worker * 20
            arena.run(args.out, label, 0, trial_duration, block["mirror"], 55916 + base_port,
                      8080 + base_port, False, study=scenario, chat_windows=windows,
                      configure_trial=lambda work, d, s: configure(work, d, s, scenario, "partner", briefing),
                      observe=checkpoint_monitor(work, scenario, checkpoints))
            temp = marker.with_suffix(".tmp")
            temp.write_text(json.dumps({"block": block, "cell": {"info": "partner", "delay": 0},
                                        "schedule": schedule, "probe": args.probe}))
            temp.rename(marker)


if __name__ == "__main__":
    main()
