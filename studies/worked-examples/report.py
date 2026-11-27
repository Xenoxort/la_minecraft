"""Verify the worked-example comparison and compute matched effects."""
import argparse
import json
from pathlib import Path
from statistics import mean, median

from study import DONORS, SOURCE_ARMS, STUDENTS, STUDENT_ARMS, calibrate, derive, verify
from analyze import contrast, group, need, read

# Published standard input and output prices per million tokens on the run date.
LIST_RATES = {"luna": (0.10, 0.50), "astra": (8.00, 40.00)}


def stats(root, rows, arms, *, donor):
    results = {}
    first_inputs = {}
    for arm in arms:
        members = [row for row, _, _ in rows if row["arm"] == arm]
        summary = group(members)
        delays, kitchen_delays = [], []
        for row in members:
            trace = read(root / row["folder"] / "trace.json")
            decisions = trace["history"]
            first_inputs[row["seed"], arm] = decisions[0]["decision"].get("tokens", {}).get("input")
            delays.extend(record["decision_ms"] / 1000 for record in decisions)
            kitchen_delays.extend((record["at"] - record["due"] - record["decision_ms"]) / 1000
                                  for record in decisions if record["at"] is not None)
        usage = summary["usage"]
        tokens = usage["input"] + usage["output"]
        input_rate, output_rate = LIST_RATES[arm if donor else "luna"]
        cost = (input_rate * usage["input"] + output_rate * usage["output"]) / 1_000_000
        orders = sum(r["count"] for r in members)
        summary.update({"mean_attempts": mean(r["tests"] for r in members), "orders": orders,
                        "attempts_per_delivery": summary["tests"] / orders if orders else None,
                        "mean_tokens": tokens / len(members), "tokens": tokens, "list_cost_usd": round(cost, 6),
                        "median_request_seconds": median(delays), "max_request_seconds": max(delays),
                        "median_non_model_seconds": median(kitchen_delays) if kitchen_delays else None})
        results[arm] = summary
    return results, first_inputs


def summary(root):
    calibration = calibrate(root / "calibration")
    need(calibration == read(root / "difficulty.json"), "Selected difficulty differs from calibration")
    width = calibration["width"]
    donors = verify(root / "donors", "donors", width)
    worked = derive(root / "donors", width, donors)
    need(worked == read(root / "material.json"), "Worked examples disagree with matched verified donor logs")
    students = verify(root / "students", "students", width, worked)
    teacher_groups, _ = stats(root / "donors", donors, SOURCE_ARMS, donor=True)
    groups, first_inputs = stats(root / "students", students, STUDENT_ARMS, donor=False)
    lookup = {(r["seed"], r["arm"]): r for r, _, _ in students}
    contrasts = {}
    for treatment, control in (("luna_examples", "solo"), ("astra_examples", "solo"),
                               ("astra_examples", "luna_examples")):
        effects = {}
        for field in ("count", "tests", "first_capped", "elapsed"):
            values = [round(lookup[seed, treatment][field] - lookup[seed, control][field], 3) for seed in STUDENTS]
            effects[field] = {**contrast(values), "positive": sum(v > 0 for v in values),
                              "negative": sum(v < 0 for v in values)}
        contrasts[treatment + "_minus_" + control] = effects
    token_pairs = [[first_inputs[seed, arm] for arm in STUDENT_ARMS] for seed in STUDENTS]
    combined = {}
    for arm in STUDENT_ARMS:
        model = arm.removesuffix("_examples")
        source = teacher_groups[model] if arm.endswith("_examples") else None
        combined[arm] = {
            "tokens": groups[arm]["tokens"] + (source["tokens"] if source else 0),
            "list_cost_usd": round(groups[arm]["list_cost_usd"] + (source["list_cost_usd"] if source else 0), 6),
        }
    pack = {}
    for arm in SOURCE_ARMS:
        third = [record["steps"][2] for record in worked["examples"][arm]]
        pack[arm] = {"characters": len(worked["rendered"][arm]), "examples": len(third),
                     "informative_third_steps": sum(sum(x > 0 for x in step["partition"]) > 1 for step in third),
                     "mean_candidates_after_third": mean(step["left"] for step in third)}
    return {
        "difficulty": calibration, "students": groups, "donors": teacher_groups, "contrasts": contrasts,
        "teacher_plus_students": combined, "example_packs": pack, "first_input_tokens_order": STUDENT_ARMS,
        "first_input_tokens": token_pairs, "source_orders": [[e["seed"], e["order"]] for e in worked["examples"]["luna"]],
        "trials": [row for row, _, _ in students], "donor_trials": [row for row, _, _ in donors],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(summary(args.root), indent=2, sort_keys=True))
