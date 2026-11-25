"""Export study evidence without worlds, credentials, or full prompt logs."""
import argparse
import json
from pathlib import Path
import re
import shutil

FILES = ("complete.json", "start.json", "finish.json", "task.json", "events.jsonl",
         "terminal-inventory-request.txt", "minecraft.log")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("runs", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--partial", action="store_true")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    attempts = []
    for source in sorted(args.runs.glob("b[0-9][0-9]-*")):
        marker = source / "complete.json"
        if not marker.exists():
            if not args.partial:
                attempts.append({"name": source.name, "status": "incomplete", "reason": "no completion marker"})
            continue
        if json.loads(marker.read_text())["probe"]:
            continue
        dest = args.out / source.name
        dest.mkdir(exist_ok=True)
        for name in FILES:
            shutil.copyfile(source / name, dest / name)
        for name in ("checkpoint.json", "checkpoint-180.json", "checkpoint-360.json"):
            if (source / name).exists():
                shutil.copyfile(source / name, dest / name)
        raw = (source / "agents.log").read_text(errors="replace")
        restart_lines = [line for line in raw.splitlines() if "Agent process exited" in line]
        health = {"restarts": raw.count("Restarting agent..."),
                  "protocol_errors": len(re.findall(r"^PartialReadError:", raw, re.MULTILINE)),
                  "process_exit_lines": restart_lines}
        (dest / "runtime.json").write_text(json.dumps(health, indent=2) + "\n")
        attempts.append({"name": source.name, "status": "complete"})
    (args.out / "attempts.json").write_text(json.dumps(attempts, indent=2) + "\n")


if __name__ == "__main__":
    main()
