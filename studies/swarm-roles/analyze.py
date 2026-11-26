"""Verify assignments, game actions, server inventories, and pooled outcomes."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
from statistics import mean
from run import MODES, design, fixture, kitchen


def read(path):
    return json.loads(path.read_text())


def check(ok, label, reason):
    if not ok:
        raise ValueError(f"{label}: {reason}")


def instructions_wait(action):
    phrase = " ".join((action["why"], action["say"])).casefold()
    return bool(re.search(r"\b(?:await(?:ing)?|wait(?:ing)?(?: for)?|need|no new|until)\b.{0,35}\b"
                          r"(?:assignment|instruction|direction|reassign|orchestrat|assigned work|assigned task)", phrase))


def expected_update(mode, leader, owners, attempts, aliases):
    if mode != "orchestrator":
        return None
    actor = next(row for row in attempts if row["player"] == leader)
    action = actor["decision"]["action"]
    move = action["assign"] if action else None
    if move is None:
        return None
    recipe, name = move["recipe"], move["to"]
    recipient = next((alias for alias in aliases if alias.casefold() == name.casefold()), None)
    if recipe not in owners or recipient is None:
        return {"status": "invalid", "recipe": recipe, "to": name}
    if any(recipe in row["held"] for row in attempts):
        return {"status": "already_done", "recipe": recipe, "to": recipient}
    previous = owners[recipe]
    return {"status": "unchanged" if previous == recipient else "reassigned",
            "recipe": recipe, "from": previous, "to": recipient}


def audit(folder, case, plan):
    label = folder.name
    trial, trace, result = [read(folder / f) for f in ("trial.json", "trace.json", "complete.json")]
    lane = (trial["stations"][0]["home"][0] - 52) // 86
    attempt = int(label.rsplit("-attempt", 1)[-1]) if "-attempt" in label else 1
    check(trial == fixture(*case, plan["duration"], plan["step"], lane, attempt), label, "fixture")
    mode, leader, aliases = trial["mode"], trial["leader"], trial["aliases"]
    start = trace["start"]
    check(trace["model"] == "gpt-6-luna" and trace["slot_budget"] == 960, label, "provider or ceiling")
    check(trace["deadline"] - start == plan["duration"] * 1000, label, "deadline")
    sample = (folder / "server-sample.txt").read_text()
    check(all(f"{player} joined the game" in sample for player in trial["players"]), label, "four bot joins")
    final = {alias: kitchen.inventory(sample, player) for alias, player in zip(aliases, trial["players"])}
    check(final == result["inventories"], label, "server inventory")
    team = {a: {"held": [], "intent": "", "say": ""} for a in aliases}
    owners = trial["initial_owners"].copy()
    inv = {a: {} for a in aliases}
    kits = {a: set() for a in aliases}
    crafts = {a: set() for a in aliases}
    totals = Counter()
    changes = []
    for index, turn in enumerate(trace["rounds"]):
        check(turn["turn"] == index + 1 and turn["due"] == start + index * plan["step"] * 1000,
              label, "turn sequence")
        check(turn["owners"] == owners and turn["team"] == team, label, "unavailable information or stale roster")
        check([r["player"] for r in turn["attempts"]] == aliases, label, "each actor gets one attempt")
        held_before = set().union(*(set(v["held"]) for v in team.values()))
        totals["all_wait_turns_while_unfinished"] += len(held_before) < len(trial["ids"]) and all(
            (r["decision"]["action"] or {}).get("act") == "wait" for r in turn["attempts"])
        for row in turn["attempts"]:
            alias, outcome, decision = row["player"], row["outcome"], row["decision"]
            content = row["input"].split("\nAssignments: ", 1)[1]
            raw_owners, content = content.split("\nTeam state from the last turn: ", 1)
            raw_team = content.split("\nYour collected kits: ", 1)[0]
            check(json.loads(raw_owners) == owners and json.loads(raw_team) == team, label, "prompt visibility")
            totals["slots"] += 1
            totals["reserved_tokens"] += decision["reserved"]
            action = decision["action"]
            if "tokens" in decision:
                check(sum(decision["tokens"]) == decision["reserved"] <= 960, label, "token accounting")
                totals["measured_tokens"] += decision["reserved"]
                totals["responses"] += 1
            else:
                check(action is None and decision["reserved"] in (0, 960), label, "failed response")
                totals["provider_failures"] += 1
                totals[decision["status"]] += 1
            totals[outcome] += 1
            if action:
                recipe = action["recipe"]
                if action.get("assign") and alias != leader:
                    totals["nonauthority_assignment_attempts"] += 1
                if action["act"] == "wait" and len(held_before) < len(trial["ids"]):
                    totals["waiting_while_unfinished"] += 1
                    totals["waiting_for_instruction"] += instructions_wait(action)
                if action["act"] in ("collect", "craft") and recipe in held_before:
                    totals["attempt_after_reported_completion"] += 1
                if outcome == "collected":
                    check(action["act"] == "collect" and recipe in trial["ids"] and recipe not in kits[alias],
                          label, "kit provenance")
                    kits[alias].add(recipe)
                if outcome == "crafted":
                    check(action["act"] == "craft" and recipe in kits[alias] and recipe not in crafts[alias]
                          and row["inventory"].get(recipe, 0) > inv[alias].get(recipe, 0), label, "craft provenance")
                    crafts[alias].add(recipe)
                    totals["leader_crafts"] += alias == leader
                    totals["craft_outside_assignment"] += recipe in owners and owners[recipe] != alias
                    totals["craft_after_reported_completion"] += recipe in held_before
            inv[alias] = row["inventory"]
            check(row["held"] == sorted(recipe for recipe in crafts[alias] if inv[alias].get(recipe)),
                  label, "client progress")
        update = expected_update(mode, leader, owners, turn["attempts"], aliases)
        check(turn["update"] == update, label, "unauthorized or missing roster update")
        if update:
            totals[update["status"] + "_assignment"] += 1
            if update["status"] == "reassigned":
                changes.append({**update, "turn": index + 1})
                owners[update["recipe"]] = update["to"]
        team = {r["player"]: {"held": r["held"], "intent": (r["decision"]["action"] or {}).get("recipe", ""),
                             "say": (r["decision"]["action"] or {}).get("say", "")} for r in turn["attempts"]}
        check(turn["goals"] == len(set().union(*(set(r["held"]) for r in team.values()))), label, "progress score")
    horizon = plan["duration"] // plan["step"]
    check(0 < totals["slots"] <= horizon * len(aliases)
          and totals["reserved_tokens"] <= horizon * len(aliases) * 960, label, "episode budget")
    check({k: sorted(v) for k, v in crafts.items()} == {k: sorted(v) for k, v in trace["crafted"].items()},
          label, "terminal craft ledger")
    output = sorted({recipe for alias in aliases for recipe in crafts[alias] if final[alias].get(recipe)})
    check(output == result["verified"] and result["full"] == (len(output) == len(trial["ids"])),
          label, "terminal goal score")
    elapsed = (trace["finish"] - start) / 1000 if trace["finish"] else plan["duration"]
    check(result["elapsed"] == elapsed and 0 < elapsed <= plan["duration"]
          and (trace["finish"] is None or result["full"]), label, "elapsed time")
    craft_union = set().union(*crafts.values())
    kit_union = set().union(*kits.values())
    return {"trial": label, "seed": case[0], "mode": mode, "leader": leader,
            "elapsed": elapsed, "goals": len(output), "full": result["full"],
            "duplicate_crafts": sum(map(len, crafts.values())) - len(craft_union),
            "duplicate_kits": sum(map(len, kits.values())) - len(kit_union),
            "reassignments": changes, "client_match": final == trace["clients"],
            "verified": output, "crafts_by_player": {k: sorted(v) for k, v in crafts.items()},
            "counts": dict(totals)}


def group(rows):
    spent = sum(r["elapsed"] for r in rows)
    goals = sum(r["goals"] for r in rows)
    return {"trials": len(rows), "completed": sum(r["full"] for r in rows), "goals": goals,
            "mean_goals": mean(r["goals"] for r in rows), "mean_elapsed": spent / len(rows),
            "seconds_per_goal": spent / goals if goals else None,
            "mean_duplicate_crafts": mean(r["duplicate_crafts"] for r in rows),
            "mean_duplicate_kits": mean(r["duplicate_kits"] for r in rows),
            "counts": dict(sum((Counter(r["counts"]) for r in rows), Counter()))}


def analyze(root, partial, probe):
    plan = read(root / "design.json")
    if not probe:
        check(plan == {"duration": 360, "step": 10, "cases": list(map(list, design()))},
              "design", "manifest differs")
    rows, pending = [], []
    for case in plan["cases"]:
        tag = "-".join(map(str, case))
        candidates = [root / tag, *root.glob(tag + "-attempt*")]
        terminal = [folder for folder in candidates if (folder / "complete.json").is_file()]
        if not terminal and partial:
            pending.append(tag)
            continue
        check(len(terminal) == 1, tag, "exactly one completed trial required")
        rows.append(audit(terminal[0], case, plan))
    groups = {mode: group(matching) for mode in MODES if (matching := [r for r in rows if r["mode"] == mode])}
    matched = {(r["seed"], r["mode"]): r for r in rows}
    contrasts = {}
    for left, right in (("fixed", "swarm"), ("orchestrator", "swarm"), ("orchestrator", "fixed")):
        pairs = []
        seeds = {r["seed"] for r in rows if r["mode"] == left}
        for seed in sorted(seeds):
            if (seed, right) not in matched:
                continue
            a, b = matched[(seed, left)], matched[(seed, right)]
            pairs.append({"seed": seed, "elapsed_difference": a["elapsed"] - b["elapsed"],
                          "goal_difference": a["goals"] - b["goals"],
                          "duplicate_craft_difference": a["duplicate_crafts"] - b["duplicate_crafts"]})
        contrasts[f"{left}_minus_{right}"] = pairs
    return {"verified_runs": len(rows), "pending": pending, "groups": groups, "contrasts": contrasts, "trials": rows}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("--partial", action="store_true")
    p.add_argument("--probe", action="store_true")
    args = p.parse_args()
    print(json.dumps(analyze(args.root, args.partial, args.probe), indent=2))


if __name__ == "__main__":
    main()
