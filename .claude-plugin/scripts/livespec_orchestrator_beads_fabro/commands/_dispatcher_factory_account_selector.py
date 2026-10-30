"""Select the factory Claude credential env var: the admission-chosen pool slot.

THE FACTORY'S CREDENTIAL COMES FROM THE WHOLE INJECTED SLOT POOL
(`SPECIFICATION/scenarios.md` Scenario 278). Session-headroom admission
assesses every injected `CLAUDE_CODE_OAUTH_TOKEN__*` slot and picks the best
qualifying one (`_dispatcher_session_headroom_pool`); the admission pass
registers a chooser here, and `select_factory_credential` returns that one slot
to every caller, so the usability probe, the credential projection and the
Definition-of-Done judgement all use the slot admission assessed. A run keeps
the token it was dispatched with, so only the injected slot's own headroom
matters, never the account the caam loop picked for interactive spend.

The caam record below is now only the FALLBACK for a caller running with no
admission choice (a standalone credential-status command, or a pass that
assessed no covered candidate). It is read, never written, and the interactive
account it selects is never changed by a factory selection.

The caam-anthropic-loop publishes, on the host it runs on, the account it
selected for interactive spend to a fixed record (livespec-overseer
SPECIFICATION v049; `overseer/caam_selection_record.py` is the writer). A factory
credential consumer that bills against the same accounts under its own
separately-provisioned `claude setup-token` credentials can follow that rotation
by preferring the pool slot minted for the selected profile.

This module is the SELECTOR. It reads the published PROFILE NAME only (never any
credential material) and, when a per-profile pool slot
`CLAUDE_CODE_OAUTH_TOKEN__<PROFILE>` is present in the wrapper-injected env,
names it; otherwise it names the unnumbered `CLAUDE_CODE_OAUTH_TOKEN` and reports
WHY it fell back. An absent, unreadable, or partial record, or a profile with no
matching slot, degrades to exactly today's behaviour — the unnumbered token — so
the selector is safe to ship BEFORE the host keys the pool slots by profile.

The record is READ, never written, here: publication is the caam loop's job and
the loop MUST NOT read its own record back (v049), so the read path lives with
the consumer, not the writer.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)

__all__: list[str] = [
    "SELECTED_ACCOUNT_RECORD_REL",
    "FactoryCredentialChoice",
    "factory_credential_env_name",
    "injected_credential_slots",
    "parse_selected_profile",
    "read_selected_profile",
    "register_admission_slot_chooser",
    "resolve_factory_credential_env_name",
    "select_factory_credential",
    "selected_account_record_path",
]

# Byte-identical to the writer's relative path (overseer/caam_selection_record.py
# SELECTION_RECORD_REL): a FIXED `~/.local/state` location, deliberately NOT
# XDG-configurable, so writer and reader cannot drift via divergent env resolution.
SELECTED_ACCOUNT_RECORD_REL: Final = Path(".local/state/caam-usage-rotate/selected-account.json")
_PROFILE_KEY: Final = "profile"
_SLOT_PREFIX: Final = "CLAUDE_CODE_OAUTH_TOKEN__"

# The admission pass's chooser: a callable returning the env-var NAME of the slot
# it chose, or None. Held at module scope because admission and every credential
# consumer run in ONE dispatcher process and the consumers take no policy argument.
_ADMISSION_CHOOSER: dict[str, Callable[[], str | None]] = {}


@dataclass(frozen=True, kw_only=True)
class FactoryCredentialChoice:
    """The chosen credential env-var NAME and, when it fell back, why.

    `fallback_reason` is None only when a published profile named a slot that is
    actually present in the injected env; it is a non-secret, operator-facing
    string in every fallback case.
    """

    env_name: str
    fallback_reason: str | None


def injected_credential_slots(*, environ: Mapping[str, str]) -> tuple[str, ...]:
    """Every injected pool slot's env-var NAME, sorted; the unnumbered token only when sole.

    A slot is injected when its variable is present and non-empty. The unnumbered
    `CLAUDE_CODE_OAUTH_TOKEN` is the pool's sole slot only when no numbered slot is
    injected, so a host keying its pool by profile never assesses the legacy token.
    """
    numbered = tuple(
        sorted(name for name, value in environ.items() if name.startswith(_SLOT_PREFIX) and value)
    )
    if numbered:
        return numbered
    return (CLAUDE_OAUTH_TOKEN_ENV,) if environ.get(CLAUDE_OAUTH_TOKEN_ENV) else ()


def register_admission_slot_chooser(*, chooser: Callable[[], str | None] | None) -> None:
    """Install (or, with `None`, clear) the admission pass's slot chooser."""
    if chooser is None:
        _ADMISSION_CHOOSER.clear()
    else:
        _ADMISSION_CHOOSER["chooser"] = chooser


