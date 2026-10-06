"""Credential and telemetry projection helpers for Dispatcher runs."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, cast

__all__: list[str] = [
    "CODEX_FRESHNESS_MARGIN_SECONDS",
    "CODEX_NON_ROTATABLE_REFRESH_SENTINEL",
    "DEFAULT_SANDBOX_OTEL_ENDPOINT",
    "SANDBOX_OTEL_ENDPOINT_ENV_VAR",
    "CodexFreshnessVerdict",
    "assess_codex_credential_freshness",
    "cc_otel_overlay_env",
    "codex_freshness_required_seconds",
    "decode_codex_access_token_claims",
    "decode_codex_access_token_exp",
    "project_codex_auth_snapshot",
    "resolve_sandbox_otel_endpoint",
]

# The lever that overrides where the in-sandbox Claude-Code OTel export
# ships (29f.3). It points at the host-local E1 OTLP receiver (29f.7),
# NOT Honeycomb — the sandbox ships PLAINTEXT and the host-local egress
# stage holds the Honeycomb ingest key (telemetry-pipeline-architecture.md
# §3.5). The committed default is the Docker default-bridge gateway:
# inside a fabro docker sandbox `127.0.0.1` is the sandbox's OWN loopback,
# so the host's loopback-bound receiver is reached via the bridge gateway
# address instead. 172.17.0.1 is the conventional Docker default-bridge
# gateway; the orchestrator's later live-verify corrects this lever if the
# real reachable address differs (e.g. `host.docker.internal` when the
# sandbox provisions that alias). The host-side E1 receiver binds the SAME
# bridge gateway by default (`_otel_receive._DEFAULT_RECEIVER_HOST` =
# 172.17.0.1), so sandbox egress lands symmetrically; a non-docker host
# overrides both levers to a loopback.
SANDBOX_OTEL_ENDPOINT_ENV_VAR = "LIVESPEC_SANDBOX_OTEL_ENDPOINT"
DEFAULT_SANDBOX_OTEL_ENDPOINT = "http://172.17.0.1:4318"


def resolve_sandbox_otel_endpoint(*, environ: dict[str, str]) -> str:
    """Resolve the sandbox-to-host OTLP endpoint for Claude-Code OTel."""
    override = environ.get(SANDBOX_OTEL_ENDPOINT_ENV_VAR, "").strip()
    return override or DEFAULT_SANDBOX_OTEL_ENDPOINT


def cc_otel_overlay_env(
    *,
    work_item_id: str,
    dispatch_id: str,
    endpoint: str,
) -> dict[str, str]:
    """Assemble the in-sandbox OTel env dict.

    Mostly Claude-Code's own `OTEL_*` surface, plus ONE key that is not
    Claude-Code's: `SANDBOX_OTEL_ENDPOINT_ENV_VAR`, which is what the sandbox
    TDD order guard (`.claude/hooks/livespec_tdd_order_span.resolve_endpoint`)
    reads to find its receiver. That guard is not a Claude-Code exporter — it
    POSTs its own OTLP span per product-write verdict — and it honors NO other
    variable and carries NO default, deliberately, so that a human session
    outside any dispatch attempts no post at all. Projecting
    `OTEL_EXPORTER_OTLP_ENDPOINT` alone therefore left every dispatched
    verdict resolving no endpoint and posting nothing, which read downstream
    as a dispatch whose guard spans never arrived (measured on live run
    01M47AGX4BB5FJJR0K6AW1736W).

    ONE NAME SERVES BOTH ROLES, and that is the point rather than a
    coincidence: the host READS this variable as the override lever
    `resolve_sandbox_otel_endpoint` resolves, and the sandbox READS it as the
    resolved answer — so the same resolution run inside the sandbox returns
    what the host computed, and there is no second spelling for the two ends
    of one contract to disagree about. The PROJECTED value is always the
    resolved `endpoint` argument, never this process's own environment, so a
    dispatch cannot ship the host's unresolved lever (or its absence) into a
    sandbox.

    `tests/integration/test_sandbox_order_guard_endpoint_projection.py` is the
    mechanical guard on the producer-consumer pair: it hands the SHIPPED hook
    emitter exactly this dict and asserts the verdict reaches a live receiver
    and both calibration fields, so a rename on either end fails there rather
    than silently zeroing the signal.
    """
    resource_attributes = ",".join(
        (
            "service.namespace=livespec-family",
            f"work.item.id={work_item_id}",
            f"livespec.dispatch.id={dispatch_id}",
        )
    )
    return {
        SANDBOX_OTEL_ENDPOINT_ENV_VAR: endpoint,
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_METRICS_EXPORTER": "otlp",
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_TRACES_EXPORTER": "otlp",
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
        "OTEL_EXPORTER_OTLP_ENDPOINT": endpoint,
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
        "OTEL_RESOURCE_ATTRIBUTES": resource_attributes,
        "OTEL_METRIC_EXPORT_INTERVAL": "10000",
        "OTEL_LOGS_EXPORT_INTERVAL": "5000",
    }


CODEX_NON_ROTATABLE_REFRESH_SENTINEL = "livespec-orch-no-refresh-sentinel"


def project_codex_auth_snapshot(*, source_auth_json: str) -> str:
    """Return a Codex auth.json snapshot with a non-rotatable refresh token."""
    source: dict[str, Any] = json.loads(source_auth_json)
    raw_tokens = source.get("tokens")
    tokens: dict[str, Any] = (
        dict(cast("dict[str, Any]", raw_tokens)) if isinstance(raw_tokens, dict) else {}
    )
    tokens["refresh_token"] = CODEX_NON_ROTATABLE_REFRESH_SENTINEL
    projected: dict[str, Any] = {**source, "tokens": tokens}
    return json.dumps(projected, indent=2, sort_keys=True) + "\n"


CODEX_FRESHNESS_MARGIN_SECONDS = 3600

# NO RUN-BUDGET CONSTANT LIVES HERE ANY MORE, and reintroducing one is the
# defect this removal retired. `CODEX_FRESHNESS_RUN_BUDGET_SECONDS` was 14400 --
# the `implement` node's own four-hour ceiling standing in for the whole run on
# the reasoning that the dominant node dominates -- so the gate demanded five
# hours of a credential however long the graph could actually run, and a
# repository that raised a node timeout or dispatched a longer workflow was
# graded against a figure its own configuration had already outgrown.
#
# The run budget is now RESOLVED PER DISPATCH by
# `_dispatcher_credential_requirement` from the workflow the dispatch selected,
# and is passed in as `run_budget_seconds`. A module constant cannot follow
# configuration, which is the whole reason this one had to go rather than be
# re-tuned.


@dataclass(frozen=True, kw_only=True)
class CodexFreshnessVerdict:
    """Outcome of the dispatch-time Codex credential freshness gate."""

    fresh_enough: bool
    access_token_expires_at_epoch: int
    remaining_seconds: int
    required_remaining_seconds: int
    renewal_message: str | None


def codex_freshness_required_seconds(*, run_budget_seconds: int) -> int:
    """Return the usable lifetime the freshness gate demands of a credential.

    The ONE place the requirement is composed. The refresh guard
    (`_dispatcher_codex_refresh.CODEX_REFRESH_GUARD_SECONDS`) is derived from
    this same function rather than written as its own number, because the two
    diverging is precisely the dead zone: a guard smaller than the requirement
    leaves an interval in which this gate refuses while the refresher declines.
    """
    return run_budget_seconds + CODEX_FRESHNESS_MARGIN_SECONDS


def assess_codex_credential_freshness(
    *,
    source_auth_json: str,
    now_epoch: int,
    run_budget_seconds: int,
) -> CodexFreshnessVerdict:
    """Require the projected Codex access token to outlive the run budget."""
    expires_at = decode_codex_access_token_exp(source_auth_json=source_auth_json)
    required_remaining = codex_freshness_required_seconds(run_budget_seconds=run_budget_seconds)
    remaining = expires_at - now_epoch
    fresh_enough = remaining >= required_remaining
    # The bounded, host-local renewal comes FIRST: this lifetime is inside the
    # refresh guard by construction, so the sanctioned refresher is eligible and
    # a human `codex login` is not yet established as necessary.
    renewal_message = (
        None
        if fresh_enough
        else (
            f"Host Codex credential has {remaining} seconds of usable lifetime, "
            f"below the {required_remaining} seconds the dispatch freshness gate "
            "requires (run budget plus margin). It is inside the refresh guard, "
            "so `dispatcher.py codex-cred-refresh` on the credential-source host "
            "can renew it in place."
        )
    )
    return CodexFreshnessVerdict(
        fresh_enough=fresh_enough,
        access_token_expires_at_epoch=expires_at,
        remaining_seconds=remaining,
        required_remaining_seconds=required_remaining,
        renewal_message=renewal_message,
    )


def decode_codex_access_token_claims(*, source_auth_json: str) -> dict[str, Any]:
    """Decode the claim set carried by a Codex auth.json access token.

    The ONE place the access token's JWT payload is unpacked, so the expiry
    gate and the identity observation cannot disagree about what a malformed
    credential is. STRUCTURAL ONLY: the signature is never verified and no
    claim value is returned to any caller that would persist or print it
    verbatim — the token itself is a secret, and its claims identify a live
    session.
    """
    source: dict[str, Any] = json.loads(source_auth_json)
    raw_tokens = source.get("tokens")
    tokens: dict[str, Any] = (
        cast("dict[str, Any]", raw_tokens) if isinstance(raw_tokens, dict) else {}
    )
    access_token = tokens.get("access_token")
    if not isinstance(access_token, str):
        raise ValueError("auth.json tokens.access_token is missing or not a string")  # noqa: TRY003, TRY004
    segments = access_token.split(".")
    if len(segments) < 2:  # noqa: PLR2004
        raise ValueError("access token is not a JWT")  # noqa: TRY003
    padded = segments[1] + "=" * (-len(segments[1]) % 4)
    claims: object = json.loads(base64.urlsafe_b64decode(padded))
    if not isinstance(claims, dict):
        raise ValueError("access token payload is not a JSON object")  # noqa: TRY003, TRY004
    return cast("dict[str, Any]", claims)


def decode_codex_access_token_exp(*, source_auth_json: str) -> int:
    """Decode the integer ``exp`` claim from a Codex auth.json access token."""
    claims = decode_codex_access_token_claims(source_auth_json=source_auth_json)
    exp = claims.get("exp")
    if not isinstance(exp, int):
        raise ValueError("access token has no integer exp claim")  # noqa: TRY003, TRY004
    return exp
