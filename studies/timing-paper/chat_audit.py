"""Count observable relay patterns for exploratory transcript review."""
import argparse
import json
from pathlib import Path
import re
import unicodedata

COMMAND = re.compile(r"^!\w+(?:\(.*\))?$", re.DOTALL)
START = re.compile(r'^!startConversation\("[^"]+",\s*("(?:[^"\\]|\\.)*")\)$')
ACTION = re.compile(r"\s+!\w+(?:\(.*\))?$", re.DOTALL)


def content(message):
    message = message.strip()
    wrapped = START.match(message)
    if wrapped:
        try:
            message = json.loads(wrapped.group(1))
        except json.JSONDecodeError:
            pass
    elif COMMAND.fullmatch(message):
        return ""
    return " ".join(unicodedata.normalize("NFKC", ACTION.sub("", message)).casefold().split())


def summarize(path):
    source = [json.loads(line) for line in path.read_text().splitlines()]
    rows = [r for r in source if r["event"] == "chat"]
    seen = set()
    counts = dict(messages=len(rows), command_only=0, exact_repeat=0)
    examples = []
    for row in rows:
        message = content(row["message"])
        if not message:
            if row["message"].strip():
                counts["command_only"] += 1
            continue
        key = row["sender"], row["receiver"], message
        if key in seen:
            counts["exact_repeat"] += 1
            if len(examples) < 3:
                examples.append({"sender": row["sender"], "message": row["message"]})
        seen.add(key)
    return {"episode": path.parent.name, **counts, "first_repeat_examples": examples}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps([summarize(p) for p in sorted(args.root.glob("*/events.jsonl"))], indent=2))


if __name__ == "__main__":
    main()
