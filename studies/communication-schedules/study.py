"""Run the matched communication-schedule pilot on private and public puzzles."""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPSConnection, HTTPException
from itertools import combinations, product
import json
from pathlib import Path
import random
from statistics import mean
import string
import time
from threading import local

MODEL = "gpt-6-luna"
PERIODS = 10
WORK_UNITS = 8
TOKEN_UNIT = 960
REASONING = "none"
SIZES = (2, 4, 8)
SEEDS = (1937, 5182)
SCHEDULES = {
    "A": (),
    "B": tuple(range(1, PERIODS + 1)),
    "C": (2, 4, 7, 9),
    "D": (2, 3, 8, 9),
    "E": (1, 6, 9, 10),
    "F": (1, 2, 5, 10),
}
LETTERS = string.ascii_uppercase[:16]
INSTRUCTIONS = """Select a subset of project letters. Maximize total benefit within both resource limits and every known rule. “XY clash” prohibits taking both. “X needs Y” prohibits taking X without Y. Missing rules may exist in a distributed task. Submit your best candidate for THIS attempt, including an empty string for no projects. You may test candidates and improve them using your private feedback. You will retain your latest attempt, the strongest valid attempt you have made under visible rules, and an editable private memory. Keep memory under 88 characters and preserve useful reasoning in it. Any relayed plans are ideas, not verified facts. Other agents see candidate plans and constraint cards only when the channel opens. Choose project letters only using the task data. Return only a JSON object with keys plan and memory. No Markdown, code, or explanatory text."""
FORMAT = {"type": "json_schema", "name": "proposal", "strict": True, "schema": {
    "type": "object", "properties": {"plan": {"type": "string"}, "memory": {"type": "string"}},
    "required": ["plan", "memory"], "additionalProperties": False,
}}


def puzzle(seed):
    rng = random.Random(seed)
    items = {c: (rng.randint(4, 18), rng.randint(2, 9), rng.randint(2, 9)) for c in LETTERS}
    pairs = rng.sample(list(combinations(LETTERS, 2)), 8)
    rules = [(("clash" if i < 4 else "needs"), *pair) for i, pair in enumerate(pairs)]
    return {"items": items, "limits": [28, 27], "rules": rules}


def evaluate(problem, plan, known):
    benefits, first, second = (sum(problem["items"][c][i] for c in plan) for i in range(3))
    errors = []
    if first > problem["limits"][0]:
        errors.append("labor")
    if second > problem["limits"][1]:
        errors.append("material")
    for i in known:
        rel, x, y = problem["rules"][i]
        if x in plan and ((y in plan) == (rel == "clash")):
            errors.append(f"rule{i + 1}")
    return {"value": benefits, "labor": first, "material": second, "errors": errors}


def optimum(problem):
    known = range(len(problem["rules"]))
    top = 0
    for count in range(len(LETTERS) + 1):
        for subset in combinations(LETTERS, count):
            score = evaluate(problem, subset, known)
            if not score["errors"]:
                top = max(top, score["value"])
    return top


def rule_text(rule):
    relation, x, y = rule
    return f"{x}{y} clash" if relation == "clash" else f"{x} needs {y}"


def make_agents(regime, n, problem):
    cards = range(len(problem["rules"]))
    return [{"own": set(cards if regime == "public" else cards[i::n]), "peer_cards": set(),
             "peers": {}, "plans": [], "memory": "", "last": None}
            for i in range(n)]


def relay(agents):
    for receiver, agent in enumerate(agents):
        for sender, peer in enumerate(agents):
            if receiver == sender:
                continue
            agent["peer_cards"].update(peer["own"])
            if peer["last"] is not None:
                agent["peers"].setdefault(sender, {}).setdefault(peer["last"], None)


def known(agent):
    return sorted(agent["own"] | agent["peer_cards"])


def local_best(problem, agent):
    cards = known(agent)
    scores = [(plan, evaluate(problem, plan, cards)) for plan in agent["plans"]]
    valid = [(score["value"], plan) for plan, score in scores if not score["errors"]]
    return max(valid, default=(0, ""))[1]


def prompt(problem, regime, agent, actor, period, step, is_open):
    items = " ".join(f"{c}:{'/'.join(map(str, triple))}" for c, triple in problem["items"].items())
    cards = "; ".join(rule_text(problem["rules"][i]) for i in known(agent)) or "none"
    feedback = "none"
    if agent["last"] is not None:
        q = evaluate(problem, agent["last"], known(agent))
        errors = [rule_text(problem["rules"][int(e[4:]) - 1]) if e.startswith("rule") else e
                  for e in q["errors"]]
        feedback = (f"{agent['last'] or 'empty'} value={q['value']} labor={q['labor']} "
                    f"material={q['material']} violations={','.join(errors) or 'none'}")
    peers = " ".join(f"p{i + 1}:" + ",".join(p or "-" for p in plans)
                     for i, plans in sorted(agent["peers"].items())) or "none"
    return (
        f"{regime} puzzle; agent {actor + 1}; period {period}/{PERIODS}, attempt {step + 1}; "
        f"relay {'OPEN' if is_open else 'CLOSED'}.\n"
        f"Project:benefit/labor/material {items}\n"
        f"Limits labor={problem['limits'][0]} material={problem['limits'][1]}. Rules you know: {cards}.\n"
        f"Your latest attempt: {feedback}. Your own best visible-valid plan: {local_best(problem, agent) or 'none'}.\n"
        f"Your private memory: {agent['memory'] or 'none'}.\nPreviously received peer plans: {peers}."
    )


