"""Runtime helpers for the governed-ACP out-of-band reflector."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._reflector_acp_chain import first_verdict
from livespec_orchestrator_beads_fabro.commands._reflector_filing import (
    JournalWriter,
    ReflectorReport,
    check_budget,
    file_findings,
)
from livespec_orchestrator_beads_fabro.commands._reflector_findings_parse import (
    parse_findings,
    parse_findings_verdict,
)
from livespec_orchestrator_beads_fabro.commands._reflector_lessons import LessonsProposer
from livespec_orchestrator_beads_fabro.commands._reflector_spans import emit_spans
from livespec_orchestrator_beads_fabro.effects import FloatParseFailure, parse_float

__all__: list[str] = [
    "acp_reflector_argv",
    "reflector_prompt",
    "resolve_mode",
    "resolve_reflector_timeout_seconds",
    "run_pass",
]

_MODE_OFF = "off"
_MODE_OBSERVE = "observe"
_MODE_FILE = "file"
_REFLECTOR_TIMEOUT_ENV = "LIVESPEC_REFLECTOR_TIMEOUT_SECONDS"
_REFLECTOR_TIMEOUT_SECONDS = 600.0


def acp_reflector_argv(*, candidate: AcpCandidate, prompt: str) -> list[str]:
    """Render one governed ACP candidate without selecting a model locally."""
    return [*shlex.split(candidate.adapter.command), *candidate.adapter.args, "-p", prompt]


def resolve_mode(*, raw: str | None) -> str:
    """Resolve the `LIVESPEC_REFLECTOR_OOB` lever to a known mode.

    Default is OFF (unlike the mechanical stage's `observe`): a real
    A host judgement is expensive and side-effectful, so the out-of-band reflector
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


def resolve_reflector_timeout_seconds(*, environ: dict[str, str]) -> float:
    """Resolve the governed candidate execution ceiling."""
    return _resolve_positive_float(
        environ=environ, name=_REFLECTOR_TIMEOUT_ENV, default=_REFLECTOR_TIMEOUT_SECONDS
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
    candidates: tuple[AcpCandidate, ...],
    deadline: float,
) -> ReflectorReport | None:
    """The scan-file-emit body (wrapped fail-open by `run_reflector_oob`)."""
    prompt = reflector_prompt(repo=repo)

    def invoke(*, candidate: AcpCandidate) -> str | None:
        return _candidate_reply(candidate=candidate, prompt=prompt, repo=repo, runner=runner)

    raw = first_verdict(
        candidates=candidates,
        invoke=invoke,
        is_verdict=lambda reply: parse_findings_verdict(raw=reply) is not None,
    )
    check_budget(deadline=deadline)
    if raw is None:
        journal.append(
            record={
                "stage": "reflector-oob-judgement-did-not-run",
                "reason": "no dod_gate candidate returned a structured findings verdict",
                "candidate_count": len(candidates),
            }
        )
        return None
    findings = parse_findings(raw=raw)
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


def _candidate_reply(
    *, candidate: AcpCandidate, prompt: str, repo: Path, runner: CommandRunner
) -> str | None:
    """Run one candidate and return only a successful reply for verdict parsing."""
    result = runner.run(
        argv=acp_reflector_argv(candidate=candidate, prompt=prompt),
        cwd=repo,
        timeout_seconds=resolve_reflector_timeout_seconds(environ=dict(os.environ)),
        env=dict(candidate.adapter.env),
    )
    return result.stdout if result.exit_code == 0 else None
