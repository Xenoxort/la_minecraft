"""Calibrate and run matched Minecraft kitchens with worked recipe examples."""
import argparse
from functools import lru_cache, partial
from itertools import permutations, product
from pathlib import Path
import random
from statistics import mean
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "recipe-transfer"))

from analyze import need, read, verify_batch
from run import run_phase
from scenario import COLORS, OUTPUTS, STUDENT, TEACHER, dump, write_pack

PROBE_SEED = 8029
CALIBRATION = tuple(range(8030, 8034))
DONORS = tuple(range(8040, 8048))
STUDENTS = tuple(range(8050, 8062))
WIDTHS = (4, 5, 6)
SOURCE_ARMS = ("luna", "astra")
STUDENT_ARMS = ("solo", "luna_examples", "astra_examples")
SLOT = 3200
SHELVES = (
    ("carrot", "apple", "beetroot", "wheat", "potato", "beetroot_seeds"),
    ("kelp", "sweet_berries", "melon_slice", "cocoa_beans", "egg", "glow_berries"),
    ("sugar", "red_mushroom", "brown_mushroom", "honeycomb", "pumpkin_seeds", "vine"),
    ("dandelion", "poppy", "blue_orchid", "allium", "azure_bluet", "cornflower"),
)
TICKETS = tuple(f"{color}_{block}" for block in ("wool", "concrete", "terracotta", "carpet", "concrete_powder",
                                               "stained_glass", "glazed_terracotta", "stained_glass_pane",
                                               "candle", "banner") for color in COLORS)
PHASES = ("probe", "calibration", "donors", "students")
EXAMPLE_COUNT = 4


def cases(phase):
    if phase == "probe":
        return [(PROBE_SEED, f"width{width}") for width in WIDTHS]
    if phase == "calibration":
        return [(seed, f"width{width}") for seed, width in product(CALIBRATION, WIDTHS)]
    if phase == "donors":
        return [(seed, arm) for seed in DONORS for arm in SOURCE_ARMS[::(-1 if seed % 2 else 1)]]
    order = list(permutations(STUDENT_ARMS)) * 2
    random.Random(9064).shuffle(order)
    return [(seed, arm) for seed, arms in zip(STUDENTS, order) for arm in arms]


def configuration(phase, width):
    return {"phase": phase, "width": width, "cases": [list(pair) for pair in cases(phase)]}


@lru_cache
def puzzles(width):
    stock = tuple(shelf[:width] for shelf in SHELVES)
    combos = list(product(*stock))
    random.Random(55300 + width).shuffle(combos)
    data = {}
    for index, seed in enumerate((*DONORS, *STUDENTS, PROBE_SEED, *CALIBRATION)):
        # All simultaneous datapack entries need distinct physical tickets.
        ticket_index = index if index < 20 else index + 5 * (width - WIDTHS[0])
        data[seed] = {f"o{j+1}": {"ticket": TICKETS[ticket_index * len(OUTPUTS) + j], "food": food,
                                 "ingredients": list(combos[index * len(OUTPUTS) + j])}
                      for j, food in enumerate(OUTPUTS)}
    return data


def width_for(arm, width):
    return width if width is not None else int(arm[-1])


def fixture(seed, arm, lane, attempt, phase, material, *, width):
    width = width_for(arm, width)
    orders = puzzles(width)[seed]
    rng = random.Random(seed * 471 + width)
    while True:
        shelves = [rng.sample(shelf[:width], width) for shelf in SHELVES]
        sums = {id: sum(shelf.index(ingredient)+1 for shelf, ingredient in zip(shelves, row["ingredients"]))
                for id, row in orders.items()}
        if all(abs(total - 2 * (width + 1)) <= 2 for total in sums.values()):
            break
    x = 64 + lane * 80
    roles = (*SOURCE_ARMS, *STUDENT_ARMS, *(f"width{w}" for w in WIDTHS))
    knowledge = material["rendered"][arm.removesuffix("_examples")] if arm.endswith("_examples") else ""
    return {"seed": seed, "arm": arm, "model": TEACHER if arm == "astra" else STUDENT,
            "player": f"W{seed}{roles.index(arm)}{attempt}", "slot": SLOT,
            "public": {"shelves": shelves, "orders": {id: {"food": row["food"], "sum": sums[id]}
                                                      for id, row in orders.items()}},
            "stock_shelves": [list(shelf[:width]) for shelf in SHELVES], "orders": orders, "knowledge": knowledge,
            "positions": {"home": [x, 65, 0], "table": [x+1, 65, -1], "outbox": [x-1, 65, 1]},
            "scripted": phase == "probe", "step": 6 if phase == "probe" else 18,
            "duration": 72 if phase == "probe" else 540 if phase == "donors" else 360}


def datapack(folder, plan, *, width):
    entries = {}
    for seed, arm in plan:
        w = width_for(arm, width)
        entries.update({f"{w}_{seed}_{id}": row for id, row in puzzles(w)[seed].items()})
    return write_pack(folder, entries)


def verify(root, phase, width=None, material=None):
    return verify_batch(root, phase, material, plan=cases(phase), manifest=configuration(phase, width),
                        fixture=partial(fixture, width=width))


def calibrate(root):
    study = verify(root, "calibration")
    choices = {}
    for width in WIDTHS:
        counts = [row["count"] for row, _, _ in study if row["arm"] == f"width{width}"]
        choices[str(width)] = {"orders": counts, "mean": mean(counts)}
    eligible = [w for w in WIDTHS if 1 <= choices[str(w)]["mean"] <= 3.5]
    selected = min(eligible or WIDTHS, key=lambda w: (abs(choices[str(w)]["mean"] - 2.5), -w))
    return {"width": selected, "calibration": choices}


