#!/usr/bin/env bash
# Load only source needed by the runner. Never copy the checkout's ignored files.
set -euo pipefail
container=$1
revision=$2
stage=$(mktemp -d)
files=(
    src/agent/agent.js src/agent/conversation.js src/mindcraft/mindserver.js
    src/agent/commands/index.js src/models/gpt.js src/models/prompter.js
    studies/communication-timing/run.py studies/communication-timing/control.js
)
git archive "$revision" -- "${files[@]}" studies/timing-paper | tar -xf - -C "$stage"
docker exec "$container" mkdir -p /app/studies/timing-paper /app/studies/communication-timing
for path in "${files[@]}"; do
    docker cp "$stage/$path" "$container:/app/$path"
done
for path in "$stage"/studies/timing-paper/*; do
    if [[ -f "$path" ]]; then
        docker cp "$path" "$container:/app/studies/timing-paper/"
    fi
done
# Staging contains public source only.
find "$stage" -depth -type f -delete
find "$stage" -depth -type d -empty -delete
