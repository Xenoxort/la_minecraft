"""Verify every visible model input and score the saved schedule trials offline."""
import argparse
from collections import Counter
from itertools import combinations, product
import json
from math import sqrt
from pathlib import Path
from statistics import mean, median

from study import (LETTERS, MODEL, PERIODS, REASONING, SCHEDULES, SEEDS, SIZES, TOKEN_UNIT, WORK_UNITS,
                   adaptive_open, evaluate, experiment_design, known, local_best, make_agents,
                   optimum, prompt, puzzle, relay, score)


def read(path):
    return json.loads(path.read_text())


def check(condition, message):
    if not condition:
        raise ValueError(message)


def ratio(n, d):
    return n / d if d else None


def avg(values):
    values = [n for n in values if n is not None]
    return mean(values) if values else None


def bounds(values):
    return {"mean": mean(values), "min": min(values), "max": max(values)}


def diversity(plans):
    return avg([len(set(a) ^ set(b)) / len(LETTERS) for a, b in combinations(plans, 2)])


def selected_plan(problem, candidates):
    return min(((-evaluate(problem, plan, ())["value"], plan, actor)
                for actor, plan in enumerate(candidates) if not evaluate(problem, plan, ())["errors"]))[1]


def phi(counts):
    n00, n01, n10, n11 = (counts[key] for key in product((False, True), repeat=2))
    denominator = sqrt((n10 + n11) * (n00 + n01) * (n01 + n11) * (n00 + n10))
    return ratio(n11 * n00 - n10 * n01, denominator)


