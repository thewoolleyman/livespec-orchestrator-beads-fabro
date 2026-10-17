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
# THE NAME IS ALSO GRADED, NOT JUST ITS PRESENCE. Requiring the argument closes
# omission; it leaves the strictly worse case open, because an UNDECLARED name is
# not an error downstream — `_factory_entry` answers `{}` for one, so the target
# resolves with no server and the dispatch lands on the ambient local engine at
# `127.0.0.1:32276`. The run is then read as evidence about the candidate the
# name meant, which is the item-quality-failure-reading-as-engine-failure this
# whole recipe exists to remove, one layer up. Only `hp` is committed, so
# `just canary-dispatch hp-candidate` — the likeliest invocation of a CANDIDATE
# canary recipe — is exactly the case that misfires whenever the host-side entry
# is absent or the name is mistyped.
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

# Grade the name BEFORE `file-canary`, so a typo does not also strand a filed
# canary at the top of the ready queue for a concurrent drain to select.
#
# The three outcomes are kept apart deliberately. An UNREADABLE `.livespec.jsonc`
# must not read as "your factory is undeclared" — `dispatcher_block`'s own
# docstring warns about exactly that confusion, and it RAISES rather than
# answering False so the two stay distinguishable. A repository that declares no
# `factories` block at all constrains no name, which is how an adopter keeps
# today's ambient behaviour; that is the `has_fabro_factories` guard, and it is
# the same reading `_usable_recorded_factory` takes one branch over when it
# discards a recorded pin that is no longer declared.
#
# The codes deliberately SKIP 1: `python3 -c` exits 1 on any uncaught exception,
# so a probe that signalled a real verdict with 1 would report an ImportError as
# "your factory is undeclared, and this repository declares none" — a confident,
# plausible, wrong-cause refusal. Every unexpected status is reported as the
# probe's own failure instead, which is the one reading that stays truthful when
# the probe cannot run at all.
#
#   0 = usable   3 = declared, and this is not one   4 = unreadable config
factory_probe='
import sys
from pathlib import Path

sys.path.insert(0, ".claude-plugin/scripts")
from livespec_orchestrator_beads_fabro.commands._config import (
    dispatcher_block,
    has_fabro_factories,
    has_fabro_factory,
)
from livespec_orchestrator_beads_fabro.errors import LivespecConfigUnreadableError

name = sys.argv[1]
here = Path(".")
try:
    if not has_fabro_factories(cwd=here):
        raise SystemExit(0)
    if has_fabro_factory(cwd=here, factory=name):
        raise SystemExit(0)
    declared = sorted(dispatcher_block(cwd=here)["factories"])
except LivespecConfigUnreadableError as unreadable:
    print(unreadable.detail)
    raise SystemExit(4) from None
print(", ".join(declared) if declared else "none")
raise SystemExit(3)
'

set +e
probe_output="$(uv run python3 -c "$factory_probe" "$factory")"
probe_status=$?
set -e

case "$probe_status" in
    0) ;;
    3)
        echo ":: canary-dispatch: $factory is not a factory this repository declares;" \
            "nothing was filed and nothing was dispatched" >&2
        echo ":: canary-dispatch: declared factories: $probe_output" >&2
        echo ":: canary-dispatch: an undeclared name resolves to the ambient local engine," \
            "whose run would be read as evidence about $factory" >&2
        echo ":: canary-dispatch: declare its entry under dispatcher.factories, then re-run" >&2
        exit 1
        ;;
    4)
        echo ":: canary-dispatch: the declared factories could not be read, so $factory could" \
            "not be graded; nothing was filed and nothing was dispatched" >&2
        echo ":: canary-dispatch: $probe_output" >&2
        exit 1
        ;;
    *)
        echo ":: canary-dispatch: the factory probe failed with status $probe_status, so" \
            "$factory could not be graded; nothing was filed and nothing was dispatched" >&2
        echo ":: canary-dispatch: this is the probe's own fault, NOT a verdict about" \
            "$factory; its output was: $probe_output" >&2
        exit 1
        ;;
esac

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
