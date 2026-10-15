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

WHAT THE WRAPPER INJECTS IS A FACT ABOUT THE WRAPPER, so it is named here beside
the declaration of what the wrapper IS, rather than in either of the two modules
that consume it. The credential assessment names the set in the refusal an
operator reads; the loop's credential re-resolution empties every name in it for
the child it spawns. One list, because the two readings have to agree: a second
copy drifts silently, and the direction it drifts in is a name nobody empties.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)
from livespec_orchestrator_beads_fabro.commands._jsonc import JsoncFailure, parse
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "WRAPPER_INJECTED_CREDENTIAL_ENV_NAMES",
    "credential_wrapper_text",
    "read_dispatch_target_credential_wrapper",
    "wrapper_injected_child_env",
]

# The full per-wrapper credential set a dispatch target's `credential_wrapper` is
# required to inject.
WRAPPER_INJECTED_CREDENTIAL_ENV_NAMES: tuple[str, ...] = (
    "GITHUB_APP_ID",
    "GITHUB_PRIVATE_KEY",
    "BEADS_DOLT_PASSWORD",
    CLAUDE_OAUTH_TOKEN_ENV,
)


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


def wrapper_injected_child_env(*, env_name: str) -> dict[str, str]:
    """The child environment that makes the wrapper's OWN cached diff genuine.

    The wrapper this fleet runs stores, in the invoker's keyring, the DIFF
    between its caller's environment and what it injected, and replays that diff
    to every caller on the host until the entry times out (`AGENTS.md`, the
    wrapper-cache entry, measured 2026-10-01). A nested invocation that already
    holds those values produces a near-empty diff, which fails in two directions
    at once: the reading sees the stale value it started with, and the near-empty
    diff is stored where every other caller on the host then reads it.

    EVERY injected name is emptied, not only the one being read. The diff the
    wrapper computes and caches covers the whole set it injected, so leaving
    three of the four inherited makes that cached diff near-empty for those
    three — the poisoning this emptying exists to prevent, happening to every
    other caller on the host, for the names this reading was not even asking
    about. Emptying only the name under read buys a genuine diff for one entry
    and leaves the defect intact for the rest.

    `env_name` is included because the caam pool slot a dispatch projects is NOT
    in the set above: it is resolved per host from the selected profile, so a
    pool-slot dispatch would otherwise read the one credential it actually
    projects through a value the child still inherited.
    """
    return dict.fromkeys((*WRAPPER_INJECTED_CREDENTIAL_ENV_NAMES, env_name), "")
