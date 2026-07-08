"""Tests for the in-sandbox CC OTel run-config overlay (29f.3).

The overlay turns ON Claude-Code native OpenTelemetry export INSIDE the
fabro sandbox, pointed at the host-local E1 receiver (29f.7), NOT at
Honeycomb directly (telemetry-pipeline-architecture.md §3.5 / §6 — the
sandbox ships PLAINTEXT OTLP to the host-local enrich/receive stage; the
Honeycomb ingest key stays OFF the sandbox). These tests exercise the
PURE overlay-assembly surface only — no real fabro run, no socket bind,
no network call, no 1Password read (the live-verification leg is the
orchestrator's, EXCLUDED here):

- `resolve_sandbox_otel_endpoint` resolves the sandbox->host OTLP
  endpoint from the `LIVESPEC_SANDBOX_OTEL_ENDPOINT` lever, defaulting
  to the Docker default-bridge gateway address (best-determined
  sandbox-reachable host address; the orchestrator's live-verify can
  correct it).
- `cc_otel_overlay_env` produces the exact CC OTel env dict (endpoint,
  http/json protocol matching the JSON-only 29f.7 receiver, correlation
  triple in `OTEL_RESOURCE_ATTRIBUTES`, exporters + telemetry on, ALL
  content flags off) from an injected dispatch context.
- `render_run_config_overlay` projects that env dict into the
  `[environments.<id>.env]` table alongside the existing token +
  sibling-clones keys.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DEFAULT_SANDBOX_OTEL_ENDPOINT,
    SANDBOX_OTEL_ENDPOINT_ENV_VAR,
    cc_otel_overlay_env,
    render_run_config_overlay,
    resolve_sandbox_otel_endpoint,
)

# The CC content-bearing export flags that MUST stay OFF at the source
# (cc-otel-gap-analysis.md §1.5 / telemetry design §3.4): the overlay
# never sets any of them, so CC redacts prompts / tool details / tool
# content / raw API bodies at the source.
_CONTENT_FLAGS = (
    "OTEL_LOG_USER_PROMPTS",
    "OTEL_LOG_TOOL_DETAILS",
    "OTEL_LOG_TOOL_CONTENT",
    "OTEL_LOG_RAW_API_BODIES",
)

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)

# Bound to a local before passing as `token=` so ruff's S106 (hardcoded
# password) does not flag the literal — the same indirection the existing
# overlay tests in test_dispatcher.py use.
_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"


def test_resolve_sandbox_otel_endpoint_defaults_to_bridge_gateway() -> None:
    """An unset lever resolves to the committed Docker-bridge-gateway default."""
    assert resolve_sandbox_otel_endpoint(environ={}) == DEFAULT_SANDBOX_OTEL_ENDPOINT
    # The committed default is the Docker default-bridge gateway on the
    # OTLP/HTTP port — the host as reachable from inside the sandbox (the
    # sandbox's own 127.0.0.1 is NOT the host). Base URL only (CC appends
    # the per-signal /v1/<signal> path itself).
    assert DEFAULT_SANDBOX_OTEL_ENDPOINT == "http://172.17.0.1:4318"


def test_resolve_sandbox_otel_endpoint_honors_the_lever() -> None:
    """The `LIVESPEC_SANDBOX_OTEL_ENDPOINT` lever overrides the default."""
    override = "http://host.docker.internal:4318"
    resolved = resolve_sandbox_otel_endpoint(environ={SANDBOX_OTEL_ENDPOINT_ENV_VAR: override})
    assert resolved == override


def test_resolve_sandbox_otel_endpoint_falls_back_on_blank() -> None:
    """A blank / whitespace-only lever value falls back to the default."""
    assert (
        resolve_sandbox_otel_endpoint(environ={SANDBOX_OTEL_ENDPOINT_ENV_VAR: "   "})
        == DEFAULT_SANDBOX_OTEL_ENDPOINT
    )


def test_cc_otel_overlay_env_shape() -> None:
    """The assembled env is the exact CC OTel projection for the sandbox."""
    env = cc_otel_overlay_env(
        work_item_id="livespec-impl-beads-29f.3",
        dispatch_id="abc123def456",
        endpoint="http://172.17.0.1:4318",
    )
    # Master switch + the three native signals on, all OTLP.
    assert env["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"
    assert env["OTEL_METRICS_EXPORTER"] == "otlp"
    assert env["OTEL_LOGS_EXPORTER"] == "otlp"
    assert env["OTEL_TRACES_EXPORTER"] == "otlp"
    assert env["CLAUDE_CODE_ENHANCED_TELEMETRY_BETA"] == "1"
    # Transport: the host-local E1 receiver, http/json (the 29f.7 receiver
    # is JSON-only), NOT Honeycomb.
    assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://172.17.0.1:4318"
    assert env["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/json"
    assert "honeycomb" not in env["OTEL_EXPORTER_OTLP_ENDPOINT"].lower()
    # No ingest key / auth header on the sandbox — the key stays on the
    # host-local E1 egress stage (telemetry design §3.5).
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in env
    # Short metric interval so a short-lived sandbox does not lose the tail
    # (the metrics-heartbeat feeds 29f.6's oyg LivenessProbe).
    assert env["OTEL_METRIC_EXPORT_INTERVAL"] == "10000"


def test_cc_otel_overlay_env_carries_the_correlation_triple() -> None:
    """`OTEL_RESOURCE_ATTRIBUTES` carries work.item.id + livespec.dispatch.id."""
    env = cc_otel_overlay_env(
        work_item_id="livespec-impl-beads-29f.3",
        dispatch_id="abc123def456",
        endpoint="http://172.17.0.1:4318",
    )
    attrs = _parse_resource_attributes(env["OTEL_RESOURCE_ATTRIBUTES"])
    assert attrs["work.item.id"] == "livespec-impl-beads-29f.3"
    assert attrs["livespec.dispatch.id"] == "abc123def456"
    # Single dataset for all sandbox CC telemetry, sliced by work.item.id;
    # service.name stays CC's own `claude-code` (NOT overridden here).
    assert attrs["service.namespace"] == "livespec-family"
    assert "service.name" not in attrs


def test_cc_otel_overlay_env_leaves_all_content_flags_off() -> None:
    """NONE of the content-bearing CC export flags are ever set (§3.4)."""
    env = cc_otel_overlay_env(work_item_id="wi", dispatch_id="d", endpoint="http://172.17.0.1:4318")
    for flag in _CONTENT_FLAGS:
        assert flag not in env


def test_cc_otel_overlay_env_values_are_all_strings() -> None:
    """Every value is a TOML-projectable string (the env table is str->str)."""
    env = cc_otel_overlay_env(work_item_id="wi", dispatch_id="d", endpoint="http://172.17.0.1:4318")
    assert all(isinstance(value, str) for value in env.values())


def test_render_run_config_overlay_projects_otel_env(tmp_path: Path) -> None:
    """The OTel env keys land in the appended [environments.<id>.env] table."""
    otel_env = cc_otel_overlay_env(
        work_item_id="livespec-impl-beads-29f.3",
        dispatch_id="abc123",
        endpoint="http://172.17.0.1:4318",
    )
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        otel_env=otel_env,
    )
    assert rendered is not None
    env_table = rendered.split("[environments.livespec-ci.env]", 1)[1]
    # The token still projects; the OTel keys ride in the SAME table (TOML
    # forbids declaring [environments.<id>.env] twice). The GitHub token
    # projects under the FULL name GITHUB_TOKEN (never the short GH_TOKEN):
    # gh and git-via-gh prefer GH_TOKEN over GITHUB_TOKEN, so a projected
    # GH_TOKEN would SHADOW Fabro's fresh per-exec GITHUB_TOKEN and go stale
    # past the ~60-min installation-token TTL. GITHUB_TOKEN agrees with
    # Fabro's own name, so Fabro's per-exec `export GITHUB_TOKEN=<fresh>`
    # overwrites this bootstrap value at the (post-TTL) publish node.
    assert 'CLAUDE_CODE_OAUTH_TOKEN = "test-oauth-token"' in env_table
    assert 'GITHUB_TOKEN = "test-github-token"' in env_table
    assert "GH_TOKEN = " not in env_table
    assert 'CLAUDE_CODE_ENABLE_TELEMETRY = "1"' in env_table
    assert 'OTEL_EXPORTER_OTLP_ENDPOINT = "http://172.17.0.1:4318"' in env_table
    assert 'OTEL_EXPORTER_OTLP_PROTOCOL = "http/json"' in env_table
    assert "OTEL_RESOURCE_ATTRIBUTES = " in env_table
    assert "work.item.id=livespec-impl-beads-29f.3" in env_table
    assert "livespec.dispatch.id=abc123" in env_table
    # Content flags are absent from the projection.
    for flag in _CONTENT_FLAGS:
        assert flag not in rendered


def test_render_run_config_overlay_otel_env_is_optional(tmp_path: Path) -> None:
    """Omitting `otel_env` preserves the pre-29f.3 token-only overlay shape."""
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )
    assert rendered is not None
    assert 'CLAUDE_CODE_OAUTH_TOKEN = "test-oauth-token"' in rendered
    assert 'GITHUB_TOKEN = "test-github-token"' in rendered
    assert "GH_TOKEN = " not in rendered
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in rendered
    assert "CLAUDE_CODE_ENABLE_TELEMETRY" not in rendered


def _parse_resource_attributes(raw: str) -> dict[str, str]:
    """Parse a W3C-Baggage-style `k=v,k=v` OTEL_RESOURCE_ATTRIBUTES string."""
    pairs: dict[str, str] = {}
    for entry in raw.split(","):
        key, _, value = entry.partition("=")
        pairs[key.strip()] = value.strip()
    return pairs