def parse_reply(answer):
    answer = answer.strip()
    if answer.startswith("```") and answer.endswith("```"):
        answer = answer.partition("\n")[2][:-3].strip()
    try:
        data = json.loads(answer)
    except ValueError:
        return None, None
    if not isinstance(data, dict) or not all(isinstance(data.get(k), str) for k in ("plan", "memory")):
        return None, None
    candidate = "".join(c for c in data["plan"].upper() if c not in " ,\t\n")
    plan = ("".join(sorted(candidate))
            if len(set(candidate)) == len(candidate) and all(c in LETTERS for c in candidate) else None)
    return plan, " ".join(data["memory"].split())[:88]


def no_reply(status, reserved, elapsed, retries):
    return {"plan": None, "memory": None, "status": status, "usage": None,
            "reserved_tokens": reserved, "generation_seconds": elapsed, "provider_retries": retries}


class Provider:
    def __init__(self, keyfile):
        config = json.loads(keyfile.read_text())
        self.connections = local()
        self.headers = {"Authorization": "Bearer " + config["OPENAI_API_KEY"], "Content-Type": "application/json"}
        if config.get("OPENAI_ORG_ID"):
            self.headers["OpenAI-Organization"] = config["OPENAI_ORG_ID"]

    def request(self, suffix, payload):
        for attempt in range(3):
            try:
                if not hasattr(self.connections, "session"):
                    self.connections.session = HTTPSConnection("api.openai.com", timeout=40)
                connection = self.connections.session
                connection.request("POST", "/v1/responses" + suffix, json.dumps(payload), self.headers)
                response = connection.getresponse()
                body = response.read()
            except (OSError, HTTPException):
                self.connections.session.close()
                del self.connections.session
                if not suffix:
                    return None, attempt
                if attempt == 2:
                    return {"failed": "input_count_unavailable"}, attempt
                time.sleep(2 ** attempt)
                continue
            if response.status == 200:
                return json.loads(body), attempt
            if response.status == 429 or (suffix and response.status in (502, 503, 504)):
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
            if not suffix and response.status in (502, 503, 504):
                return None, attempt
            if response.status in (429, 502, 503, 504) and suffix:
                return {"failed": "input_count_unavailable"}, attempt
            kind = json.loads(body).get("error", {}).get("code")
            if kind == "invalid_prompt" or response.status == 429:
                return {"failed": "provider_rejected"}, attempt
            raise RuntimeError(f"Provider {suffix or 'generation'} HTTP {response.status} ({kind})")
        raise AssertionError("Missing provider response")

    def attempt(self, body):
        payload = {"model": MODEL, "instructions": INSTRUCTIONS, "input": body, "text": {"format": FORMAT},
                   "reasoning": {"effort": REASONING}}
        token_count, count_retries = self.request("/input_tokens", payload)
        if "failed" in token_count:
            return no_reply(token_count["failed"], 0, 0, count_retries)
        token_in = token_count["input_tokens"]
        remaining = TOKEN_UNIT - token_in
        if remaining < 64:
            raise RuntimeError(f"Context consumed {token_in} of {TOKEN_UNIT} reserved tokens")
        started = time.monotonic()
        result, retries = self.request("", {**payload, "max_output_tokens": remaining, "store": False})
        elapsed = round(time.monotonic() - started, 4)
        if result is None:
            # The server may have billed an accepted generation. Reserve its full slot.
            return no_reply("transport_unknown", TOKEN_UNIT, elapsed, retries + count_retries)
        if "failed" in result:
            return no_reply(result["failed"], TOKEN_UNIT, elapsed, retries + count_retries)
        usage = result["usage"]
        if (result["model"] != MODEL or usage["input_tokens"] != token_in
                or usage["total_tokens"] > TOKEN_UNIT
                or usage["total_tokens"] != token_in + usage["output_tokens"]):
            raise RuntimeError(f"Provider usage violated token reservation: expected {token_in}, usage {usage}")
        answer = "".join(p["text"] for item in result["output"] if item["type"] == "message"
                         for p in item["content"] if p["type"] == "output_text")
        plan, memory = None, None
        if result["status"] == "completed" and answer:
            plan, memory = parse_reply(answer)
        return {"plan": plan, "memory": memory, "status": result["status"],
                "unparsed_excerpt": answer[:200] if plan is None and answer else None,
                "usage": {"input": token_in, "output": usage["output_tokens"], "total": usage["total_tokens"],
                          "reasoning": usage.get("output_tokens_details", {}).get("reasoning_tokens", 0)},
                "reserved_tokens": usage["total_tokens"],
                "generation_seconds": round(time.monotonic() - started, 4),
                "provider_retries": retries + count_retries}


