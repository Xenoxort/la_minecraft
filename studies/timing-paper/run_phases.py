"""Compare training-free chat schedules on the partner-card task."""
import argparse
import json
from pathlib import Path

from run_study import DURATION, arena, configure, monitor

SCENARIOS = json.loads(Path(__file__).with_name("phase_scenarios.json").read_text())

SCHEDULES = {
    "always": [[0, 180]],
    "upfront": [[0, 60]],
    "alternating": [[0, 20], [60, 80], [120, 140]],
}
BLOCKS = [
    {"number": 1, "scenario": "bakery", "mirror": 1, "order": ["alternating", "upfront", "always"]},
    {"number": 2, "scenario": "harvest", "mirror": -1, "order": ["upfront", "always", "alternating"]},
    {"number": 3, "scenario": "dyes", "mirror": 1, "order": ["always", "alternating", "upfront"]},
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--worker", type=int, choices=(0, 1), default=0)
    p.add_argument("--probe", action="store_true")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    blocks = BLOCKS[args.worker::2]
    if args.probe:
        blocks = [{"number": 0, "scenario": "bakery", "mirror": 1, "order": ["alternating"]}]
    for block in blocks:
        scenario = SCENARIOS[block["scenario"]]
        for schedule in block["order"]:
            prefix = f"b{block['number']:02d}-{block['scenario']}-{schedule}"
            label = prefix
            attempt = 1
            while (args.out / label).exists() and not (args.out / label / "complete.json").exists():
                attempt += 1
                label = f"{prefix}-attempt{attempt}"
            marker = args.out / label / "complete.json"
            if marker.exists():
                continue
            windows = SCHEDULES[schedule] if not args.probe else [[0, 10], [25, 45]]
            duration = DURATION if not args.probe else 45
            times = ", ".join(f"{a}–{b}" for a, b in windows)
            briefing = (
                f"Bot chat is open during these seconds after the episode starts: {times}. "
                "Use open windows to ask for or pass along objective information. "
                "When chat is closed, explore, gather, and craft on your own. "
            )
            base_port = 60 + args.worker * 20
            arena.run(args.out, label, 0, duration, block["mirror"], 55916 + base_port,
                      8080 + base_port, False, study=scenario, chat_windows=windows,
                      configure_trial=lambda work, d, s: configure(work, d, s, scenario, "partner", briefing),
                      observe=monitor(scenario))
            temp = marker.with_suffix(".tmp")
            temp.write_text(json.dumps({"block": block, "cell": {"info": "partner", "delay": 0},
                                        "schedule": schedule, "probe": args.probe}))
            temp.rename(marker)


if __name__ == "__main__":
    main()
