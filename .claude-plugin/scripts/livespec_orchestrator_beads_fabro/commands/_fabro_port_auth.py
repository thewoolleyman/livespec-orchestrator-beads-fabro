"""The factory credential: how `fabro auth login` leaves it, and how it is read.

Two halves of ONE concern, which is why they sit together. `fabro_auth_login` is
the invocation that OBTAINS the credential — it writes `~/.fabro/auth.json`,
which is exactly the file the resolution below reads — so the write and the read
of that file are stated in one place rather than one here and one as a line of
the facade class. Part of the `_fabro_port` facade family either way, which is
the only place this package reaches the engine.

`fabro_auth_login` answers `None` without invoking anything when the target names
no server or carries no dev token, because there is then no login to perform: a
factory with no address cannot be logged in to, and a factory with no token has
nothing to log in WITH. That is the same line the resolution below draws, and for
the same reason — it is an answer worth journalling at the call site, not an
error.

Bearer-credential resolution has two sources, in a fixed order. The
`FABRO_DEV_TOKEN__<factory>` environment
variable wins when it is set, because an operator who exported it for THIS
factory said something more specific than a login file shared by every
client on the host. `_config.resolve_fabro_factory` has already read it into
the target's `dev_token`, so this module reads the target rather than the
environment a second time.

Otherwise the credential comes from `~/.fabro/auth.json`, which is where
`fabro auth login` leaves it and therefore what every operator host actually
has. Its shape is `{"servers": {"<server url>": {"kind": ..., "token":
...}}}`, keyed by the url the CLI was pointed at. A configured url and a
logged-in url that name the same server can still differ by a trailing slash
or by case, so an exact hit is tried first and a scheme/host/port-normalised
comparison second — a normalised-only match would quietly accept a path
suffix the exact form would have rejected.

Resolving to `None` is a legitimate answer, not an error: it means the
caller is about to speak to the server unauthenticated. That is worth
JOURNALLING at the call site rather than raising here, because the visible
symptom — every route failing and the destructive fallback firing — reads
exactly like a healthy server refusing the act.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from livespec_orchestrator_beads_fabro.commands._fabro_port_types import (
    FabroCommandResult,
    FabroRunner,
    FabroTarget,
)
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "FABRO_AUTH_FILE_RELATIVE",
    "fabro_auth_file",
    "fabro_auth_login",
    "resolve_bearer_token",
]

# Relative to the operator's home directory, which is where the `fabro` CLI
# writes it and the only place this module looks for it.
FABRO_AUTH_FILE_RELATIVE = Path(".fabro") / "auth.json"


def fabro_auth_file() -> Path:
    """Where `fabro auth login` left this host's credential.

    A named function rather than an inline `Path.home()` join because it is
    an AMBIENT host dependency: the test suite has to be able to point it at
    a scratch file, or whether a check passes depends on whether the machine
    running it happens to be logged in to a factory.
    """
    return Path.home() / FABRO_AUTH_FILE_RELATIVE


def fabro_auth_login(
    *,
    fabro_bin: str,
    runner: FabroRunner,
    cwd: Path,
    target: FabroTarget,
    timeout_seconds: float,
) -> FabroCommandResult | None:
    """Log this host in to ONE factory with that factory's dev token.

    `--server` is spelled explicitly rather than taken from the shared server
    suffix because this verb's argv names the server it is logging in TO as an
    operand of the login itself; the credential and the address are one pair.
    """
    if target.server_url is None or target.dev_token is None:
        return None
    argv = [
        fabro_bin,
        "auth",
        "login",
        "--dev-token",
        target.dev_token,
        "--server",
        target.server_url,
    ]
    return FabroCommandResult(
        command=runner.run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds)
    )


def resolve_bearer_token(*, target: FabroTarget) -> str | None:
    """Resolve one factory's bearer credential, or `None` if it has none."""
    if target.dev_token is not None:
        return target.dev_token
    if target.server_url is None:
        return None
    return _auth_file_token(server_url=target.server_url)


def _auth_file_token(*, server_url: str) -> str | None:
    servers = _logged_in_servers(path=fabro_auth_file())
    exact = _token_of(entry=servers.get(server_url))
    if exact is not None:
        return exact
    wanted = _normalised(url=server_url)
    for url, entry in servers.items():
        token = _token_of(entry=entry)
        if token is not None and _normalised(url=url) == wanted:
            return token
    return None


def _logged_in_servers(*, path: Path) -> dict[str, object]:
    read = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(read, AttemptFailure):
        return {}
    parsed = parse_json(text=read)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return {}
    servers: object = cast("dict[str, Any]", parsed).get("servers")
    if not isinstance(servers, dict):
        return {}
    return cast("dict[str, object]", servers)


def _token_of(*, entry: object) -> str | None:
    if not isinstance(entry, dict):
        return None
    token: object = cast("dict[str, Any]", entry).get("token")
    if isinstance(token, str) and token != "":
        return token
    return None


def _normalised(*, url: str) -> str:
    trimmed = url.strip().rstrip("/")
    split = urlsplit(trimmed)
    if split.scheme == "" or split.netloc == "":
        return trimmed.lower()
    return f"{split.scheme.lower()}://{split.netloc.lower()}"