def inspect_one(data, problem, top, cell):
    seed, regime, n, mode = cell
    name = f"{seed}-{regime}-{n}-{mode}"
    budget = PERIODS * WORK_UNITS * TOKEN_UNIT
    check((data["seed"], data["information"], data["agents"], data["schedule"]) == tuple(cell), f"{name}: cell")
    check((data["model"], data["optimum"], data["budget"]) == (MODEL, top, budget), f"{name}: model/optimum/budget")
    check(len(data["rounds"]) == PERIODS, f"{name}: horizon")
    actors = make_agents(regime, n, problem)
    stats, error_counts, cross_step = Counter(), Counter(), Counter()
    seen = {}
    exact, partial, scores, diversities, selected_scores, open_changes, closed_changes = [], [], [], [], [], [], []
    published = []
    generation_times = []
    for period, current in enumerate(data["rounds"], 1):
        opened = (adaptive_open(period, published, regime) if mode == "G" else period in SCHEDULES[mode])
        label = f"{name}, period {period}"
        check(current["period"] == period and current["open"] == opened, f"{label}: channel timing")
        check(len(current["attempts"]) == WORK_UNITS, f"{label}: work count")
        for step in range(WORK_UNITS // n):
            if opened:
                relay(actors)
            pending, errors = [], []
            for i, actor in enumerate(actors):
                example = current["attempts"][step * n + i]
                required = prompt(problem, regime, actor, i, period, step, opened)
                expected_peer = {str(j): list(plans) for j, plans in actor["peers"].items()}
                check((example["agent"], example["step"]) == (i, step), f"{label}: actor order")
                check(example["input"] == required and example["known"] == known(actor)
                      and example["peers"] == expected_peer, f"{label}: private or relayed information mismatch")
                count = example["usage"]
                stats["calls"] += 1
                stats["accounted_tokens"] += example["reserved_tokens"]
                generation_times.append(example["generation_seconds"])
                stats["provider_retries"] += example["provider_retries"]
                if count is None:
                    status = example["status"]
                    allowed = {"transport_unknown": (TOKEN_UNIT,), "input_count_unavailable": (0,),
                               "provider_rejected": (0, TOKEN_UNIT)}
                    check(status in allowed and example["reserved_tokens"] in allowed[status]
                          and example["plan"] is None and example["memory"] is None, f"{label}: transport accounting")
                    stats[status] += 1
                    stats["missing_plan"] += 1
                    continue
                check(count["total"] == count["input"] + count["output"] == example["reserved_tokens"]
                      <= TOKEN_UNIT and 0 <= count["reasoning"] <= count["output"], f"{label}: per-call token cap")
                for key, value in count.items():
                    stats[key] += value
                if example["status"] != "completed":
                    stats["incomplete_generation"] += 1
                    check(example["plan"] is None, f"{label}: incomplete plan unexpectedly accepted")
                if example["memory"] is not None:
                    check(len(example["memory"]) <= 88, f"{label}: private memory bound")
                    actor["memory"] = example["memory"]
                plan = example["plan"]
                if plan is None:
                    stats["missing_plan"] += 1
                    continue
                check(plan == "".join(sorted(set(plan))) and set(plan) <= set(LETTERS), f"{label}: plan syntax")
                actor["last"] = plan
                actor["plans"].append(plan)
                q = evaluate(problem, plan, range(len(problem["rules"])))
                pending.append((i, plan))
                errors.append(set(q["errors"]))
                stats["valid_syntax"] += 1
                stats["feasible_proposals"] += not q["errors"]
                stats["repeat_other_prior"] += bool(seen.get(plan, set()) - {i})
                stats["repeat_self_prior"] += i in seen.get(plan, set())
                stats["used_received_plan"] += any(plan in ps for ps in actor["peers"].values())
            same_wave = Counter(p for _, p in pending)
            stats["same_wave_duplicate"] += sum(count - 1 for count in same_wave.values())
            for i, plan in pending:
                seen.setdefault(plan, set()).add(i)
            violations = ("labor", "material", *(f"rule{i}" for i in range(1, 9)))
            for left, right in combinations(errors, 2):
                for key in violations:
                    both = key in left, key in right
                    error_counts[both] += 1
                    error_counts[both[::-1]] += 1  # Remove arbitrary actor ordering.
                cross_step["eligible_error_pairs"] += bool(left | right)
                cross_step["shared_error_pairs"] += bool(left & right)
        candidates = [local_best(problem, actor) for actor in actors]
        check(candidates == current["candidates"], f"{label}: retained candidate selection")
        check(max(evaluate(problem, p, ())["value"] for p in candidates) == current["observable_best"]
              and len(set(candidates)) == current["observable_diversity"], f"{label}: monitor state")
        team = selected_plan(problem, candidates)
        period_quality = mean(score(problem, top, plan) for plan in candidates)
        if scores:
            if opened and not published[-1]["open"]:
                open_changes.append(period_quality - scores[-1])
            elif not opened:
                closed_changes.append(period_quality - scores[-1])
        scores.append(period_quality)
        candidates_quality = [score(problem, top, plan) for plan in candidates]
        selected_scores.append(score(problem, top, team))
        exact.append(sum(q == 1 for q in candidates_quality))
        partial.append(sum(q >= 0.9 for q in candidates_quality))
        diversities.append(diversity(candidates))
        published.append(current)

    check(stats["calls"] == PERIODS * WORK_UNITS and stats["accounted_tokens"] <= budget, f"{name}: team token cap")
    if mode == "G":
        check(sum(r["open"] for r in published) == 4, f"{name}: adaptive exposure count")
    selected = selected_plan(problem, candidates)
    best = max(score(problem, top, p) for actor in actors for p in ["", *actor["plans"]])
    return {"cell": list(cell), "name": name, "selected_plan": selected, "selected_quality": selected_scores[-1],
            "selected_feasible": not evaluate(problem, selected, range(len(problem["rules"])))["errors"],
            "success": selected_scores[-1] == 1, "near_optimum": selected_scores[-1] >= 0.9,
            "best_individual_quality": best, "mean_final_quality": scores[-1],
            "final_diversity": diversities[-1], "mean_period_diversity": mean(diversities),
            "selected_by_period": selected_scores, "mean_quality_by_period": scores, "diversity_by_period": diversities,
            "optimal_agents_at_end": exact[-1], "near_optimal_agents_at_end": partial[-1],
            "rule_visibility_at_end": mean(len(known(actor)) / len(problem["rules"]) for actor in actors),
            "error_phi": phi(error_counts), "error_pair_overlap": ratio(cross_step["shared_error_pairs"],
                                                                       cross_step["eligible_error_pairs"]),
            "reopening_improvement": avg(open_changes), "closed_period_improvement": avg(closed_changes),
            "open_periods": [r["period"] for r in published if r["open"]],
            "wall_seconds": data["wall_seconds"], "median_generation_seconds": median(generation_times),
            "cross_agent_duplicate_rate": ratio(stats["repeat_other_prior"], stats["valid_syntax"]),
            "same_wave_duplicate_rate": ratio(stats["same_wave_duplicate"], stats["valid_syntax"]),
            "received_plan_adoption_rate": ratio(stats["used_received_plan"], stats["valid_syntax"]),
            "token_count": dict(stats)}


def group(rows):
    keys = ("selected_quality", "best_individual_quality", "mean_final_quality", "final_diversity",
            "mean_period_diversity", "rule_visibility_at_end", "error_phi", "error_pair_overlap",
            "reopening_improvement", "closed_period_improvement", "cross_agent_duplicate_rate",
            "same_wave_duplicate_rate", "received_plan_adoption_rate")
    return {"trials": len(rows), "successes": sum(r["success"] for r in rows),
            "near_optimum": sum(r["near_optimum"] for r in rows),
            "selected_feasible": sum(r["selected_feasible"] for r in rows),
            **{key: avg([r[key] for r in rows]) for key in keys},
            "wall_seconds": bounds([r["wall_seconds"] for r in rows]),
            "measured_tokens": bounds([r["token_count"].get("total", 0) for r in rows]),
            "missing_plans": sum(r["token_count"].get("missing_plan", 0) for r in rows),
            "unknown_transport": sum(r["token_count"].get("transport_unknown", 0) for r in rows),
            "calls": sum(r["token_count"]["calls"] for r in rows)}


def contrasts(rows):
    by_group = {(tuple(row["cell"][:3]), row["cell"][3]): row for row in rows}
    comparisons = [
        ("C", "A"), ("C", "B"), ("C", "D"), ("E", "F"),
        *([("G", "C"), ("G", "D")] if any(r["cell"][3] == "G" for r in rows) else []),
    ]
    results = {}
    for info in ("public", "distributed"):
        results[info] = {}
        for left, right in comparisons:
            pairs = [(by_group[((seed, info, n), left)], by_group[((seed, info, n), right)])
                     for seed, n in product(SEEDS, SIZES)]
            diffs = [a["selected_quality"] - b["selected_quality"] for a, b in pairs]
            results[info][f"{left}-{right}"] = {"mean_quality_difference": mean(diffs),
                "win_tie_loss": [sum(d > 0 for d in diffs), sum(d == 0 for d in diffs), sum(d < 0 for d in diffs)],
                "paired_differences": diffs}
    return results


def analyze(roots):
    problems = {seed: puzzle(seed) for seed in SEEDS}
    tops = {seed: optimum(problem) for seed, problem in problems.items()}
    rows = []
    for index, root in enumerate(roots):
        design = experiment_design(bool(index))
        manifest = read(root / "manifest.json")
        check(manifest["cells"] == [list(cell) for cell in design]
              and manifest["model"] == MODEL and manifest["reasoning"] == REASONING
              and manifest["per_call_tokens"] == TOKEN_UNIT and manifest["periods"] == PERIODS
              and manifest["work_per_period"] == WORK_UNITS
              and manifest["schedules"] == {k: list(v) for k, v in SCHEDULES.items()}
              and manifest["optima"] == {str(k): v for k, v in tops.items()},
              f"{root}: experiment manifest mismatch")
        check(len(list(root.glob("*.json"))) == len(design) + 1, f"{root}: unexpected result file count")
        for seed, info, n, mode in design:
            data = read(root / f"{seed}-{info}-{n}-{mode}.json")
            rows.append(inspect_one(data, problems[seed], tops[seed], (seed, info, n, mode)))
    modes = (*SCHEDULES, *(("G",) if len(roots) == 2 else ()))
    groups = {}
    for regime, mode in product(("public", "distributed"), modes):
        chosen = [r for r in rows if r["cell"][1] == regime and r["cell"][3] == mode]
        groups[f"{regime}-{mode}"] = group(chosen)
        for n in SIZES:
            groups[f"{regime}-{n}-{mode}"] = group([r for r in chosen if r["cell"][2] == n])
    return {"groups": groups, "paired_contrasts": contrasts(rows), "episodes": rows,
            "verification": {"episodes": len(rows), "inputs_reconstructed": len(rows) * PERIODS * WORK_UNITS,
                             "model": MODEL, "reasoning": REASONING,
                             "budget_per_team": PERIODS * WORK_UNITS * TOKEN_UNIT}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixed", type=Path)
    parser.add_argument("--adaptive", type=Path)
    args = parser.parse_args()
    result = analyze([args.fixed, args.adaptive] if args.adaptive else [args.fixed])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
