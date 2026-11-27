"""Replay the scored crafts, transferred material, prompts, and matched contrasts."""
import argparse
from collections import Counter
from itertools import product
import json
from pathlib import Path
import random
from statistics import mean, median

from run import snapshot
from scenario import LESSONS, SEEDS, SLOT, cases, formulas, trial_spec


def read(path):
    return json.loads(path.read_text())


def need(ok, text):
    if not ok:
        raise ValueError(text)


def prompt(trial, turn, done, past):
    public = trial["public"]
    lines = [f"Turn {turn} of {trial['duration'] // trial['step']}."]
    for slot, shelf in zip("ABCDEFGHI", public["shelves"]):
        lines.append(f"{slot}: " + " ".join(f"{i}={item}" for i, item in enumerate(shelf, 1)))
    for id, row in public["orders"].items():
        label = "Delivered." if id in done else "Open."
        lines.append(f'{id} makes {row["food"]}. Rank sum {row["sum"]}. {label}')
    lines.append("Transferred notes:\n" + trial["knowledge"] if trial["knowledge"] else "Transferred notes: none.")
    lines.append("Your observed tests: " + ("; ".join(past) or "none"))
    return "\n".join(lines)


def replay(folder, case, phase, material, fixture=trial_spec):
    trial = read(folder / "trial.json")
    lane = (trial["positions"]["home"][0] - 64) // 80
    retry = int(folder.name.split("-attempt")[-1]) if "-attempt" in folder.name else 1
    need(trial == fixture(*case, lane, retry, phase, material), f"Scenario mismatch for {folder.name}")
    trace = read(folder / "trace.json")
    start, deadline = trace["start"], trace["deadline"]
    need(start == read(folder / "start.json")["start"] and deadline - start == trial["duration"] * 1000,
         "Wrong measurement window")
    slot = trial.get("slot", SLOT)
    size = len(trial["public"]["shelves"])
    width = len(trial["public"]["shelves"][0])
    need(trace["slot"] == slot and trace["model"] == trial["model"], "Wrong model or token ceiling")
    remaining = {id: {p for p in product(range(1, width+1), repeat=size) if sum(p) == public["sum"]}
                 for id, public in trial["public"]["orders"].items()}
    tests, done, past, seen = [], {}, [], set()
    usage, statuses, outcomes = Counter(), Counter(), Counter()
    reserved = duplicate = eliminated = 0
    for index, row in enumerate(trace["history"]):
        turn = index + 1
        due = start + index * trial["step"] * 1000
        need(row["turn"] == turn and row["due"] == due and due < deadline, "Wrong decision cadence")
        need(row["input"] == prompt(trial, turn, done, past), "Model saw extra or missing information")
        decision, action, outcome = row["decision"], row["action"], row["outcome"]
        need(decision["action"] == action, "Executed action differs from recorded decision")
        need(0 <= decision["reserved"] <= slot, "Slot token budget exceeded")
        reserved += decision["reserved"]
        statuses[decision["status"]] += 1
        outcomes[outcome] += 1
        if "tokens" in decision:
            tokens = decision["tokens"]
            need(tokens["input"] + tokens["output"] == decision["reserved"] and 0 <= tokens["cached"] <= tokens["input"],
                 "Reported tokens are inconsistent")
            usage.update(tokens)
        if outcome not in ("tested", "delivered"):
            need(row["matches"] is None and row["craft"] is None and row["at"] is None, "Unexpected tool feedback")
            continue
        id = action["order"]
        ranks = tuple(action["ranks"])
        order = trial["orders"][id]
        shelf_items = [shelf[i-1] for shelf, i in zip(trial["public"]["shelves"], ranks)]
        hits = sum(i == j for i, j in zip(shelf_items, order["ingredients"]))
        need(row["ingredients"] == shelf_items and row["matches"] == hits and id not in done, "Wrong craft feedback")
        need(due <= row["at"] < deadline, "Physical test outside the trial clock")
        need(row["craft"] == (order["food"] if hits == size else None)
             and outcome == ("delivered" if hits == size else "tested"), "Expected a genuine Minecraft recipe result")
        if hits == size:
            done[id] = {"turn": turn, "seconds": (row["at"] - start) / 1000, "ingredients": shelf_items}
        duplicate += (id, ranks) in seen
        seen.add((id, ranks))
        survivors = {p for p in remaining[id] if sum(i == j for i, j in zip(p, ranks)) == hits}
        need(bool(survivors), "Feedback eliminated the real recipe")
        eliminated += len(remaining[id]) - len(survivors)
        remaining[id] = survivors
        tests.append({"turn": turn, "order": id, "ranks": list(ranks), "hits": hits, "candidates_left": len(survivors)})
        past.append(f'{id} [{",".join(map(str, ranks))}] => {hits}/{size}')
    complete = len(done) == len(trial["orders"])
    duration = trial["duration"]
    max_turns = duration // trial["step"]
    need(complete or len(trace["history"]) == max_turns, "Trial ended before the cutoff")
    need(sum(usage.values()) - usage["cached"] <= reserved <= max_turns * slot, "Team token budget exceeded")
    first = min((row["seconds"] for row in done.values()), default=None)
    elapsed = max(row["seconds"] for row in done.values()) if complete else duration
    need(sorted(done) == trace["done"] and (trace["finish"] is not None) == complete
         and (not complete or (trace["finish"] - start) / 1000 == elapsed), "Incorrect stop record")
    terminal = read(folder / "complete.json")
    raw = (folder / "server-sample.txt").read_text()
    need(raw.count(f'{trial["player"]} joined the game') == 1, "Missing Minecraft join")
    stock = snapshot(raw, trial)
    need(terminal == {"done": sorted(done), "elapsed": elapsed, "stock": stock}
         and stock == {trial["orders"][id]["food"]: 1 for id in done}, "Terminal inventory disagrees with traces")
    need(trial["scripted"] or statuses["completed"] > 0, "Empty model trial")
    if trial["scripted"]:
        need([row["hits"] for row in tests] == [0, size - 1] + [size] * len(trial["orders"]), "Probe failed negative and positive controls")
    return {"seed": case[0], "arm": case[1], "folder": folder.name, "count": len(done), "full": complete,
            "first": first, "first_capped": duration if first is None else first, "elapsed": elapsed,
            "usage": dict(usage), "statuses": dict(statuses), "outcomes": dict(outcomes), "reserved": reserved,
            "tests": len(tests), "duplicates": duplicate, "candidate_eliminations": eliminated}, done, tests


