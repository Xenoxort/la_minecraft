"""Replay the physical handoffs and aggregate matched Hell's Kitchen trials."""
from collections import Counter
from copy import deepcopy
import argparse
import json
from pathlib import Path
import random
from statistics import mean, median

from run import ENVIRONMENTS, MODES, NAMES, SEEDS, design, fixture, snapshot

SLOT = 1450


def load(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def totals(order, staged):
    stock = Counter()
    for part in staged:
        stock.update(order["parts"][part]["items"])
    return dict(stock)


def check_phase(turn, trial, root, due):
    seconds = (turn["turn"] - 1) * trial["step"]
    if seconds not in (trial["close"], trial["reopen"]):
        require(turn["phase"] is None, "Unexpected station change")
        return
    label = "close" if seconds == trial["close"] else "reopen"
    proof = load(root / f"{label}.json")
    want = "air" if trial["environment"] == "outage" and label == "close" else "crafting_table"
    tag = next(iter(trial["players"].values()))
    require(turn["phase"] == proof and proof["target"] == due and proof["block"] == want,
            "Station state disagrees with the experimental phase")
    require(due <= proof["sent"] <= proof["ack"] < due + 2500, "Station change missed the scheduled turn")
    require(f"[Server] PHASE_{tag}_{label}_{want}" in proof["evidence"], "Missing authentic server marker")


def check_prompt(text, trial, name, turn, before, unavailable, previous):
    require(text.startswith(f"You are {name}. Turn {turn}.")
            and f'Closed assembly bench: {unavailable or "none"}.' in text, "Prompt clock or identity mismatch")
    lines = text.splitlines()
    prep, assemble, ready = [], [], []
    for id, order in trial["orders"].items():
        row = before[id]
        label = f'{id} {order["item"]} x{order["quantity"]}'
        if row["done"]:
            require(f"{label} delivered" in lines, "Delivered order missing from public board")
            continue
        parts = " ".join(f'{part}:{batch["cook"]}{"+" if part in row["parts"] else ""}'
                         for part, batch in order["parts"].items())
        require(f'{label} owner={row["owner"]} batches={parts}' in lines, "Public order board drifted")
        prep.extend(f"{id}.{part}" for part, batch in order["parts"].items()
                    if batch["cook"] == name and part not in row["parts"])
        if len(row["parts"]) == len(order["parts"]):
            ready.append(f'{id}={row["owner"]}')
            if row["owner"] == name != unavailable:
                assemble.append(id)
    # The first unscored interface preflight preceded these three derived lists.
    if trial["duration"] == 360 or "Your legal prep jobs:" in text:
        for label, jobs in (("Ready orders (owner)", ready), ("Your legal prep jobs", prep),
                            ("Your legal assembly jobs", assemble)):
            require(f'{label}: {", ".join(jobs) or "none"}' in lines, "Derived action list drifted")
    require(text.endswith(f'Previous actions and open chat: {" | ".join(previous) or "none"}'),
            "Previous-turn chat was not visible")


def replay(root, trial):
    trace = load(root / "trace.json")
    scripted = trial["scripted"]
    require(trace["model"] == ("scripted" if scripted else "gpt-6-luna"), "Unexpected model")
    require(trace["slot"] == SLOT, "Token slot was changed")
    start, deadline = trace["start"], trace["deadline"]
    require(start == load(root / "start.json")["start"] and deadline == start + trial["duration"] * 1000,
            "Terminal clock mismatch")
    orders = trial["orders"]
    state = {id: {"owner": row["owner"], "parts": [], "done": False} for id, row in orders.items()}
    staged_times, assembly, delivered = {}, {}, {}
    routed = []
    accepted = 0
    errors, outcomes, route_statuses, crafts_by = Counter(), Counter(), Counter(), Counter()
    used, reserved, responses = 0, 0, 0
    previous = []
    for index, turn in enumerate(trace["turns"]):
        seconds = index * trial["step"]
        due = start + seconds * 1000
        require(turn["turn"] == index + 1 and turn["due"] == due and due < deadline, "Turn cadence mismatch")
        closing = trial["environment"] == "outage" and trial["close"] <= seconds < trial["reopen"]
        unavailable = trial["affected"] if closing else None
        require(turn["unavailable"] == unavailable, "Wrong workstation availability")
        check_phase(turn, trial, root, due)
        before = deepcopy(state)
        require(turn["before"] == before and [row["name"] for row in turn["attempts"]] == list(NAMES),
                "Board is inconsistent with previous actions")
        for row in turn["attempts"]:
            decision, outcome, name = row["decision"], row["outcome"], row["name"]
            check_prompt(row["input"], trial, name, index + 1, before, unavailable, previous)
            outcomes[outcome] += 1
            if decision["status"] in ("completed", "incomplete"):
                responses += 1
                if decision["status"] == "incomplete":
                    errors["response_incomplete"] += 1
            elif decision["status"] != "scripted":
                errors[decision["status"]] += 1
            if "tokens" in decision:
                require(all(0 <= n <= SLOT for n in decision["tokens"])
                        and sum(decision["tokens"]) == decision["reserved"], "Invalid token count")
                used += sum(decision["tokens"])
            require(0 <= decision["reserved"] <= SLOT, "Per-decision ceiling exceeded")
            reserved += decision["reserved"]
            if outcome not in ("staged", "delivered"):
                continue
            require(seconds * 1000 <= row["started"] <= row["at"] < deadline - start, "Late stage or output")
            action = decision["action"]
            id, *part = action["job"].split(".")
            order, current = orders[id], state[id]
            if outcome == "staged":
                require(action["act"] == "prep" and len(part) == 1, "Invalid preparation action")
                batch = part[0]
                require(order["parts"][batch]["cook"] == name and batch not in current["parts"]
                        and not current["done"], "Illegal material transfer")
                current["parts"].append(batch)
                current["parts"].sort()
                require(row["chest"] == totals(order, current["parts"]), "Deposited stock mismatch")
                if len(current["parts"]) == len(order["parts"]):
                    staged_times[id] = row["at"]
            else:
                require(action["act"] == "assemble" and not part and name != unavailable
                        and before[id]["owner"] == name and not current["done"]
                        and len(before[id]["parts"]) == len(order["parts"]), "Illegal assembly")
                require(row["chest"] == {order["item"]: order["quantity"]}, "Wrong crafted amount")
                current["done"] = True
                assembly[id] = row["started"]
                delivered[id] = row["at"]
                crafts_by[name] += 1
        grants = 0
        for route in turn["routes"]:
            status, actor, id, recipient = (route[key] for key in ("status", "who", "order", "to"))
            route_statuses[status] += 1
            if status != "routed":
                continue
            require((trial["mode"] == "peer" and actor == recipient)
                    or (trial["mode"] == "leader" and actor == trial["leader"])
                    or (trial["mode"] == "dispatch" and actor == "rule"), "Unauthorized reassignment")
            require(not state[id]["done"] and len(before[id]["parts"]) == len(orders[id]["parts"])
                    and route["from"] == state[id]["owner"] != recipient and recipient in NAMES, "Illegal reassignment")
            state[id]["owner"] = recipient
            grants += 1
            accepted += 1
            routed.append(id)
        require(grants <= 1 and turn["done"] == [id for id in orders if state[id]["done"]], "Board update failed")
        previous = []
        for actor in turn["attempts"]:
            action = actor["decision"]["action"] or {}
            line = (f'{actor["name"]} {action.get("act", "none")} {action.get("job", "")} '
                    f'{actor["outcome"]} {action.get("say", "")}')
            previous.append(line.strip())
    complete = len(delivered) == len(orders)
    finish = start + max(delivered.values()) if complete else None
    require(trace["finish"] == finish and sorted(trace["done"]) == sorted(delivered), "Final trace mismatch")
    require(complete or len(trace["turns"]) == trial["duration"] // trial["step"], "Incomplete observation window")
    require(used <= reserved <= SLOT * len(NAMES) * trial["duration"] // trial["step"], "Team cap exceeded")
    if not scripted:
        require(responses > 0, "No usable provider service in this trial")
    return state, staged_times, assembly, delivered, {
        "accepted": accepted, "routed_delivered": len(set(routed) & set(delivered)),
        "outcomes": dict(outcomes), "crafts_by": dict(crafts_by), "route_statuses": dict(route_statuses),
        "model_errors": dict(errors), "responses": responses, "tokens": used, "reserved_tokens": reserved,
        "elapsed": (finish - start) / 1000 if finish else trial["duration"],
    }


def score(root, kind, expected):
    trial = load(root / "trial.json")
    lane = (trial["home"][0] - 64) // 84
    attempt = int(root.name.split("-attempt")[-1]) if "-attempt" in root.name else 1
    require(trial == fixture(*expected, lane, attempt, kind), f"Scenario drift in {root.name}")
    state, staged, assembly, delivered, summary = replay(root, trial)
    data = load(root / "complete.json")
    raw = (root / "server-sample.txt").read_text()
    for name in trial["players"].values():
        require(raw.count(f"{name} joined the game") == 1, f"No matching Minecraft join for {name}")
    stock = snapshot(raw, trial)
    verify = {id: {order["item"]: order["quantity"]} if state[id]["done"] else totals(order, state[id]["parts"])
              for id, order in trial["orders"].items()}
    require(stock == verify == data["terminal"] and sorted(delivered) == data["done"]
            and summary["elapsed"] == data["elapsed"], "Server stock disagrees with traced transfers or crafts")
    watch = {}
    cutoff = trial["duration"] * 1000
    for id, order in trial["orders"].items():
        if order["owner"] != trial["affected"] or id not in staged:
            continue
        begin = max(staged[id], trial["close"] * 1000)
        if begin >= trial["reopen"] * 1000 or assembly.get(id, cutoff) < begin:
            continue
        end = assembly.get(id, cutoff)
        watch[id] = {"ready": staged[id] / 1000, "assembly": assembly[id] / 1000 if id in assembly else None,
                     "wait": (end - begin) / 1000, "capped": id not in assembly,
                     "delivered_in_window": delivered.get(id, cutoff) < trial["reopen"] * 1000}
    return {"seed": trial["seed"], "mode": trial["mode"], "environment": trial["environment"], "dir": root.name,
            "affected": trial["affected"], "leader": trial["leader"], "orders": len(delivered),
            "completed": len(delivered) == len(trial["orders"]), "done": sorted(delivered),
            "watched_orders": watch, **summary}


def percentile(values, share):
    offset = (len(values) - 1) * share
    index = int(offset)
    return values[index] + (offset - index) * (values[min(index + 1, len(values) - 1)] - values[index])


def contrast(values):
    rng = random.Random(41614)
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(20_000))
    return {"values": values, "mean": mean(values),
            "interval": [percentile(samples, 0.025), percentile(samples, 0.975)]}


def pooling(rows):
    def aggregate(key):
        total = Counter()
        for row in rows:
            total.update(row[key])
        return dict(total)

    finish = [row["elapsed"] for row in rows if row["completed"]]
    orders = [row["orders"] for row in rows]
    watched = [watch for row in rows for watch in row["watched_orders"].values()]
    return {"runs": len(rows), "full": len(finish), "mean_orders": mean(orders), "range_orders": [min(orders), max(orders)],
            "finish_median": median(finish) if finish else None,
            "finish_range": [min(finish), max(finish)] if finish else None,
            "capped_mean": mean(row["elapsed"] for row in rows), "accepted": sum(row["accepted"] for row in rows),
            "routed_delivered": sum(row["routed_delivered"] for row in rows),
            "responses": sum(row["responses"] for row in rows), "tokens": sum(row["tokens"] for row in rows),
            "outcomes": aggregate("outcomes"), "route_statuses": aggregate("route_statuses"),
            "model_errors": aggregate("model_errors"),
            "watched_count": len(watched), "watched_in_window": sum(row["delivered_in_window"] for row in watched),
            "watched_capped": sum(row["capped"] for row in watched),
            "watched_median_wait": median(row["wait"] for row in watched) if watched else None}


def analyze(root):
    manifest = load(root / "design.json")
    kind = manifest["kind"]
    expected = design(kind)
    require(manifest["cases"] == [list(case) for case in expected], "Study cases do not match the design")
    files = sorted(path.parent for path in root.glob("*/complete.json"))
    used = set()
    rows = []
    for case in sorted(expected):
        label = "-".join(map(str, case))
        matches = [path for path in files if path.name == label or path.name.startswith(label + "-attempt")]
        require(len(matches) == 1, f"Expected exactly one verified terminal record for {label}")
        path = matches[0]
        rows.append(score(path, kind, case))
        used.add(path)
    require(used == set(files), "Unexpected completed trials")
    groups = {f"{mode}-{env}": pooling([row for row in rows if row["mode"] == mode and row["environment"] == env])
              for mode, env in sorted({(row["mode"], row["environment"]) for row in rows})}
    if kind == "probe":
        require(groups["fixed-outage"]["accepted"] == 0
                and groups["fixed-outage"]["route_statuses"].get("forbidden", 0) > 0,
                "Fixed ownership authorization was not exercised")
        for rule in ("peer", "leader"):
            require(groups[f"{rule}-outage"]["routed_delivered"] > 0,
                    "Smoke test did not prepare, reroute, and deliver actual food")
    pairs, timing = {}, {}
    if kind == "main":
        scores = {(r["seed"], r["mode"], r["environment"]): r["orders"] for r in rows}
        for environment in ENVIRONMENTS:
            for a, b in (("leader", "peer"), ("peer", "fixed"), ("leader", "fixed")):
                pairs[f"{a}_minus_{b}_{environment}"] = contrast(
                    [scores[seed, a, environment] - scores[seed, b, environment] for seed in SEEDS])
        for a, b in (("leader", "peer"), ("peer", "fixed"), ("leader", "fixed")):
            pairs[f"{a}_minus_{b}_interaction"] = contrast([
                disrupted - normal for disrupted, normal in zip(pairs[f"{a}_minus_{b}_outage"]["values"],
                                                                 pairs[f"{a}_minus_{b}_normal"]["values"])])
        elapsed = {(r["seed"], r["mode"], r["environment"]): r["elapsed"] for r in rows}
        for env in ENVIRONMENTS:
            timing[env] = contrast([round(elapsed[s, "leader", env] - elapsed[s, "peer", env], 3) for s in SEEDS])
        timing["interaction"] = contrast([round(disrupted - normal, 3) for disrupted, normal in
                                         zip(timing["outage"]["values"], timing["normal"]["values"])])
    return {"kind": kind, "groups": groups, "contrasts_orders": pairs,
            "leader_minus_peer_seconds": timing,
            "dispatch_trigger": bool(pairs and pairs["leader_minus_peer_outage"]["mean"] >= 0.5
                                     and pairs["leader_minus_peer_interaction"]["mean"] > 0), "trials": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.root), indent=2, sort_keys=True))
