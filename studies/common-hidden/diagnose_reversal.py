"""Compare action and information bottlenecks in two recorded Minecraft studies."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
from statistics import mean
from tarfile import open as open_tar

SCHEDULES = ("always", "blocks", "alternating")
COMMAND = re.compile(r"!([A-Za-z][A-Za-z0-9]*)")
CARD = re.compile(r"(\w+) L=(\d+|\?) R=(\d+|\?)")
PHYSICAL = {"craftRecipe", "takeFromChest", "givePlayer", "collectBlocks", "goToCoordinates",
            "goToPlayer", "moveAway", "searchForBlock", "viewChest"}


def read(path):
    return json.loads(path.read_text())


def cancellations(archive, label, start, stop):
    response = None
    generated = ""
    changes = Counter()
    commands = Counter()
    with archive.extractfile(f"{label}/agents.log") as log:
        for row in log:
            line = row.decode(errors="replace").rstrip()
            if line.startswith("STUDY "):
                event = json.loads(line[6:])
                if event["event"] == "model_response":
                    response = event["ms"]
                    generated = ""
            elif line.startswith("Generated response: "):
                generated = line.removeprefix("Generated response: ")
            elif "received new message while generating, discarding old response." in line:
                if response is not None and start <= response <= stop:
                    changes["discarded"] += 1
                    found = set(COMMAND.findall(generated))
                    changes["physical_or_world_query"] += bool(PHYSICAL & found)
                    commands.update(found)
    return {**changes, "commands": dict(commands)}


def old_study(study, raw):
    episodes = []
    with open_tar(raw, "r:gz") as log:
        for result in read(study / "long-results.json")["episodes"]:
            episode = result["episode"]
            folder = study / "data" / "long" / episode
            start = read(folder / "start.json")["startMs"]
            end = min(start + 360_000, read(folder / "finish.json")["endMs"])
            drops = cancellations(log, episode, start, end)
            episodes.append({"episode": episode, "scenario": result["scenario"],
                             "schedule": result["schedule"], "goals": result["terminal_objectives"],
                             "time": result["capped_360_s"], "model_responses": result["model_responses"],
                             "drops": drops})
    subsets = {}
    for removed in ((), ("dyes",), ("dyes", "masonry")):
        by_schedule = {}
        for schedule in ("always", "two_blocks", "alternating"):
            subset = [x for x in episodes if x["schedule"] == schedule and x["scenario"] not in removed]
            goals = sum(x["goals"] for x in subset)
            elapsed = sum(x["time"] for x in subset)
            responses = sum(x["model_responses"] for x in subset)
            discarded = sum(x["drops"].get("discarded", 0) for x in subset)
            by_schedule[schedule] = {"episodes": len(subset), "goals": goals, "seconds": elapsed,
                                     "seconds_per_goal": elapsed / goals, "responses": responses,
                                     "discarded": discarded, "discarded_fraction": discarded / responses,
                                     "discarded_with_world_action": sum(
                                         x["drops"].get("physical_or_world_query", 0) for x in subset)}
        subsets["without_" + "_".join(removed) if removed else "all"] = by_schedule
    return {"episodes": episodes, "comparisons": subsets}


def goal_pipeline(folder):
    trial = read(folder / "trial.json")
    trace = read(folder / "trace.json")
    result = read(folder / "complete.json")
    access, collect, craft = {}, {}, {}
    count = Counter()
    for turn in trace["rounds"]:
        count["open_rounds"] += turn["open"]
        for attempt in turn["attempts"]:
            actor = attempt["player"]
            cards = attempt["input"].split("\nCards: ", 1)[1].split(".\nItems you crafted", 1)[0]
            complete_cards = {recipe for recipe, left, right in CARD.findall(cards) if "?" not in (left, right)}
            for recipe in sorted(complete_cards):
                access.setdefault(recipe, {"round": turn["round"], "actor": actor})
            outcome = attempt["outcome"]
            count["slots"] += 1
            count[outcome] += 1
            if outcome.startswith("collected_"):
                collect.setdefault(outcome.removeprefix("collected_"), {"round": turn["round"], "actor": actor})
            if outcome.startswith("crafted_"):
                craft.setdefault(outcome.removeprefix("crafted_"), {"round": turn["round"], "actor": actor})
    final = set(result["goals"])
    if not final <= set(craft) <= set(collect) <= set(access):
        raise ValueError(f"{folder.name}: inconsistent recorded action and recipe stages")
    return {"episode": folder.name, "mode": trial["mode"], "schedule": trial["schedule"],
            "candidates": len(trial["ids"]), "access": access, "collection": collect, "craft": craft,
            "terminal": sorted(final), "counts": dict(count)}


def new_study(root):
    records = [goal_pipeline(p.parent) for p in sorted(root.glob("*/complete.json"))]
    groups = {}
    for mode in ("public", "split", "hidden"):
        for schedule in SCHEDULES:
            rows = [r for r in records if (r["mode"], r["schedule"]) == (mode, schedule)]
            if len(rows) != 10:
                raise ValueError(f"{mode}-{schedule}: expected ten episodes, found {len(rows)}")
            totals = Counter()
            for row in rows:
                totals.update(row["counts"])
            groups[f"{mode}-{schedule}"] = {
                "recipes": sum(r["candidates"] for r in rows),
                **{stage: sum(len(r[stage]) for r in rows)
                   for stage in ("access", "collection", "craft", "terminal")},
                "mean_open_rounds": mean(r["counts"]["open_rounds"] for r in rows),
                "exploring_missing_room": totals["no_such_room"],
                "episodes_with_missing_room": sum(r["counts"].get("no_such_room", 0) > 0 for r in rows),
                "locked_cupboard": totals["cupboard_locked"],
                "slots": totals["slots"],
            }
    return {"groups": groups, "episodes": records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("legacy_study", type=Path, help="Folder containing long-results.json and data/long")
    parser.add_argument("legacy_logs", type=Path, help="Original raw-logs.tar.gz")
    parser.add_argument("shared_trials", type=Path, help="Extracted evidence folder")
    args = parser.parse_args()
    result = {"assigned": old_study(args.legacy_study, args.legacy_logs),
              "shared": new_study(args.shared_trials)}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