def verify_batch(root, phase, material=None, *, plan=None, manifest=None, fixture=trial_spec):
    plan = cases(phase) if plan is None else plan
    manifest = {"phase": phase, "cases": [list(pair) for pair in plan]} if manifest is None else manifest
    need(read(root / "design.json") == manifest, "Wrong trial manifest")
    folders = {p.parent for p in root.glob("*/complete.json")}
    data = []
    for case in sorted(plan):
        label = "-".join(map(str, case))
        matches = {path for path in folders if path.name == label or path.name.startswith(label + "-attempt")}
        need(len(matches) == 1, f"Expected a single terminal record for {label}")
        folder = matches.pop()
        data.append(replay(folder, case, phase, material or {}, fixture=fixture))
        folders.remove(folder)
    need(not folders, "Unexpected completed runs")
    return data


def training_ledger(teacher):
    return [{"seed": row["seed"], "tests": [[a["order"], a["turn"], a["ranks"], a["hits"],
                                               a["candidates_left"]] for a in tests]}
            for row, _, tests in teacher]


def check_material(material, teacher):
    want = {str(row["seed"]): dict(sorted(done.items())) for row, done, _ in teacher}
    need(material["cards"] == want, "A recipe card is missing or was not earned in teacher logs")
    need(material["synthesis"]["ledger"] == training_ledger(teacher), "Synthesis saw a different training ledger")
    lessons = material["playbook"]
    need(len(lessons) == len(set(lessons)) == 3 and all(item in LESSONS for item in lessons),
         "Playbook has unapproved text or too few recorded lessons")
    evidence = {(row["seed"], test["order"], test["turn"]) for row, _, tests in teacher for test in tests}
    need([row["lesson"] for row in material["evidence"]] == lessons, "Lesson provenance missing")
    for row in material["evidence"]:
        need((row["seed"], row["order"], row["turn"]) in evidence, "Lesson references a turn outside training")
    own = formulas()
    train = {tuple(row["ingredients"]) for seed in SEEDS for row in own["reuse", seed].values()}
    novel = {tuple(row["ingredients"]) for seed in SEEDS for row in own["novel", seed].values()}
    need(len(train) == len(novel) == 40 and not train.intersection(novel), "Training recipes leaked into held-out recipes")


def spread(values):
    return [min(values), max(values)] if values else None


def group(rows):
    counters = {}
    for key in ("usage", "statuses", "outcomes"):
        tally = Counter()
        for row in rows:
            tally.update(row[key])
        counters[key] = dict(tally)
    first = [row["first"] for row in rows if row["first"] is not None]
    finishes = [row["elapsed"] for row in rows if row["full"]]
    return {"n": len(rows), "full": len(finishes), "mean_orders": mean(r["count"] for r in rows),
            "order_range": spread([r["count"] for r in rows]), "first_observed": len(first),
            "first_median": median(first) if first else None, "first_range": spread(first),
            "first_capped_mean": mean(row["first_capped"] for row in rows),
            "finish_median": median(finishes) if finishes else None, "finish_range": spread(finishes),
            "finish_capped_mean": mean(row["elapsed"] for row in rows),
            "tests": sum(row["tests"] for row in rows), "duplicates": sum(row["duplicates"] for row in rows),
            "candidate_eliminations": sum(row["candidate_eliminations"] for row in rows), **counters}


def contrast(values):
    rng = random.Random(24533)
    distribution = sorted(mean(rng.choices(values, k=len(values))) for _ in range(20_000))
    return {"mean": mean(values), "values": values, "interval": [distribution[499], distribution[19_499]]}


def analyze(teacher, students, material):
    teacher_runs = verify_batch(teacher, "teacher")
    check_material(material, teacher_runs)
    data = [row for row, _, _ in [*teacher_runs, *verify_batch(students, "students", material)]]
    lookup = {(row["seed"], row["arm"]): row for row in data}
    contrasts = {}
    for treatment, control in (("reuse_cards", "reuse_solo"), ("novel_playbook", "novel_solo")):
        contrasts[treatment] = {}
        for field in ("count", "first_capped", "elapsed", "tests"):
            contrasts[treatment][field] = contrast([
                round(lookup[seed, treatment][field] - lookup[seed, control][field], 3) for seed in SEEDS])
    return {"groups": {arm: group([r for r in data if r["arm"] == arm]) for arm in sorted({r["arm"] for r in data})},
            "contrasts": contrasts, "recipes_transferred": sum(map(len, material["cards"].values())),
            "playbook": material["playbook"], "trials": data}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--phase", choices=("probe", "calibration", "teacher"))
    args = parser.parse_args()
    if args.phase:
        trial_rows = [row for row, _, _ in verify_batch(args.root, args.phase)]
        print(json.dumps(trial_rows, indent=2, sort_keys=True))
    else:
        report = analyze(args.root / "teacher", args.root / "students", read(args.root / "knowledge.json"))
        print(json.dumps(report, indent=2, sort_keys=True))