def matches(candidate, test):
    return sum(a == b for a, b in zip(candidate, test))


def example_steps(tests, total, width):
    pending = {p for p in product(range(1, width+1), repeat=len(SHELVES)) if sum(p) == total}
    steps = []
    for test in tests:
        ranks = test["ranks"]
        partition = [0] * (1 + len(SHELVES))
        for candidate in pending:
            partition[matches(candidate, ranks)] += 1
        pending = {p for p in pending if matches(p, ranks) == test["hits"]}
        steps.append({"turn": test["turn"], "ranks": ranks, "score": test["hits"],
                      "partition": partition, "left": len(pending)})
    return steps


def render_examples(examples):
    lines = ["Worked examples from four past kitchens. Each is a separate order with its own rank sum.",
             "The split lists how many candidates would give 0, 1, 2, 3, or 4 matches before seeing the feedback. "
             "The remaining count is after applying that feedback."]
    for idx, example in enumerate(examples, 1):
        lines.append(f'Example {idx}, past rank sum {example["sum"]:02d}.')
        for test, row in enumerate(example["steps"], 1):
            ranks = ",".join(map(str, row["ranks"]))
            split = ",".join(f"{number:03d}" for number in row["partition"])
            lines.append(f'Test {test} [{ranks}] split [{split}] feedback {row["score"]}/4, '
                         f'{row["left"]:03d} remain.')
    return "\n".join(lines)


def derive(root, width, runs=None):
    donors = verify(root, "donors", width) if runs is None else runs
    index = {(row["seed"], row["arm"]): (row, done, tests) for row, done, tests in donors}
    examples = {arm: [] for arm in SOURCE_ARMS}
    for seed in DONORS:
        candidates = {}
        for arm in SOURCE_ARMS:
            _, done, tests = index[seed, arm]
            candidates[arm] = {}
            for id in done:
                actions = [test for test in tests if test["order"] == id]
                if len(actions) >= 3 and actions[0]["hits"] < 4 and actions[1]["hits"] < 4:
                    candidates[arm][id] = actions[:3]
        shared = sorted(set(candidates["luna"]) & set(candidates["astra"]))
        if not shared:
            continue
        id = shared[0]
        for arm in SOURCE_ARMS:
            row, _, _ = index[seed, arm]
            source_trial = read(root / row["folder"] / "trial.json")
            total = source_trial["public"]["orders"][id]["sum"]
            steps = example_steps(candidates[arm][id], total, width)
            examples[arm].append({"seed": seed, "order": id, "sum": total, "steps": steps})
        if len(examples["luna"]) == EXAMPLE_COUNT:
            break
    need(all(len(value) == EXAMPLE_COUNT for value in examples.values()), "Too few common verified donor examples")
    rendered = {arm: render_examples(examples[arm]) for arm in SOURCE_ARMS}
    need(len(rendered["luna"]) == len(rendered["astra"]), "Example packs differ in text size")
    donor_truth = [row["ingredients"] for seed in DONORS for row in puzzles(width)[seed].values()]
    tested_truth = [row["ingredients"] for seed in STUDENTS for row in puzzles(width)[seed].values()]
    need(len({tuple(p) for p in donor_truth+tested_truth}) == len(donor_truth+tested_truth),
         "Donor and held-out answers are not disjoint")
    return {"width": width, "examples": examples, "rendered": rendered}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="command", required=True)
    run = command.add_parser("run")
    run.add_argument("root", type=Path)
    run.add_argument("--phase", choices=PHASES, required=True)
    run.add_argument("--difficulty", type=Path)
    run.add_argument("--material", type=Path)
    run.add_argument("--archive", type=Path, default=Path("/tmp/examples-world"))
    run.add_argument("--key", type=Path, default=Path("/tmp/examples-keys.json"))
    run.add_argument("--servers", type=int, default=3)
    run.add_argument("--lanes", type=int, default=4)
    calibration = command.add_parser("calibrate")
    calibration.add_argument("root", type=Path)
    calibration.add_argument("output", type=Path)
    material = command.add_parser("derive")
    material.add_argument("root", type=Path)
    material.add_argument("difficulty", type=Path)
    material.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "calibrate":
        result = calibrate(args.root)
        dump(args.output, result)
        print(result, flush=True)
        return
    if args.command == "derive":
        selected = read(args.difficulty)["width"]
        result = derive(args.root, selected)
        if args.output.exists():
            need(read(args.output) == result, "Frozen examples differ from verified donors")
        else:
            dump(args.output, result)
        print([(record["seed"], record["order"]) for record in result["examples"]["luna"]], flush=True)
        return
    if (args.phase in ("donors", "students")) != (args.difficulty is not None):
        parser.error("Donor and student stages require the calibrated difficulty file")
    if (args.phase == "students") != (args.material is not None):
        parser.error("Student trials require the frozen worked examples")
    selected = read(args.difficulty)["width"] if args.difficulty else None
    worked = read(args.material) if args.material else {}
    need(not worked or worked["width"] == selected, "Worked examples use a different difficulty")
    run_phase(args, cases(args.phase), configuration(args.phase, selected), worked,
              partial(fixture, width=selected), partial(datapack, width=selected))


if __name__ == "__main__":
    main()