def score(problem, top, plan):
    result = evaluate(problem, plan, range(len(problem["rules"])))
    return result["value"] / top if not result["errors"] else 0


def experiment_design(adaptive=False):
    modes = ("G",) if adaptive else tuple(SCHEDULES)
    cells = list(product(SEEDS, ("public", "distributed"), SIZES, modes))
    random.Random(11793).shuffle(cells)
    return cells


def adaptive_open(period, rounds, regime):
    used = sum(r["open"] for r in rounds)
    if used == 4:
        return False
    if PERIODS - period + 1 == 4 - used:
        return True
    if period == 1:
        return regime == "distributed"
    if period < 3 or rounds[-1]["open"]:
        return False
    previous, latest = rounds[-2:]
    return (latest["observable_best"] <= previous["observable_best"]
            and latest["observable_diversity"] >= 2)


async def episode(cell, problem, top, provider, output, pool):
    seed, regime, n, mode = cell
    agents = make_agents(regime, n, problem)
    rounds = []
    loop = asyncio.get_running_loop()
    started = time.monotonic()
    name = f"{seed}-{regime}-{n}-{mode}"
    for period in range(1, PERIODS + 1):
        rows = []
        is_open = (adaptive_open(period, rounds, regime) if mode == "G" else period in SCHEDULES[mode])
        for step in range(WORK_UNITS // n):
            if is_open:
                relay(agents)
            inputs = [prompt(problem, regime, a, i, period, step, is_open) for i, a in enumerate(agents)]
            calls = await asyncio.gather(*(loop.run_in_executor(pool, provider.attempt, body) for body in inputs))
            for i, (agent, row) in enumerate(zip(agents, calls)):
                row.update(agent=i, step=step, known=known(agent),
                           peers={str(j): list(p) for j, p in agent["peers"].items()}, input=inputs[i])
                if row["plan"] is not None:
                    agent["last"] = row["plan"]
                    agent["plans"].append(row["plan"])
                if row["memory"] is not None:
                    agent["memory"] = row["memory"]
                rows.append(row)
        candidates = [local_best(problem, a) for a in agents]
        observable = [evaluate(problem, plan, ()) for plan in candidates]
        rounds.append({"period": period, "open": is_open, "attempts": rows, "candidates": candidates,
                       "observable_best": max(s["value"] for s in observable if not s["errors"]),
                       "observable_diversity": len(set(candidates))})
        if period == 1:
            print(f"Started {name}; first period recorded", flush=True)
    result = {"seed": seed, "information": regime, "agents": n, "schedule": mode, "model": MODEL,
              "budget": PERIODS * WORK_UNITS * TOKEN_UNIT, "optimum": top, "rounds": rounds,
              "wall_seconds": round(time.monotonic() - started, 4)}
    target = output / f"{name}.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(result, separators=(",", ":")) + "\n")
    temp.rename(target)
    return target.name


async def run(args):
    provider = Provider(args.key_file)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    cells = experiment_design(args.adaptive)
    if args.probe:
        cells = [(SEEDS[0], "distributed", 8, "B")]
    tasks = {seed: puzzle(seed) for seed in SEEDS}
    tops = {seed: optimum(problem) for seed, problem in tasks.items()}
    manifest = {"model": MODEL, "reasoning": REASONING, "per_call_tokens": TOKEN_UNIT, "periods": PERIODS, "work_per_period": WORK_UNITS,
                "cells": cells, "schedules": SCHEDULES, "problems": tasks, "optima": tops}
    manifest_path = output / "manifest.json"
    encoded = json.dumps(manifest, indent=2) + "\n"
    if manifest_path.exists() and manifest_path.read_text() != encoded:
        raise RuntimeError("Output directory already has a different experiment manifest")
    manifest_path.write_text(encoded)
    queue = asyncio.Queue()
    for seed, regime, n, mode in cells:
        if not (output / f"{seed}-{regime}-{n}-{mode}.json").exists():
            queue.put_nowait((seed, regime, n, mode))

    async def worker(pool):
        while not queue.empty():
            seed, regime, n, mode = queue.get_nowait()
            name = await episode((seed, regime, n, mode), tasks[seed], tops[seed], provider, output, pool)
            print(f"Completed {name} at {time.strftime('%H:%M:%S', time.gmtime())} UTC", flush=True)

    with ThreadPoolExecutor(max_workers=args.requests) as pool:
        async with asyncio.TaskGroup() as group:
            for _ in range(min(args.episodes, queue.qsize())):
                group.create_task(worker(pool))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--key-file", required=True, type=Path)
    parser.add_argument("--episodes", type=int, default=12)
    parser.add_argument("--requests", type=int, default=42)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--adaptive", action="store_true")
    mode.add_argument("--probe", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
