"""The dispatch target's committed `credential_wrapper` declaration, as read.

Split out of `_dispatcher_credentials` by cohesion. That module PROJECTS
credentials into a sandbox; this one answers a narrower and entirely different
question — what argv prefix has the target repository declared as the thing that
injects its credential environment — and the answer is now read by three callers
rather than one: the Claude credential assessment beside it, and both
pre-dispatch paths' proof-credential gate, whose absent-value refusal must name
the wrapper that did not inject the value.

FAIL-SOFT ONTO "NOT DECLARED", DELIBERATELY. Every arm of the read returns the
empty tuple rather than raising: an unreadable file, unparseable JSONC, a root
that is not an object, a `credential_wrapper` that is not a list, and a list
holding a non-string element. The consumers are all building a DIAGNOSTIC — a
message telling an operator which wrapper to fix — so an exception here would
replace an actionable refusal with a traceback about the file the refusal was
about to name. `credential_wrapper_text` renders the empty answer as prose that
says so, which is what reaches the operator.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._jsonc import JsoncFailure, parse
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "credential_wrapper_text",
    "read_dispatch_target_credential_wrapper",
]


def read_dispatch_target_credential_wrapper(*, repo: Path) -> tuple[str, ...]:
    config_path = repo / ".livespec.jsonc"
    config_text = attempt(
        action=lambda: config_path.read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    if isinstance(config_text, AttemptFailure):
        return ()
    data = parse(text=config_text)
    if isinstance(data, JsoncFailure):
        return ()
    if not isinstance(data, dict):
        return ()
    mapping = cast(dict[str, object], data)
    wrapper = mapping.get("credential_wrapper")
    if not isinstance(wrapper, list):
        return ()
    wrapper_parts = cast(list[object], wrapper)
    parts: list[str] = []
    for part in wrapper_parts:
        if not isinstance(part, str):
            return ()
        parts.append(part)
    return tuple(parts)


def credential_wrapper_text(*, repo: Path) -> str:
    wrapper = read_dispatch_target_credential_wrapper(repo=repo)
    if not wrapper:
        return f"no credential_wrapper configured in {repo / '.livespec.jsonc'}"
    return repr(list(wrapper))
