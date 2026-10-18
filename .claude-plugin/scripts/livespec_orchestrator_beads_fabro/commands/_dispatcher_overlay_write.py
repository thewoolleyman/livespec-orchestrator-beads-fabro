"""How a rendered run-configuration bundle becomes the on-disk overlay.

Split from `_dispatcher_credentials` by cohesion. That module answers WHAT a
dispatch projects -- it reads the host's credentials, mints an installation
token, grades freshness and assembles every projection input -- while this one
answers the narrower question of how the assembled text reaches disk: its
credentials placed on the transport the factory declared, and the file created
mode-600 so no other user on the host can read what is left inline.

The two halves are ONE act and belong together. Routing decides whether a value
travels in the file at all, and the file's permissions are what protect it when
it does, so a caller that performed one without the other would either write a
bundle it had not routed or route one it then wrote world-readable.

ROUTING HAPPENS BEFORE THE FILE EXISTS. The refusal arms of the transport are
the ones that matter here: a bundle that cannot be routed cleanly must leave no
overlay behind at all, because the dispatch path treats the overlay's existence
as a materialized projection and a half-written one would be launched.
"""

from __future__ import annotations

import os
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import (
    SecretChannelRefusal,
    VaultSecretSink,
    route_dispatch_secrets,
)

__all__: list[str] = ["write_routed_overlay"]


def write_routed_overlay(
    *,
    overlay: Path,
    rendered: str,
    channel: str,
    proof_credentials_env: str,
    routes_codex: bool,
    sink: VaultSecretSink | None,
) -> str | None:
    """Route `rendered` onto `channel` and write it; a refusal message, or None.

    `proof_credentials_env` is the proof-credential projection's OWN rendered
    lines, passed so the routed name list can be read back off what that
    projection actually emitted rather than from a second reading of the
    declaration it owns.

    `routes_codex` is this dispatch's RESOLVED routing, which decides whether
    the Codex credential is a family the bundle must carry or one the dispatch
    was right not to project. It is threaded from the caller rather than
    re-resolved here for the same reason the proof-credential lines are: the
    caller has already asked that question, and a second resolution cannot be
    proven to agree with the one the Codex projection leg scoped itself by.

    The write is `O_EXCL` over a path unlinked immediately before, which is how
    the mode argument is load-bearing rather than advisory: an `open` onto an
    existing file would keep that file's permissions, so a leftover overlay from
    an earlier dispatch could silently downgrade this one's.
    """
    overlay.unlink(missing_ok=True)
    routed = route_dispatch_secrets(
        overlay_text=rendered,
        channel=channel,
        proof_credentials_env=proof_credentials_env,
        routes_codex=routes_codex,
        sink=sink,
    )
    if isinstance(routed, SecretChannelRefusal):
        return routed.message
    descriptor = os.open(str(overlay), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        _ = handle.write(routed.overlay_text)
    return None
