"""Verify and report the common-goal and hidden-recipe Minecraft episodes."""
import argparse
from collections import Counter
from itertools import product
from math import fmod
import json
from pathlib import Path
from statistics import mean

from run import MODES, SCHEDULES, SEEDS, fixture, inventory


def read(path):
    return json.loads(path.read_text())


def check(ok, label, detail):
    if not ok:
        raise ValueError(f"{label}: {detail}")


def gate(schedule, seconds):
    if schedule == "always":
        return True
    if schedule == "blocks":
        return seconds < 60 or 180 <= seconds < 240
    return fmod(seconds, 60) < 20


def audit(folder, case):
    trial, trace, result = (read(folder / file) for file in ("trial.json", "trace.json", "complete.json"))
    label = folder.name
    lane = (trial["stations"][0]["home"][0] - 64) // 80
    attempt = int(label.split("-attempt")[1]) if "-attempt" in label else 1
    check(trial == fixture(*case, trial["duration"], trial["step"], lane, attempt),
          label, "condition, ingredient stock or map identity")
    log = (folder / "server-sample.txt").read_text()
    names = ("Andy", "Jill")
    check(all(f"{name} joined the game" in log for name in trial["players"]), label, "missing bot join")
    final = {alias: inventory(log, player) for alias, player in zip(names, trial["players"])}
    check(final == result["inventories"], label, "terminal server inventory differs")
    check(trace["model"] == "gpt-6-luna" and trace["slot_budget"] == 960, label, "model or token cap")
    check(trace["deadline"] - trace["start"] == trial["duration"] * 1000, label, "deadline")
    cards = trial["cards"]
    fields = ("left", "right")
    initial = {id: {f: cards[id][f] for f in fields} for id in trial["seeded"]}
    known = [{id: c.copy() for id, c in initial.items()} if trial["mode"] != "split"
             else {id: {fields[i]: c[fields[i]]} for id, c in initial.items()} for i in range(2)]
    peer = [{}, {}]
    queued = [[], []]
    previous = [None, None]
    crafts, discoveries, visits, kits = ([set(), set()] for _ in range(4))
    process = Counter()
    stages = []
    for index, turn in enumerate(trace["rounds"]):
        elapsed = index * trial["step"]
        check(turn["round"] == index + 1 and turn["at"] == trace["start"] + elapsed * 1000, label, "round clock")
        actual = (turn["relayAt"] - trace["start"]) / 1000
        if actual < 0:
            check(index == 0 and actual >= -0.005 and all(
                not (item["id"] or item["goals"] or item["intent"] or item["message"])
                for item in turn["deliveries"]), label, "early relay exposed peer information")
        scheduled_open = gate(trial["schedule"], elapsed)
        allowed = scheduled_open and gate(trial["schedule"], actual)
        process["scheduled_open_rounds"] += scheduled_open
        process["missed_open_rounds"] += scheduled_open and not allowed
        check(turn["open"] == allowed and len(turn["deliveries"]) == int(allowed) * 2
              and len(turn["attempts"]) == 2, label, "chat gate or participant count")
        for j, event in enumerate(turn["deliveries"]):
            sender = 1 - j
            expected_id = queued[sender].pop(0) if queued[sender] else None
            check(event["id"] == expected_id, label, "queued recipe ID")
            if expected_id:
                packet = known[sender][expected_id]
                check(event["card"] == packet, label, "shared unknown recipe information")
                current = known[j].setdefault(expected_id, {})
                new_info = any(current.get(field) != number for field, number in packet.items())
                process["card_deliveries"] += 1
                process["informative_card_deliveries"] += new_info
                process["hidden_card_deliveries"] += new_info and expected_id not in initial
                current.update(packet)
            else:
                check(event["card"] is None, label, "card without a delivery")
            last = previous[sender]
            prior_action = last["output"]["action"] if last else None
            expected_intent = (prior_action["id"] or prior_action["room"]) if prior_action else ""
            expected_message = prior_action["say"] if prior_action else ""
            check(event["intent"] == expected_intent and event["message"] == expected_message
                  and event["goals"] == (last["held"] if last else []), label, "unexpected peer report")
            peer[j] = {k: event[k] for k in ("goals", "intent", "message")}
            process["text_deliveries"] += bool(event["message"])
        for j, row in enumerate(turn["attempts"]):
            check(row["player"] == names[j], label, "actor order")
            display = row["input"].split("\nCards: ", 1)[1].split(".\nItems you crafted", 1)[0]
            known_text = []
            for id, card in sorted(known[j].items()):
                kit = "/".join(f"{item}={qty}" for k, (item, qty) in enumerate(cards[id]["ingredients"].items())
                               if card.get(fields[k % 2]))
                known_text.append(f"{id} L={card.get('left', '?')} R={card.get('right', '?')} [{kit}]")
            check(display == ", ".join(known_text), label, "prompt cards differ from private and shared information")
            displayed_peer = row["input"].split("\nWork on missing", 1)[0].split(
                "Partner state from last open turn: ", 1)[1].removesuffix(".")
            check(json.loads(displayed_peer) == peer[j], label, "prompt received unexpected peer state")
            decision = row["output"]
            action = decision["action"]
            reservation = decision["reserved"]
            process["slots"] += 1
            process["reserved"] += reservation
            if "tokens" in decision:
                check(sum(decision["tokens"]) == reservation <= 960, label, "slot token accounting")
                process["measured_tokens"] += reservation
                process["model_responses"] += 1
            else:
                check(reservation in (0, 960) and action is None, label, "failed slot accounting")
                process["provider_failures"] += 1
                process[decision["status"]] += 1
            process[row["outcome"]] += 1
            if action is not None:
                outcome = row["outcome"]
                if action["act"] in ("collect", "craft"):
                    process["kitchen_actions_selected"] += 1
                    process["acted_on_known_peer_goal"] += action["id"] in peer[j].get("goals", [])
                if outcome.startswith("discovered_"):
                    id = outcome.removeprefix("discovered_")
                    check(action["act"] == "explore" and trial["stations"][j]["rooms"][action["room"]]["id"] == id,
                          label, "discovery did not match a visited clue")
                    if "position" in row:
                        x, y, z = trial["stations"][j]["rooms"][action["room"]]["marker"]
                        target = (x + 0.5, y, z + 0.5)
                        check(sum((p - q) ** 2 for p, q in zip(row["position"], target)) <= 2.8 ** 2,
                              label, "bot did not reach the clue marker")
                    known[j][id] = {f: cards[id][f] for f in fields}
                    discoveries[j].add(id)
                if action["act"] == "explore" and (outcome.startswith(("discovered_", "empty_"))):
                    visits[j].add(action["room"])
                if outcome.startswith("collected_"):
                    check(action["act"] == "collect" and all(int(action[f]) == cards[action["id"]][f] for f in fields),
                          label, "kit code")
                    kits[j].add(action["id"])
                if outcome.startswith("crafted_"):
                    id = action["id"]
                    before = previous[j]["inventory"] if previous[j] else {}
                    check(action["act"] == "craft" and id in kits[j]
                          and row["inventory"].get(id, 0) > before.get(id, 0), label, "unconfirmed game craft")
                    crafts[j].add(id)
                if action["share"] in known[j] and action["share"] not in queued[j]:
                    queued[j].append(action["share"])
            check(set(row["discoveries"]) == discoveries[j] and set(row["visits"]) == visits[j], label, "clue ledger")
            check(set(row["held"]) == {id for id in crafts[j] if row["inventory"].get(id)}, label, "goal progress")
            previous[j] = row
        stages.append(len(set(turn["attempts"][0]["held"]) | set(turn["attempts"][1]["held"])))
    check(process["slots"] <= trial["duration"] // trial["step"] * 2, label, "attempt budget")
    check(process["reserved"] <= 960 * trial["duration"] // trial["step"] * 2, label, "token ceiling")
    verified = {id for alias, crafted in zip(names, crafts) for id in crafted if final[alias].get(id)}
    check(set(result["goals"]) == verified and result["success"] == (len(verified) == len(cards)),
          label, "unique team goal score")
    finish = trace["finish"]
    elapsed = (finish - trace["start"]) / 1000 if finish else trial["duration"]
    check(result["elapsed"] == elapsed and 0 < elapsed <= trial["duration"]
          and (finish is None or result["success"]), label, "invalid finish time")
    seeded = set(trial["seeded"])
    return {"trial": label, "seed": trial["seed"], "mode": trial["mode"], "schedule": trial["schedule"],
            "goal_total": len(cards), "goals": len(verified), "known_goals": len(verified & seeded),
            "hidden_goals": len(verified - seeded), "hidden_discoveries": len(discoveries[0] | discoveries[1]),
            "duplicate_clues": len(discoveries[0] & discoveries[1]), "duplicate_kits": len(kits[0] & kits[1]),
            "duplicate_crafts": len(crafts[0] & crafts[1]), "elapsed": elapsed, "full": result["success"],
            "measured_tokens": process["measured_tokens"], "process": dict(process), "progress": stages,
            "client_match": result["client_match"], "inventory": final}


def aggregate(rows):
    spent = sum(r["elapsed"] for r in rows)
    goals = sum(r["goals"] for r in rows)
    return {"trials": len(rows), "mean_goals": mean(r["goals"] for r in rows),
            "mean_goal_fraction": mean(r["goals"] / r["goal_total"] for r in rows),
            "seconds_per_verified_goal": spent / goals if goals else None,
            "total_elapsed": spent, "total_goals": goals, "full_runs": sum(r["full"] for r in rows),
            **{f"mean_{key}": mean(r[key] for r in rows) for key in (
                "known_goals", "hidden_goals", "hidden_discoveries", "duplicate_clues", "duplicate_kits",
                "duplicate_crafts", "measured_tokens")},
            "process": dict(sum((Counter(r["process"]) for r in rows), Counter()))}


def collect(root, partial, probe):
    plan = read(root / "design.json")
    if not probe:
        check(plan["duration"] == 360 and plan["step"] == 10
              and {tuple(case) for case in plan["cases"]} == set(product(SEEDS, MODES, SCHEDULES))
              and len(plan["cases"]) == 90, "design", "incomplete assigned matrix")
    rows, pending = [], []
    for case in plan["cases"]:
        label = "-".join(map(str, case))
        options = [root / label, *root.glob(label + "-attempt*")]
        completed = [p for p in options if (p / "complete.json").is_file()]
        if not completed and partial:
            pending.append(label)
            continue
        check(len(completed) == 1, label, "expected exactly one terminal record")
        spec = read(completed[0] / "trial.json")
        check((spec["duration"], spec["step"]) == (plan["duration"], plan["step"]),
              label, "trial clock differs from the plan")
        rows.append(audit(completed[0], case))
    groups = {}
    comparisons = {}
    for mode in MODES:
        blocks = {s: {} for s in SCHEDULES}
        for row in [row for row in rows if row["mode"] == mode]:
            blocks[row["schedule"]][row["seed"]] = row
        for schedule, cases in blocks.items():
            if cases:
                groups[f"{mode}-{schedule}"] = aggregate(list(cases.values()))
        comparisons[mode] = {}
        for left, right in (("alternating", "always"), ("blocks", "always"), ("alternating", "blocks")):
            paired = sorted(set(blocks[left]) & set(blocks[right]))
            differences = [(s, blocks[left][s]["goals"] - blocks[right][s]["goals"]) for s in paired]
            if differences:
                comparisons[mode][f"{left}_minus_{right}"] = {
                    "mean_goal_difference": mean(d for _, d in differences),
                    "paired_goals": differences,
                }
    return {"verified_runs": len(rows), "pending": pending, "groups": groups, "comparisons": comparisons, "trials": rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path)
    ap.add_argument("--partial", action="store_true")
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()
    print(json.dumps(collect(args.root, args.partial, args.probe), indent=2))


if __name__ == "__main__":
    main()
