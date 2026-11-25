"""Reconcile the Minecraft server logs and verify the schedule evidence."""
import argparse
from collections import Counter
from itertools import combinations, product
import json
from math import sqrt
from pathlib import Path
from statistics import mean, median

from run import SCHEDULES, design, make_trial, terminal

SLOT = 960
ERRORS = ("unknown_item", "stock_unavailable", "recipe_or_ingredients_unavailable", "no_inventory_gain",
          "game_action_error")


def read(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def average(values):
    return mean(values) if values else None


def phi(counts):
    a, b, c, d = (counts[flags] for flags in product((False, True), repeat=2))
    scale = sqrt((a + b) * (a + c) * (d + b) * (d + c))
    return (a * d - b * c) / scale if scale else None


def scores(trial, inventories):
    return [sum(inventories[card["owner"]].get(g["item"], 0) > 0 for g in card["goals"])
            for card in trial["cards"]]


def adaptive_open(trial, period, past):
    used = sum(p["open"] for p in past)
    if used == 4:
        return False
    if 11 - period == 4 - used:
        return True
    if period == 1:
        return trial["information"] == "split"
    return period >= 3 and not past[-1]["open"] and past[-1]["goals_held"] <= past[-2]["goals_held"]


def audit(path, trial):
    recorded_trial = read(path / "trial.json")
    require(recorded_trial == trial, f"{path}: trial specification changed")
    trace = read(path / "episodes.json")
    saved = read(path / "complete.json")["terminal"]
    log = (path / "minecraft.log").read_text(errors="replace")
    ready = log.split("[Server] HK_BEGIN", 1)[0]
    names = trial["names"]
    require(all(f"{name} joined the game" in ready for name in names), f"{path}: missing bot join")
    require(terminal(log, names) == saved == trace["inventories"], f"{path}: terminal inventory")
    require(trace["model"] == "gpt-6-luna" and trace["token_budget"] == 80 * SLOT
            and len(trace["periods"]) == 10, f"{path}: model or budget constant")
    n = len(names)
    cards = {name: trial["cards"][(i + 1) % n] for i, name in enumerate(names)}
    receipts = {name: set() for name in names}
    private_inv = {name: {} for name in names}
    visible = {name: {} for name in names}
    attempted_recipes = {name: set() for name in names}
    last_failures = set()
    counts, pairs = Counter(), Counter()
    past, curve, reopen, closed = [], [], [], []
    first_wave = None
    own_exposure = None if trial["information"] == "split" else 0
    for period, record in enumerate(trace["periods"], 1):
        is_open = (adaptive_open(trial, period, past) if trial["schedule"] == "G"
                   else period in trial["windows"])
        require(record["period"] == period and record["open"] == is_open
                and len(record["attempts"]) == 8, f"{path}: phase {period}")
        if is_open and own_exposure is None:
            own_exposure = period
        for wave in range(8 // n):
            items = record["attempts"][wave * n:(wave + 1) * n]
            if is_open:
                visible = {name: {peer: {"cards": cards[peer], "recipes_crafted": sorted(receipts[peer])}
                                  for peer in names if peer != name} for name in names}
            wave_errors = []
            for actor, attempt in enumerate(items):
                name = names[actor]
                require((attempt["name"], attempt["step"], attempt["visible"]) == (name, wave, visible[name]),
                        f"{path}: changed peer access in period {period}")
                allowed = (trial["cards"] if trial["information"] == "public"
                           else [cards[name], *(v["cards"] for v in visible[name].values())])
                visible_cards = "\n".join(card["owner"] + " " + "; ".join(
                    g["item"] + ": " + g["recipe"] for g in card["goals"]) for card in allowed)
                expected_targets = ", ".join(g["item"] for card in allowed if card["owner"] == name
                                             for g in card["goals"]) or "Your recipe card is held by another bot"
                actual_targets = attempt["input"].split("\nYour targets: ", 1)[1].split("\n", 1)[0]
                expected_receipts = " ".join(peer + ":" + ",".join(state["recipes_crafted"])
                                             for peer, state in visible[name].items()
                                             if state["recipes_crafted"]) or "none"
                actual_receipts = attempt["input"].split(
                    "\nPreviously shared peer crafting receipts: ", 1)[1].split("\n", 1)[0]
                require(attempt["input"].split("\nVisible recipe cards:\n", 1)[1].split(
                    "\nOwn inventory: ", 1)[0] == visible_cards and actual_targets == expected_targets
                    and actual_receipts == expected_receipts, f"{path}: prompt disclosed unexpected peer data")
                action = attempt["action"]
                result = attempt["outcome"]
                counts["slots"] += 1
                counts["reserved"] += attempt["reserved"]
                tokens = attempt.get("tokens")
                if tokens is None:
                    require(attempt["reserved"] in (0, SLOT) and action is None,
                            f"{path}: missing response accounting")
                    counts["provider_unavailable"] += 1
                    counts[attempt["status"]] += 1
                else:
                    require(sum(tokens.values()) == attempt["reserved"] <= SLOT, f"{path}: token accounting")
                    counts["input_tokens"] += tokens["input"]
                    counts["output_tokens"] += tokens["output"]
                    counts["provider_responses"] += 1
                if not action:
                    counts["missing_actions"] += 1
                else:
                    verb = action["action"]
                    if verb != "wait":
                        counts["game_attempts"] += 1
                        wave_errors.append(result in ERRORS)
                    counts[result] += 1
                    if verb == "craft":
                        counts["craft_attempts"] += 1
                        item = action["item"]
                        attempted_recipes[name].add(item)
                        if result.startswith("gained_"):
                            require(attempt["inventory"].get(item, 0) > private_inv[name].get(item, 0),
                                    f"{path}: crafting result did not change inventory")
                            receipts[name].add(item)
                            counts["craft_actions_succeeded"] += 1
                        elif result in ERRORS:
                            key = (name, item, tuple(sorted(private_inv[name].items())), result)
                            counts["repeated_identical_craft_error"] += key in last_failures
                            last_failures.add(key)
                private_inv[name] = attempt["inventory"]
            for left, right in combinations(wave_errors, 2):
                pairs[(left, right)] += 1
                pairs[(right, left)] += 1
            held = sum(scores(trial, private_inv))
            if held == 8 and first_wave is None:
                first_wave = ((period - 1) * 8 // n) + wave + 1
        require(record["goals_held"] == held, f"{path}: goal trajectory mismatch")
        if curve:
            if is_open and not past[-1]["open"]:
                reopen.append(held - curve[-1])
            elif not is_open:
                closed.append(held - curve[-1])
        curve.append(held)
        past.append(record)
    require(counts["slots"] == 80 and counts["reserved"] <= trace["token_budget"], f"{path}: total cap")
    require(trial["schedule"] != "G" or sum(row["open"] for row in past) == 4, f"{path}: adaptive exposure")
    finish = scores(trial, saved)
    held = sum(finish)
    require(held == curve[-1], f"{path}: terminal trajectory mismatch")
    for card in trial["cards"]:
        name = card["owner"]
        require(all(not saved[name].get(g["item"]) or g["item"] in receipts[name] for g in card["goals"]),
                f"{path}: goal item was not crafted by its assigned bot")
    fraction = [v / (8 // n) for v in finish]
    return {"name": path.name, "recipes": trial["recipes"], "information": trial["information"],
            "agents": n, "schedule": trial["schedule"], "finished": held == 8, "goals_held": held,
            "goal_curve": curve, "best_agent_fraction": max(fraction), "mean_agent_fraction": mean(fraction),
            "first_period_all": next((i for i, val in enumerate(curve, 1) if val == 8), None),
            "first_wave_all": first_wave, "open_periods": [p["period"] for p in past if p["open"]],
            "first_period_own_card_visible": own_exposure,
            "mean_gain_on_reopening": average(reopen), "mean_gain_on_closed_period": average(closed),
            "distinct_recipe_attempts_per_agent": mean(map(len, attempted_recipes.values())),
            "paired_error_phi": phi(pairs), "wall_seconds": trace["wall_seconds"],
            "counts": dict(counts), "terminal": saved}


def aggregate(rows):
    stats = sum((Counter(r["counts"]) for r in rows), Counter())
    end_periods = [r["first_period_all"] for r in rows if r["finished"]]
    return {"trials": len(rows), "complete": len(end_periods), "mean_goals": mean(r["goals_held"] for r in rows),
            "median_completion_period_among_successes": median(end_periods) if end_periods else None,
            "mean_capped_completion_period": mean(r["first_period_all"] or 11 for r in rows),
            "goals_by_period": [mean(r["goal_curve"][i] for r in rows) for i in range(10)],
            "mean_best_agent_fraction": mean(r["best_agent_fraction"] for r in rows),
            "mean_distinct_recipe_attempts": mean(r["distinct_recipe_attempts_per_agent"] for r in rows),
            "mean_paired_error_phi": average([r["paired_error_phi"] for r in rows if r["paired_error_phi"] is not None]),
            "mean_gain_on_reopening": average([r["mean_gain_on_reopening"] for r in rows
                                              if r["mean_gain_on_reopening"] is not None]),
            "mean_wall_seconds": mean(r["wall_seconds"] for r in rows),
            "mean_measured_tokens": (stats["input_tokens"] + stats["output_tokens"]) / len(rows), "counts": dict(stats)}


def matched_contrasts(rows):
    cases = {(r["information"], r["recipes"], r["agents"], r["schedule"]): r for r in rows}
    output = {}
    for regime in ("public", "split"):
        output[regime] = {}
        blocks = sorted({(r["recipes"], r["agents"]) for r in rows if r["information"] == regime})
        for left, right in (("B", "A"), ("C", "B"), ("C", "D"), ("E", "F"), ("G", "D")):
            pairs = []
            for recipe, n in blocks:
                a, b = (cases.get((regime, recipe, n, mode)) for mode in (left, right))
                if a and b:
                    pairs.append({"recipe": recipe, "agents": n, "goal_difference": a["goals_held"] - b["goals_held"],
                                  "capped_period_difference": (a["first_period_all"] or 11) -
                                  (b["first_period_all"] or 11)})
            if pairs:
                output[regime][f"{left}-{right}"] = {
                    "pairs": pairs,
                    "mean_goal_difference": mean(r["goal_difference"] for r in pairs),
                    "mean_capped_period_difference": mean(r["capped_period_difference"] for r in pairs),
                }
    return output


def collect(output, allow_partial):
    rows, pending = [], []
    for trial in read(output / "design.json"):
        label = f"{trial['recipes']}-{trial['information']}-{trial['agents']}-{trial['schedule']}"
        options = [output / label, *sorted(output.glob(label + "-attempt*"))]
        completed = [p for p in options if (p / "complete.json").is_file()]
        if not completed and allow_partial:
            pending.append(label)
            continue
        require(len(completed) == 1, f"{label}: expected one terminal record")
        rows.append(audit(completed[0], trial))
    require(rows, "No completed episodes")
    groups = {}
    for regime, mode in product(("public", "split"), SCHEDULES):
        included = [r for r in rows if (r["information"], r["schedule"]) == (regime, mode)]
        if included:
            groups[f"{regime}-{mode}"] = aggregate(included)
        for size in (2, 4, 8):
            sized = [r for r in included if r["agents"] == size]
            if sized:
                groups[f"{regime}-{size}-{mode}"] = aggregate(sized)
    return {"verified_trials": len(rows), "pending": pending, "groups": groups,
            "matched_contrasts": matched_contrasts(rows), "episodes": rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output", type=Path)
    ap.add_argument("--partial", action="store_true")
    args = ap.parse_args()
    print(json.dumps(collect(args.output, args.partial), indent=2))


if __name__ == "__main__":
    main()
