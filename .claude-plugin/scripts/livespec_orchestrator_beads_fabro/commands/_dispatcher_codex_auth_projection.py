"""The sandbox Codex credential projection the Dispatcher overlay appends.

The host is the sole `codex login` + refresh owner; `_dispatcher_codex_auth`
reads its live `auth.json`, freshness-gates it and returns a NON-rotatable
snapshot. This module owns the other half — how that snapshot reaches the
sandbox: the `[[run.prepare.steps]]` block that writes it to
`$CODEX_HOME/auth.json`, and the `[environments.<id>.env]` lines that carry
its value and pin where the projected credential may not egress to. It is
the credential sibling of `_dispatcher_codex_otel_config`, which owns the
same two projections for the Codex `[otel]` table.
"""

from __future__ import annotations

import json

__all__: list[str] = [
    "codex_auth_env_lines",
    "codex_auth_prepare_steps_block",
]

# The sandbox path the projected Codex auth.json is written to. The
# prepare step (running before the agent nodes) writes the credential
# here, and the codex-acp child reads it via $CODEX_HOME — both inherit
# CODEX_HOME from the container-level [environments.<id>.env] table.
_SANDBOX_CODEX_HOME = "/workspace/.codex"

# Where the projected credential is allowed to reach codex-core's token
# refresh/revocation service: nowhere. The projected auth.json carries a
# deliberately non-rotatable `tokens.refresh_token` sentinel, but codex-core
# still SENDS it: on any HTTP 401 its unauthorized-recovery state machine POSTs
# `tokens.refresh_token` to the refresh endpoint with no validation and NO
# expiry check, so the freshness gate does not cover this path (a spurious 401,
# or a container clock running fast -- codex compares the access-token `exp`
# against the CONTAINER clock while the gate evaluates on the HOST clock -- both
# reach it). codex-core resolves that endpoint from
# CODEX_REFRESH_TOKEN_URL_OVERRIDE when set, and resolves its REVOCATION
# endpoint from the same variable, so pinning it at a closed loopback port keeps
# both the sentinel and any revoke attempt inside the container: the POST fails
# locally with connection-refused instead of presenting a bogus credential to
# the real auth service. Port 1 is privileged and never bound.
_SANDBOX_CODEX_REFRESH_URL_OVERRIDE = "http://127.0.0.1:1/livespec-refresh-disabled"


def codex_auth_prepare_steps_block(*, codex_auth_snapshot: str | None) -> str:
    """Render the Codex-auth `[[run.prepare.steps]]` block (Scenario 18).

    Empty string when `codex_auth_snapshot` is None (the Claude-OAuth-only
    shape). The step runs before the agent nodes and writes the projected
    snapshot to `$CODEX_HOME/auth.json` mode-600; both `$CODEX_HOME` and
    `$CODEX_AUTH_JSON` are inherited from the container-level env table the
    same overlay declares, so the shell needs no inline value. The script
    is `json.dumps`-ed to TOML-quote it, matching the sibling-clone steps.

    The trailing `test -s` READS THE PROJECTION BACK, so a projection that
    silently produced an empty file aborts the run here rather than surfacing
    as a Codex node that cannot authenticate several minutes later. This is
    the ONLY position from which the read-back is possible: `overlay_text`
    appends these steps AFTER the committed workflow's own, so this is the
    last prepare step and nothing an outside caller appends to the committed
    file can observe the file this step writes.
    """
    if codex_auth_snapshot is None:
        return ""
    script = (
        'mkdir -p "$CODEX_HOME" && printf %s "$CODEX_AUTH_JSON" >'
        ' "$CODEX_HOME/auth.json" && chmod 600 "$CODEX_HOME/auth.json"'
        ' && test -s "$CODEX_HOME/auth.json"'
    )
    lines = [
        "",
        "# --- Dispatcher-materialized Codex credential projection: write the",
        "# --- non-rotatable auth.json snapshot the codex-acp adapter reads ---",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(script)}",
    ]
    return "\n".join(lines) + "\n"


def codex_auth_env_lines(*, codex_auth_snapshot: str | None) -> str:
    """Render the Codex `CODEX_HOME` / `CODEX_AUTH_JSON` env-table lines.

    Empty string when `codex_auth_snapshot` is None. Each value is
    `json.dumps`-ed so the multi-line JSON snapshot single-line-encodes
    with `\\n` escapes (valid TOML), exactly like the CLAUDE_CODE_OAUTH_TOKEN
    / OTel lines. These ride in the same `[environments.<id>.env]` table —
    the container baseline env every sandbox process inherits — so the
    prepare-step shell and the codex-acp child both see them.

    `CODEX_REFRESH_TOKEN_URL_OVERRIDE` rides alongside them so the projected
    credential's non-rotatable sentinel can never egress; see
    `_SANDBOX_CODEX_REFRESH_URL_OVERRIDE`.
    """
    if codex_auth_snapshot is None:
        return ""
    return (
        f"CODEX_HOME = {json.dumps(_SANDBOX_CODEX_HOME)}\n"
        f"CODEX_AUTH_JSON = {json.dumps(codex_auth_snapshot)}\n"
        "CODEX_REFRESH_TOKEN_URL_OVERRIDE = "
        f"{json.dumps(_SANDBOX_CODEX_REFRESH_URL_OVERRIDE)}\n"
    )
