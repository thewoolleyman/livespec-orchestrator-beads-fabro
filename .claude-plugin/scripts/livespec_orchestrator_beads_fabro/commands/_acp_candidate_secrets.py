"""Literal-credential detection over COMMITTED ACP candidate configuration.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" makes a fallback-enabled node's `command`, `args` and `env`
PUBLIC COMMITTED DATA: they must carry no literal credential, token or
secret reference, because candidate credentials arrive only through
section "Worker credential projection" -- the uncommitted overlay that
hands the key straight to the child process.

WHY A LEXICAL MARKER SCAN RATHER THAN A VALUE-SHAPE ONE. There is no
reliable shape for "this string is a secret": provider tokens are opaque,
and a scanner tuned to one vendor's prefix passes every other vendor's.
What IS reliable is that a credential arrives under a NAME that says so --
`ANTHROPIC_AUTH_TOKEN`, `OPENAI_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN` -- so
the scan reads names and text for those markers and refuses the whole
configuration. That trades a false positive (a node genuinely wanting an
env key spelled `TOKEN_BUDGET`) for never committing a live credential,
which is the right way round: the false positive is one rename, and the
false negative is a secret in git history.

NO REFUSAL THIS MODULE PRODUCES ECHOES THE OFFENDING VALUE. A refusal is
journalled, and the same contract requires journals, traces, events,
diagnostics and refusals to omit credential material. So a hit inside an
env VALUE names only its key, and a hit inside `command` or `args` names
the position and the marker that matched -- never the text around it.
"""

from __future__ import annotations

from collections.abc import Mapping

__all__: list[str] = [
    "SECRET_MARKERS",
    "adapter_secret_refusal",
    "secret_marker",
]

# The credential-naming vocabulary, case-folded and matched as substrings
# so `ANTHROPIC_AUTH_TOKEN`, `openai_api_key` and `--bearer` all hit. Bare
# `auth` and bare `key` are deliberately ABSENT: they match `author` and
# `keyring`, and a scan that refuses ordinary configuration gets switched
# off, which is worse than a narrower one that stays on.
SECRET_MARKERS: tuple[str, ...] = (
    "api-key",
    "api_key",
    "apikey",
    "bearer",
    "credential",
    "passwd",
    "password",
    "private-key",
    "private_key",
    "secret",
    "token",
)


def secret_marker(*, text: str) -> str | None:
    """The first credential marker `text` carries, or `None` when it is clean."""
    folded = text.casefold()
    return next((marker for marker in SECRET_MARKERS if marker in folded), None)


def adapter_secret_refusal(
    *,
    command: str,
    args: tuple[str, ...],
    env: Mapping[str, str],
    key: str,
) -> str | None:
    """Refuse committed adapter data carrying a literal credential reference.

    Scans the command, every argument, and every env key AND value. The
    env value is scanned even though its key already was, because the
    reverse spelling -- an innocuous key holding a pasted token whose own
    text says `secret` -- is exactly as committed as the other.
    """
    command_marker = secret_marker(text=command)
    if command_marker is not None:
        return _refusal(key=key, location="command", marker=command_marker)
    for index, argument in enumerate(args):
        marker = secret_marker(text=argument)
        if marker is not None:
            return _refusal(key=key, location=f"args[{index}]", marker=marker)
    return _env_refusal(env=env, key=key)


def _env_refusal(*, env: Mapping[str, str], key: str) -> str | None:
    """The first credential-shaped env entry, scanned in sorted key order."""
    for name in sorted(env):
        name_marker = secret_marker(text=name)
        if name_marker is not None:
            return _refusal(key=key, location=f"env key {name!r}", marker=name_marker)
        value_marker = secret_marker(text=env[name])
        if value_marker is not None:
            return _refusal(key=key, location=f"env value for {name!r}", marker=value_marker)
    return None


def _refusal(*, key: str, location: str, marker: str) -> str:
    """One refusal line, naming the position and the marker but never the text."""
    return (
        f"{key}.{location} reads as a literal credential (matched {marker!r}); "
        "fallback-enabled candidate command, args and env are committed public "
        "data, so credentials must arrive through the Worker credential projection"
    )
