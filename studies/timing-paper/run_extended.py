"""Give the same MineCollab tasks a twelve-minute deadline."""
from run_long import main

DURATION = 720
CHECKPOINTS = {t: f"checkpoint-{t}.json" for t in (180, 360)}
SCHEDULES = {
    "always": [[0, DURATION]],
    "two_blocks": [[t, t + 60] for t in range(0, DURATION, 180)],
    "alternating": [[t, t + 20] for t in range(0, DURATION, 60)],
}


if __name__ == "__main__":
    main(duration=DURATION, schedules=SCHEDULES, checkpoints=CHECKPOINTS,
         probe_checkpoints={1: CHECKPOINTS[180], 3: CHECKPOINTS[360]})
