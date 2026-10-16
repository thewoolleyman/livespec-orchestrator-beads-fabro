#!/usr/bin/env bash
# Take a candidate canary: file a fresh canary work-item from the committed
# fixture template, then dispatch that item to the NAMED factory.
#
# A canary is a measurement of the ENGINE, so the two things that must not vary
# between canaries are the brief and the factory. The brief comes from
# `orchestrator-image/canary-fixture.md` and cannot be supplied here; the factory
# is this script's one argument and cannot be omitted, so no canary silently
# lands on `dispatcher.default_factory` and gets read as evidence about the
# candidate.
#
# Run it under this project's configured credential wrapper, per the beads
# prerequisites in AGENTS.md:
#
#   with-livespec-env.sh -- mise exec -- just canary-dispatch hp
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo ":: canary-dispatch: expected exactly one argument, the factory name" >&2
    echo ":: canary-dispatch: usage: just canary-dispatch <factory>" >&2
    exit 2
fi
factory=$1

# STDOUT carries the filed id and nothing else, so the capture is the whole
# handoff between the two commands; the subcommand's narration is on stderr and
# reaches the operator untouched.
item="$(uv run python3 .claude-plugin/scripts/bin/dispatcher.py file-canary --repo .)"
if [[ -z $item ]]; then
    echo ":: canary-dispatch: no canary work-item id was printed; nothing dispatched" >&2
    exit 1
fi
echo ":: canary-dispatch: filed canary $item from orchestrator-image/canary-fixture.md"
echo ":: canary-dispatch: dispatching it to factory $factory"
uv run python3 .claude-plugin/scripts/bin/dispatcher.py dispatch \
    --repo . --item "$item" --factory "$factory"
