"""Verify all planned live handoff trials and summarize the paired comparison."""

import argparse
from collections import Counter
import hashlib
from itertools import product
import json
from math import comb
from pathlib import Path
from statistics import median

from run import ACTORS, TIMEOUT, evaluation_schedule, metrics, read_events, score, summarize, summarize_pairs, tasks


def read(path):
    return json.loads(path.read_text())


def verify_trial(root, row, task, model, note):
    directory = root / row["directory"]
    result = read(directory / "result.json")
    if any(row.get(key) != value for key, value in result.items()):
        raise ValueError(f"Result record differs from its episode: {directory}")
    if row["status"] not in ("complete", "timeout"):
        raise ValueError(f"Unscoreable assigned episode: {directory}")
    if read(directory / "task.json") != {row["scenario"]: task}:
        raise ValueError(f"Task changed: {directory}")
    for agent in ACTORS:
        profile = read(directory / f"{agent}.json")
        _, marker, carried = profile["conversing"].partition("\nLessons from previous episodes:\n")
        if bool(marker) != bool(note) or carried != note or profile["model"]["model"] != model:
            raise ValueError(f"Wrong treatment or model: {directory} / {agent}")
    events = read_events(directory / "events.jsonl")
    start = result["started_ms"]
    deadline = start + TIMEOUT * 1000
    replay = score(events, start, TIMEOUT, deadline)
    if any(result[key] != value for key, value in replay.items()):
        raise ValueError(f"Inventory replay disagrees with recorded outcome: {directory}")
    end = start + round(result["completion_seconds"] * 1000) if result["status"] == "complete" else deadline
    runtime = metrics(events, start, end)
    if not runtime["model_calls"] or any(result.get(key) != value for key, value in runtime.items()):
        raise ValueError(f"Model and event telemetry mismatch: {directory}")
    if {e["model"] for e in events if e["type"] == "model_call" and start <= e["time_ms"] <= end} != {model}:
        raise ValueError(f"Provider returned unexpected model: {directory}")
    server = (directory / "server.log").read_text(errors="replace")
    if "Done (" not in server or any(f"{name} joined the game" not in server for name in ACTORS):
        raise ValueError(f"Missing server or joins: {directory}")
    return {**row, "capped_seconds": result["completion_seconds"] if result["status"] == "complete" else TIMEOUT}


def attempts(directory):
    return Counter(read(path / "result.json")["status"] if (path / "result.json").is_file() else "interrupted"
                   for path in directory.iterdir() if path.is_dir())


def report(evidence):
    training = evidence / "practice"
    manifest = read(training / "manifest.json")
    note = (training / "frozen_note.md").read_text().strip()
    digest = hashlib.sha256(note.encode()).hexdigest()
    suite, model = manifest["scenarios"], manifest["model"]
    schedule = [tuple(t) for t in manifest["evaluation_order"]]
    if manifest["mode"] != "practice" or suite != tasks() or not 0 < len(note.split()) <= 250:
        raise ValueError("Invalid practice manifest or frozen note")
    if schedule != evaluation_schedule(suite["held_out"], manifest["repetitions"], manifest["seed"]):
        raise ValueError("Evaluation order differs from the planned seed")
    training_rows = read(training / "practice.json")
    expected = [(s, i) for s in suite["practice"] for i in (1, 2)]
    if [(r["scenario"], r["repetition"]) for r in training_rows] != expected:
        raise ValueError("Incomplete practice sequence")
    last_note = ""
    summary_usage = []
    for row in training_rows:
        verify_trial(training, row, suite["practice"][row["scenario"]], model, "")
        directory = training / row["directory"]
        last_note = (directory / "updated_note.md").read_text().strip()
        usage = read(directory / "summary_usage.json")
        if not 0 < len(last_note.split()) <= 250 or usage["model"] != model:
            raise ValueError(f"Invalid practice note update: {directory}")
        summary_usage.append(usage["usage"])
    if last_note != note:
        raise ValueError("Frozen note does not match the last practice update")

    by_key = {}
    all_attempts = attempts(training)
    workers = sorted(evidence.glob("eval-*"))
    for worker, source in enumerate(workers):
        setup = read(source / "manifest.json")
        if setup != {**manifest, "mode": "evaluation", "worker": worker,
                     "workers": len(workers), "frozen_note_sha256": digest}:
            raise ValueError(f"Worker manifest differs from practice: {source}")
        all_attempts.update(attempts(source))
        for row in read(source / "evaluation.json"):
            key = (row["scenario"], row["repetition"], row["arm"])
            if key in by_key or key not in schedule or schedule.index(key) // 2 % setup["workers"] != worker:
                raise ValueError(f"Duplicate or misplaced assignment: {key}")
            by_key[key] = verify_trial(source, row, suite["held_out"][row["scenario"]], model,
                                       note if row["arm"] == "learned" else "")
    if set(by_key) != set(schedule):
        raise ValueError(f"Missing designated trials: {set(schedule) - set(by_key)}")
    rows = [by_key[key] for key in schedule]
    paired = summarize_pairs(rows, schedule)
    discordant = paired["overall"]["learned_only"] + paired["overall"]["baseline_only"]
    smaller = min(paired["overall"]["learned_only"], paired["overall"]["baseline_only"])
    exact_p = min(1.0, 2 * sum(comb(discordant, i) for i in range(smaller + 1)) / 2 ** discordant)
    timing_pairs = []
    for scenario, repetition in dict.fromkeys((s, r) for s, r, _ in schedule):
        control = by_key[scenario, repetition, "baseline"]["capped_seconds"]
        treatment = by_key[scenario, repetition, "learned"]["capped_seconds"]
        timing_pairs.append({"scenario": scenario, "repetition": repetition,
                             "baseline_s": control, "learned_s": treatment,
                             "learned_minus_baseline_s": round(treatment - control, 3)})
    differences = [round(row["learned_minus_baseline_s"] * 1000) for row in timing_pairs]
    # This is a secondary reference for a sharp no-effect null within matched pairs.
    timing_p = None
    if len(differences) <= 20:
        observed = abs(sum(differences))
        timing_p = sum(abs(sum(value * sign for value, sign in zip(differences, signs))) >= observed
                       for signs in product((-1, 1), repeat=len(differences))) / 2 ** len(differences)
    arms = {}
    for arm in ("baseline", "learned"):
        cell = [r for r in rows if r["arm"] == arm]
        times = [r["completion_seconds"] for r in cell if r["status"] == "complete"]
        arms[arm] = {"n": len(cell), "completed": len(times), "timeouts": len(cell) - len(times),
                     "completion_times_s": sorted(times), "median_completed_s": median(times) if times else None}
    return {
        "manifest": manifest, "frozen_note_sha256": digest, "note_words": len(note.split()),
        "practice": training_rows, "note_update_usage": summary_usage, "evaluation": rows,
        "arms": arms, "by_scenario": summarize(rows, schedule), "paired": paired,
        "paired_completion_exact_p": exact_p, "timing_pairs": timing_pairs,
        "paired_timing_exact_p": timing_p, "attempts": dict(all_attempts),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    print(json.dumps(report(args.evidence), indent=2))


if __name__ == "__main__":
    main()
