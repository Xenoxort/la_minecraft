"""Extract earned recipe cards and distill a bounded playbook from teacher trials."""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from analyze import check_material, need, read, training_ledger, verify_batch
from scenario import LESSONS, TEACHER, dump


def summarize(trials, key_path):
    ledger = training_ledger(trials)
    instructions = (
        "Select three useful general discovery procedures for a junior kitchen student. "
        "The teacher solved hidden three-shelf recipes using a clue about the sum of ranks and exact-match "
        "counts. Each training ledger row gives order, turn, tried triple, exact matches, and candidates left. "
        "Look at what worked across these runs, including failed tests. Pick only from the provided procedures "
        "and cite a real training observation that supports each one. Return only JSON shaped as "
        '{"evidence":[{"lesson":"procedure key","seed":123,"order":"o1","turn":1}]} '
        "with exactly three distinct lessons. Do not give any ingredients, recipes or other prose."
    )
    body = {"model": TEACHER, "reasoning": {"effort": "low"}, "instructions": instructions,
            "input": json.dumps({"available_procedures": LESSONS, "teacher_training_ledgers": ledger}),
            "max_output_tokens": 2250, "store": False}
    key = read(key_path)
    headers = {"Authorization": "Bearer " + key["OPENAI_API_KEY"], "Content-Type": "application/json"}
    if key.get("OPENAI_ORG_ID"):
        headers["OpenAI-Organization"] = key["OPENAI_ORG_ID"]
    request = Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(), headers=headers)
    try:
        with urlopen(request, timeout=70) as res:
            result = json.load(res)
    except HTTPError as error:
        raise RuntimeError(f"Teacher summary request failed with HTTP {error.code}") from None
    need(result["status"] == "completed" and result["model"] == TEACHER, "Teacher summary did not complete")
    text = "".join(part["text"] for msg in result["output"] if msg["type"] == "message"
                   for part in msg["content"] if part["type"] == "output_text")
    parsed = json.loads(text[text.index("{"):text.rindex("}")+1])
    entries = [{k: entry[k] for k in ("lesson", "seed", "order", "turn")} for entry in parsed["evidence"]]
    metadata = {"model": TEACHER, "usage": result["usage"], "instructions": instructions, "ledger": ledger}
    return entries, metadata


def derive(teacher, key, output):
    if output.exists():
        trials = verify_batch(teacher, "teacher")
        check_material(read(output), trials)
        return
    trials = verify_batch(teacher, "teacher")
    evidence, metadata = summarize(trials, key)
    materials = {
        "cards": {str(row["seed"]): dict(sorted(done.items())) for row, done, _ in trials},
        "playbook": [row["lesson"] for row in evidence],
        "evidence": evidence,
        "synthesis": metadata,
    }
    check_material(materials, trials)
    dump(output, materials)
    print(f"Extracted {sum(map(len, materials['cards'].values()))} teacher-verified recipe cards.", flush=True)
    print("Teacher selected " + ", ".join(materials["playbook"]), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("teacher", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--key", type=Path, default=Path("/tmp/transfer-keys.json"))
    args = parser.parse_args()
    derive(args.teacher, args.key, args.output)
