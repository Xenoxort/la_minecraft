"""Run a camera-enabled demonstration outside the scored MineCollab cohorts."""
import argparse
from pathlib import Path

from run_long import SCENARIOS
from run_study import arena, configure, monitor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("schedule", choices=("always", "alternating"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    duration = 240
    scenario = SCENARIOS["harvest"]
    windows = ([[0, duration]] if args.schedule == "always" else
               [[t, t + 20] for t in range(0, duration, 60)])
    brief = ("Chat is always open." if args.schedule == "always" else
             "Chat is open for the first 20 seconds of each minute. When it is closed, work independently.")
    arena.run(args.out, args.schedule, 0, duration, 1, 55916, 8080, True,
              study=scenario, chat_windows=windows,
              configure_trial=lambda work, delay, deadline:
              configure(work, delay, deadline, scenario, "partner", brief),
              observe=monitor(scenario))


if __name__ == "__main__":
    main()
