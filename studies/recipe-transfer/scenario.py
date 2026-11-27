"""Generate disjoint recipe families and their Minecraft 1.21.1 data packs."""
from itertools import product
import json
from pathlib import Path
import random

SEEDS = tuple(range(7280, 7290))
PILOT = 7279
TEACHER = "gpt-6.2-astra"
STUDENT = "gpt-6-luna"
SLOT = 2500
STEP = 18
DURATION = 360
SHELVES = (
    ("carrot", "apple", "beetroot", "wheat", "potato"),
    ("kelp", "sweet_berries", "melon_slice", "cocoa_beans", "egg"),
    ("sugar", "red_mushroom", "brown_mushroom", "honeycomb", "pumpkin_seeds"),
)
OUTPUTS = ("mushroom_stew", "pumpkin_pie", "rabbit_stew", "cake")
COLORS = ("white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray",
          "light_gray", "cyan", "purple", "blue", "brown", "green", "red", "black")
TICKETS = tuple(f"{color}_{block}" for block in ("wool", "concrete", "terracotta", "carpet",
                                              "concrete_powder", "stained_glass") for color in COLORS)
ARMS = ("teacher", "reuse_solo", "reuse_cards", "novel_solo", "novel_playbook")
LESSONS = {
    "ledger": "Keep the clues and all feedback for the current order in one candidate list. Delete every triple that would have given any different feedback on a past test.",
    "split": "Pick a test that can produce several different feedback counts across the remaining candidates. Choose a test that rules out useful groups whichever score appears.",
    "compare": "To identify one shelf, compare two tests that change only that shelf and keep the other two picks unchanged. A change in score identifies which of the two picks is correct there.",
    "zero": "A zero-match test rules out all three of its shelf choices for that order. A two-match test means exactly one of its choices needs to change.",
    "sum": "List triples with the required rank sum before testing. Once two shelf picks are fixed, subtract their ranks from the clue to find the last rank.",
    "finish": "When the evidence leaves just one possible triple, test it immediately and switch to another unfinished order.",
}


def dump(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)


def formulas():
    combos = list(product(*SHELVES))
    random.Random(708161).shuffle(combos)
    data = {}
    for i, (family, seed) in enumerate(product(("reuse", "novel"), (PILOT, *SEEDS))):
        data[family, seed] = {
            f"o{j+1}": {"food": food, "ticket": TICKETS[i * len(OUTPUTS) + j],
                        "ingredients": list(combos[i * len(OUTPUTS) + j])}
            for j, food in enumerate(OUTPUTS)
        }
    return data


def cases(phase):
    if phase == "probe":
        return [(PILOT, "teacher"), (PILOT, "novel_solo")]
    if phase == "calibration":
        return [(PILOT, "teacher"), (PILOT, "reuse_solo"), (PILOT, "novel_solo")]
    if phase == "teacher":
        return [(seed, "teacher") for seed in SEEDS]
    if phase != "students":
        raise ValueError(f"Unknown phase {phase}")
    plan = list(product(SEEDS, ARMS[1:]))
    random.Random(76429).shuffle(plan)
    return plan


def family_of(arm):
    return "novel" if arm.startswith("novel_") else "reuse"


def layout(seed, generation, orders):
    rng = random.Random(seed * 201 + generation)
    while True:
        shelves = [rng.sample(shelf, len(shelf)) for shelf in SHELVES]
        sums = {id: sum(shelf.index(item) + 1 for shelf, item in zip(shelves, row["ingredients"]))
                for id, row in orders.items()}
        if all(7 <= total <= 11 for total in sums.values()):
            return shelves, sums


def trial_spec(seed, arm, lane, attempt, phase, material):
    family = family_of(arm)
    generation = 0 if arm == "teacher" else 1 if family == "reuse" else 2
    orders = formulas()[family, seed]
    shelves, sums = layout(seed, generation, orders)
    if generation == 1 and shelves == layout(seed, 0, orders)[0]:
        raise ValueError("Teacher and student shelf layouts must differ")
    x = 64 + lane * 80
    side = 1 if generation == 0 else -1
    public = {"shelves": shelves, "orders": {id: {"food": row["food"], "sum": sums[id]}
                                             for id, row in orders.items()}}
    knowledge = ""
    if arm == "reuse_cards":
        cards = material["cards"][str(seed)]
        knowledge = "\n".join(f'{id} uses ' + ", ".join(row["ingredients"])
                              for id, row in cards.items())
    if arm == "novel_playbook":
        knowledge = "\n".join(LESSONS[id] for id in material["playbook"])
    return {"seed": seed, "arm": arm, "family": family, "player": f"F{seed}{ARMS.index(arm)}{attempt}",
            "model": TEACHER if arm == "teacher" else STUDENT, "public": public, "orders": orders,
            "knowledge": knowledge, "positions": {"home": [x, 65, 0], "table": [x+side, 65, -1],
                                                   "outbox": [x-side, 65, 1]},
            "duration": 72 if phase == "probe" else 180 if phase == "calibration" else DURATION,
            "step": 6 if phase == "probe" else STEP, "scripted": phase == "probe"}


def datapack(folder, plan):
    available = formulas()
    entries = {f"{family}_{seed}_{id}": row
               for family, seed in sorted({(family_of(arm), seed) for seed, arm in plan})
               for id, row in available[family, seed].items()}
    write_pack(folder, entries)


def write_pack(folder, entries):
    pack = folder / "Superflat" / "datapacks" / "hells-kitchen-recipes"
    recipes = pack / "data" / "hells_kitchen" / "recipe"
    recipes.mkdir(parents=True, exist_ok=True)
    dump(pack / "pack.mcmeta", {"pack": {"pack_format": 48, "description": "Hidden Hell's Kitchen orders"}})
    for id, row in entries.items():
        dump(recipes / f"{id}.json", {
            "type": "minecraft:crafting_shapeless", "category": "misc",
            "ingredients": [{"item": f"minecraft:{item}"} for item in [row["ticket"], *row["ingredients"]]],
            "result": {"id": "minecraft:" + row["food"], "count": 1},
        })
    return pack
