"""Credential and telemetry projection helpers for Dispatcher runs."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, cast

__all__: list[str] = [
    "CODEX_FRESHNESS_MARGIN_SECONDS",
    "CODEX_FRESHNESS_RUN_BUDGET_SECONDS",
    "CODEX_NON_ROTATABLE_REFRESH_SENTINEL",
    "DEFAULT_SANDBOX_OTEL_ENDPOINT",
    "SANDBOX_OTEL_ENDPOINT_ENV_VAR",
    "CodexFreshnessVerdict",
    "assess_codex_credential_freshness",
    "cc_otel_overlay_env",
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
# sandbox provisions that alias). NOTE: the host-side E1 receiver defaults
# to a loopback (127.0.0.1) bind — for sandbox egress to actually land it
# must bind a bridge-reachable interface; that host-side wiring is the
# live-verify leg, OUT OF SCOPE for the overlay-assembly here.
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
    """Assemble the in-sandbox Claude-Code OTel env dict."""
    resource_attributes = ",".join(
        (
            "service.namespace=livespec-family",
            f"work.item.id={work_item_id}",
            f"livespec.dispatch.id={dispatch_id}",
        )
    )
    return {
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

# The freshness gate's run budget: the realistic maximum wall-clock a single
# dispatch can run. The gate requires the projected Codex credential to outlive
# this budget plus CODEX_FRESHNESS_MARGIN_SECONDS before dispatch (Scenario 19).
#
# Anchored to the Fabro `implement` node's per-turn ceiling
# (.fabro/workflows/implement-work-item/workflow.fabro, timeout="14400s" = 4h):
# implement is the dominant leg of a run, while the downstream janitor/review/pr
# nodes are sub-hour ceilings that realistically take minutes, comfortably
# absorbed by the 1h margin. Observed real dispatches run ~30-45min, so 4h
# carries ~5-8x slack; the gate thus requires the token to outlive 5h total.
#
# DELIBERATELY DECOUPLED from `_dispatcher_engine._FABRO_TIMEOUT_SECONDS`
# (54000s = 15h). That 15h value is a coarse subprocess CEILING / defense-in-depth
# backstop, NOT an expected run length; wiring it in as the freshness run budget
# demanded the token outlive 15h + 1h = 16h, so a host Codex token (minted ~18h,
# dropping below 16h within ~2h) was refused for nearly every unattended dispatch.
CODEX_FRESHNESS_RUN_BUDGET_SECONDS = 14400


@dataclass(frozen=True, kw_only=True)
class CodexFreshnessVerdict:
    """Outcome of the dispatch-time Codex credential freshness gate."""

    fresh_enough: bool
    access_token_expires_at_epoch: int
    renewal_message: str | None


def assess_codex_credential_freshness(
    *,
    source_auth_json: str,
    now_epoch: int,
    run_budget_seconds: int,
) -> CodexFreshnessVerdict:
    """Require the projected Codex access token to outlive the run budget."""
    expires_at = _decode_codex_access_token_exp(source_auth_json=source_auth_json)
    required_remaining = run_budget_seconds + CODEX_FRESHNESS_MARGIN_SECONDS
    fresh_enough = (expires_at - now_epoch) >= required_remaining
    renewal_message = (
        None
        if fresh_enough
        else (
            "Host Codex credential is too short-lived for the run budget; "
            "run `codex login` on the orchestrator host to renew it."
        )
    )
    return CodexFreshnessVerdict(
        fresh_enough=fresh_enough,
        access_token_expires_at_epoch=expires_at,
        renewal_message=renewal_message,
    )


def _decode_codex_access_token_exp(*, source_auth_json: str) -> int:
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
    claims: dict[str, Any] = json.loads(base64.urlsafe_b64decode(padded))
    exp = claims.get("exp")
    if not isinstance(exp, int):
        raise ValueError("access token has no integer exp claim")  # noqa: TRY003, TRY004
    return exp
