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


def checkpoint_monitor(work, scenario, checkpoint):
    observe = monitor(scenario)
    saved = False

    def check(server, server_log, bot_log, start, deadline):
        nonlocal saved
        due = start + checkpoint * 1000
        if not saved and arena.stamp() >= due:
            offset = server_log.stat().st_size
            asked = arena.stamp()
            arena.send(server, [*(f"data get entity {name} Inventory" for name in arena.NAMES),
                                "say STUDY_CHECKPOINT_END"])
            arena.wait_for(server, server_log, lambda s: "[Server] STUDY_CHECKPOINT_END" in s, 4)
            inventory = observed_inventory(server_log, offset)
            (work / "checkpoint.json").write_text(json.dumps(
                {"dueMs": due, "requestedMs": asked, "observedMs": arena.stamp(),
                 "inventory": {k: sorted(v) for k, v in inventory.items()}}, indent=2))
            saved = True
        return observe(server, server_log, bot_log, start, deadline)

    return check


def main():
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
    if args.probe:
        blocks = [{"number": 0, "scenario": "metalwork", "mirror": 1, "order": ["alternating"]}]
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
            duration = 65 if args.probe else DURATION
            windows = [[0, 12], [30, 50]] if args.probe else SCHEDULES[schedule]
            times = ", ".join(f"{a}–{b}" for a, b in windows)
            briefing = (f"Bot chat is open during these seconds after the episode starts: {times}. "
                        "Use open windows to exchange objective cards and coordinate handoffs. "
                        "When chat is closed, explore, gather, craft, or physically transfer items.")
            base_port = 100 + args.worker * 20
            arena.run(args.out, label, 0, duration, block["mirror"], 55916 + base_port,
                      8080 + base_port, False, study=scenario, chat_windows=windows,
                      configure_trial=lambda work, d, s: configure(work, d, s, scenario, "partner", briefing),
                      observe=checkpoint_monitor(work, scenario, 30 if args.probe else CHECKPOINT))
            temp = marker.with_suffix(".tmp")
            temp.write_text(json.dumps({"block": block, "cell": {"info": "partner", "delay": 0},
                                        "schedule": schedule, "probe": args.probe}))
            temp.rename(marker)


if __name__ == "__main__":
    main()
