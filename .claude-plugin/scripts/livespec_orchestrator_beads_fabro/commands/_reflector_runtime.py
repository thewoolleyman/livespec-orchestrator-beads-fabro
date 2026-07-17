"""Runtime configuration and Claude invocation helpers for the OOB reflector."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from contextlib import ExitStack
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._reflector_filing import (
    JournalWriter,
    ReflectorReport,
    check_budget,
    file_findings,
)
from livespec_orchestrator_beads_fabro.commands._reflector_findings_parse import parse_findings
from livespec_orchestrator_beads_fabro.commands._reflector_lessons import LessonsProposer
from livespec_orchestrator_beads_fabro.commands._reflector_spans import emit_spans
from livespec_orchestrator_beads_fabro.effects import FloatParseFailure, parse_float

__all__: list[str] = [
    "build_mcp_config",
    "claude_reflector_argv",
    "reflector_prompt",
    "resolve_claude_path",
    "resolve_claude_timeout_seconds",
    "resolve_mode",
    "resolve_strict_mcp",
    "run_claude_reflector",
    "run_pass",
]

_MODE_OFF = "off"
_MODE_OBSERVE = "observe"
_MODE_FILE = "file"
_HONEYCOMB_MCP_URL = "https://mcp.honeycomb.io/mcp"
_HONEYCOMB_MCP_SERVER_NAME = "honeycomb"
_HONEYCOMB_MCP_TOOL_SCOPE = f"mcp__{_HONEYCOMB_MCP_SERVER_NAME}"
_CLAUDE_TIMEOUT_ENV = "LIVESPEC_REFLECTOR_CLAUDE_TIMEOUT_SECONDS"
_CLAUDE_TIMEOUT_SECONDS = 600.0
_CLAUDE_PATH_ENV = "LIVESPEC_REFLECTOR_CLAUDE_PATH"
_CLAUDE_LOCAL_BIN_FALLBACK = "~/.local/bin/claude"
_STRICT_MCP_ENV = "LIVESPEC_REFLECTOR_STRICT_MCP"
_STRICT_MCP_FALSEY = frozenset({"off", "false", "0", "no"})
_REFLECTOR_MODEL_ENV = "LIVESPEC_REFLECTOR_MODEL"
_DEFAULT_REFLECTOR_MODEL = "claude-opus-4-8"


def resolve_mode(*, raw: str | None) -> str:
    """Resolve the `LIVESPEC_REFLECTOR_OOB` lever to a known mode.

    Default is OFF (unlike the mechanical stage's `observe`): a real
    `claude -p` is expensive + side-effectful, so the out-of-band reflector
    is strictly opt-in. Only the explicit `observe` / `file` values arm it.
    """
    if raw == _MODE_OBSERVE:
        return _MODE_OBSERVE
    if raw == _MODE_FILE:
        return _MODE_FILE
    return _MODE_OFF


def _resolve_positive_float(*, environ: dict[str, str], name: str, default: float) -> float:
    """Resolve a positive-float env lever, falling back on absent/bad/≤0 values.

    Mirrors `_dispatcher_cost._resolve_cap`: an unset, empty, unparseable, or
    non-positive value reads as the committed default rather than crashing the
    fail-open stage (a 0/negative time-box would be a self-inflicted hang).
    """
    raw = environ.get(name, "")
    if raw == "":
        return default
    parsed = parse_float(text=raw)
    if isinstance(parsed, FloatParseFailure):
        return default
    return parsed if parsed > 0 else default


def resolve_claude_timeout_seconds(*, environ: dict[str, str]) -> float:
    """The `claude -p` subprocess ceiling: env override or the 600s default.

    Raised from the silently-fatal 90s (29f.8 gap 1): a real review took ~371s,
    so 90s ALWAYS timed out + fail-softed to 0 findings. Operators tune larger
    telemetry windows via `LIVESPEC_REFLECTOR_CLAUDE_TIMEOUT_SECONDS`. The
    fallback reads the module `_CLAUDE_TIMEOUT_SECONDS` alias (which is the
    committed default) so a test that monkeypatches it still flows through.
    """
    return _resolve_positive_float(
        environ=environ, name=_CLAUDE_TIMEOUT_ENV, default=_CLAUDE_TIMEOUT_SECONDS
    )


def resolve_claude_path(*, environ: dict[str, str]) -> str:
    """Resolve the `claude` executable for the host dispatcher (29f.8 gap 3).

    Under `with-livespec-env.sh` the bash PATH is minimal (no `~/.local/bin`),
    so a bare `claude` argv[0] fail-opens with `FileNotFoundError: 'claude'`
    and the reflector silently does nothing. Resolution order: the explicit
    `LIVESPEC_REFLECTOR_CLAUDE_PATH` override → `shutil.which("claude")` → the
    conventional `~/.local/bin/claude` (only if it exists) → bare `"claude"`
    (last resort; lets the runner surface the FileNotFoundError honestly).
    """
    override = environ.get(_CLAUDE_PATH_ENV, "").strip()
    if override:
        return override
    found = shutil.which("claude")
    if found is not None:
        return found
    local_bin = Path(_CLAUDE_LOCAL_BIN_FALLBACK).expanduser()
    if local_bin.is_file():
        return str(local_bin)
    return "claude"


def resolve_strict_mcp(*, environ: dict[str, str]) -> bool:
    """Whether the headless judge runs with `--strict-mcp-config` (29f.8 follow-up).

    DEFAULT = strict ON: an unset (or empty) `LIVESPEC_REFLECTOR_STRICT_MCP`
    reads as `True`, so the judge loads ONLY the `--mcp-config` hosted
    Honeycomb server (the durable API-key path) and never falls back to an
    ambient OAuth honeycomb plugin whose token can expire unattended. An
    explicit falsey value (`off` / `false` / `0` / `no`, case- and
    whitespace-insensitive) is the opt-out escape hatch that restores the
    prior ambient-plugin-permitted behavior. Any other value keeps strict on.
    Mirrors the tolerant, always-wired shape of the other env resolvers.
    """
    return environ.get(_STRICT_MCP_ENV, "").strip().lower() not in _STRICT_MCP_FALSEY


def build_mcp_config(*, api_key: str) -> dict[str, object]:
    """Build the `--mcp-config` JSON wiring the hosted Honeycomb MCP server.

    The reflector reads the already-scrubbed pass evidence from the hosted
    Honeycomb MCP at `https://mcp.honeycomb.io/mcp` over HTTP (the `/mcp`
    path — the bare host 404s; the EU region variant is
    `https://mcp.eu1.honeycomb.io/mcp`, not currently wired).

    Auth contract (Honeycomb headless-agent docs): the `Authorization:
    Bearer <key>` value MUST be a Honeycomb API key in the `<KEY_ID>:
    <SECRET_KEY>` composite form (a team-owner-generated key), scoped to
    "Model Context Protocol (Read)" + "Environments (Read)". A team-member
    key, or a key missing those scopes, fails the MCP handshake. The key
    VALUE flows only into the generated temp config (probe-only hygiene:
    never echoed, never journaled, never put on a span).
    """
    return {
        "mcpServers": {
            _HONEYCOMB_MCP_SERVER_NAME: {
                "type": "http",
                "url": _HONEYCOMB_MCP_URL,
                "headers": {"Authorization": f"Bearer {api_key}"},
            }
        }
    }


def claude_reflector_argv(
    *,
    prompt: str,
    mcp_config_path: Path,
    model: str,
    claude_path: str = "claude",
    strict_mcp: bool = True,
) -> list[str]:
    """Build the headless `claude -p` argv (best-practices §7 decision 9).

    A plain headless invocation — NOT a fabro run (recursion hazard). The
    prompt drives the reference-anchored single-strong-judge review; the
    MCP config grants read-only Honeycomb access; `--output-format json`
    yields a machine envelope the runtime parses.

    `claude_path` is the resolved executable (29f.8 gap 3): under the env
    wrapper's minimal PATH a bare `claude` is not found, so the host dispatcher
    passes an absolute path. `--allowedTools` scopes headless tool permission to
    the ONE configured honeycomb MCP server (29f.8 gap 4): a headless `claude -p`
    grants no tools by default, so without this the MCP review can call nothing
    and produces an empty pass. The scope is `mcp__<server>` — the minimal grant
    (every honeycomb tool, nothing else), NOT `--dangerously-skip-permissions`.

    `strict_mcp` (29f.8 follow-up; default `True`): when set, appends
    `--strict-mcp-config` so claude loads ONLY the `--mcp-config` honeycomb
    server and IGNORES any ambient OAuth honeycomb plugin (whose token can
    expire unattended and silently blind the reflector). The opt-out
    (`strict_mcp=False`) omits the flag, restoring the prior ambient-permitted
    behavior. The resolved value is threaded in by `run_claude_reflector`
    (via `resolve_strict_mcp`), mirroring how `claude_path` is threaded.
    """
    strict_flag = ["--strict-mcp-config"] if strict_mcp else []
    return [
        claude_path,
        "-p",
        prompt,
        "--mcp-config",
        str(mcp_config_path),
        "--allowedTools",
        _HONEYCOMB_MCP_TOOL_SCOPE,
        "--model",
        model,
        "--output-format",
        "json",
        *strict_flag,
    ]


def run_claude_reflector(
    *,
    runner: CommandRunner,
    prompt: str,
    repo: Path,
    api_key: str,
    model: str,
) -> CommandResult:
    """Invoke the headless `claude -p` reflector through the subprocess seam.

    Writes the `--mcp-config` to a throwaway temp file (the key VALUE never
    leaves this function except into that file), runs `claude -p` through
    the injected `CommandRunner` (so the hermetic tier injects a fake and
    NO real `claude -p` / MCP call ever fires in a test), and cleans the
    temp file up afterward. A non-zero / timeout result surfaces as data,
    never an exception (the runner contract).
    """
    config = build_mcp_config(api_key=api_key)
    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - cleaned in finally
        mode="w", suffix="-honeycomb-mcp.json", delete=False, encoding="utf-8"
    )
    config_path = Path(handle.name)
    claude_path = resolve_claude_path(environ=dict(os.environ))
    timeout_seconds = resolve_claude_timeout_seconds(environ=dict(os.environ))
    strict_mcp = resolve_strict_mcp(environ=dict(os.environ))
    with ExitStack() as stack:
        _ = stack.callback(handle.close)
        _ = stack.callback(lambda: config_path.unlink(missing_ok=True))
        json.dump(config, handle)
        handle.close()
        return runner.run(
            argv=claude_reflector_argv(
                prompt=prompt,
                mcp_config_path=config_path,
                model=model,
                claude_path=claude_path,
                strict_mcp=strict_mcp,
            ),
            cwd=repo,
            timeout_seconds=timeout_seconds,
        )


def reflector_prompt(*, repo: Path) -> str:
    """The reference-anchored single-strong-judge review prompt (§1.1).

    Instructs the judge to query Honeycomb GROUPed BY `work.item.id`,
    sample all `failed`/`blocked` runs + top-k latency/cost outliers + ~10%
    green as a control, and emit a STRUCTURED JSON findings list this
    module parses. The prompt is static text (no secret, no env value).
    """
    return (
        "You are the out-of-band reflector for the livespec dispatcher loop in "
        f"repo {repo.name}. Using the Honeycomb MCP tools, review the recent "
        "dispatch evidence: query GROUP BY work.item.id; sample ALL failed and "
        "blocked runs, the top-k latency and cost outliers, and ~10% of green "
        "runs as a control. Act as a single strong judge against the loop's "
        "reference behavior. Emit ONLY a JSON object of the shape "
        '{"findings": [{"category": str, "stage": str, "severity": '
        '"critical"|"warn"|"info", "subject": str, "detail": str, '
        '"occurrences": int, "work_item_id": str|null, "score": number, '
        '"label": str}]}. Never include credentials, tokens, or remote URLs '
        "with embedded credentials in any field."
    )


def run_pass(  # noqa: PLR0913 - kw-only fail-open stage; each is an independent seam input.
    *,
    repo: Path,
    journal: JournalWriter,
    spans_path: Path,
    runner: CommandRunner,
    lessons_proposer: LessonsProposer,
    mode: str,
    api_key: str,
    deadline: float,
) -> ReflectorReport:
    """The scan-file-emit body (wrapped fail-open by `run_reflector_oob`)."""
    model = os.environ.get(_REFLECTOR_MODEL_ENV, "").strip() or _DEFAULT_REFLECTOR_MODEL
    result = run_claude_reflector(
        runner=runner, prompt=reflector_prompt(repo=repo), repo=repo, api_key=api_key, model=model
    )
    check_budget(deadline=deadline)
    findings = parse_findings(raw=result.stdout)
    emit_spans(findings=findings, spans_path=spans_path)
    check_budget(deadline=deadline)
    if mode == _MODE_OBSERVE:
        journal.append(
            record={"stage": "reflector-oob", "mode": mode, "finding_count": len(findings)}
        )
        return ReflectorReport(
            mode=mode,
            repo=str(repo),
            findings=findings,
            filed=(),
            bumped=(),
            muted=(),
            digested=tuple(f.category for f in findings),
            lesson_proposed=False,
        )
    return file_findings(
        repo=repo,
        journal=journal,
        findings=findings,
        lessons_proposer=lessons_proposer,
        mode=mode,
        deadline=deadline,
    )