def selected_account_record_path(*, home: Path) -> Path:
    return home / SELECTED_ACCOUNT_RECORD_REL


def _slot_env_name(*, profile: str) -> str:
    # "anthropic-3" -> "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3": env-var names carry
    # no hyphens, so the profile is upper-cased with hyphens folded to underscores.
    normalized = profile.strip().upper().replace("-", "_")
    return f"{_SLOT_PREFIX}{normalized}"


def parse_selected_profile(*, record_text: str) -> str | None:
    """The published `profile` value, or None for any unusable record.

    Tolerant by contract: malformed JSON, a non-object root, or a missing,
    non-string, or empty `profile` all read as "no selection" so the caller
    falls back rather than raising.
    """
    try:
        parsed = json.loads(record_text)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    record = cast("dict[str, object]", parsed)
    profile = record.get(_PROFILE_KEY)
    if not isinstance(profile, str) or profile.strip() == "":
        return None
    return profile.strip()


def read_selected_profile(*, home: Path) -> str | None:
    """Read the published profile name from the host record, tolerating absence."""
    try:
        record_text = selected_account_record_path(home=home).read_text(encoding="utf-8")
    except OSError:
        return None
    return parse_selected_profile(record_text=record_text)


def resolve_factory_credential_env_name(
    *,
    selected_profile: str | None,
    available_env_names: frozenset[str],
) -> FactoryCredentialChoice:
    """Pure: choose the credential env-var NAME from the selection and the env.

    Prefer the per-profile pool slot when the loop published a profile AND that
    slot is present in the injected env; otherwise name the unnumbered token and
    say why. Never raises; the fallback is always a valid choice.
    """
    if selected_profile is None:
        return FactoryCredentialChoice(
            env_name=CLAUDE_OAUTH_TOKEN_ENV,
            fallback_reason="no caam-published account selection record",
        )
    slot = _slot_env_name(profile=selected_profile)
    if slot in available_env_names:
        return FactoryCredentialChoice(env_name=slot, fallback_reason=None)
    return FactoryCredentialChoice(
        env_name=CLAUDE_OAUTH_TOKEN_ENV,
        fallback_reason=f"no {slot} in the injected env for published profile {selected_profile!r}",
    )


def factory_credential_env_name(
    *,
    home: Path,
    available_env_names: frozenset[str],
) -> FactoryCredentialChoice:
    """Impure convenience: read the host record, then resolve against the env."""
    return resolve_factory_credential_env_name(
        selected_profile=read_selected_profile(home=home),
        available_env_names=available_env_names,
    )


def select_factory_credential(
    *,
    environ: Mapping[str, str],
    home: Path,
    warn: Callable[[str], object],
) -> FactoryCredentialChoice:
    """Resolve the credential env-var name and emit ONE loud line on fallback.

    The slot admission chose out of the injected pool wins whenever it is still
    injected; only without one does the caam-published selection decide.

    The caller then reads `environ[choice.env_name]`. `warn` is invoked exactly
    once, with a non-secret operator-facing message, precisely when the selector
    fell back to the unnumbered token — so a slot that silently fails to map is
    visible rather than a quiet reversion.
    """
    chooser = _ADMISSION_CHOOSER.get("chooser")
    admitted = None if chooser is None else chooser()
    if admitted is not None and admitted in injected_credential_slots(environ=environ):
        return FactoryCredentialChoice(env_name=admitted, fallback_reason=None)
    choice = factory_credential_env_name(home=home, available_env_names=frozenset(environ))
    if choice.fallback_reason is not None:
        _ = warn(
            f"factory credential slot fallback — using {choice.env_name}: {choice.fallback_reason}"
        )
    return choice
