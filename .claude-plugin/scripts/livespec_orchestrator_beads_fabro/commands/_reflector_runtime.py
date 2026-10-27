"""ACP-candidate invocation and filing runtime for the OOB reflector."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
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


def resolve_mode(*, raw: str | None) -> str:
    """Resolve the opt-in reflector mode."""
    if raw == _MODE_OBSERVE:
        return _MODE_OBSERVE
    if raw == _MODE_FILE:
        return _MODE_FILE
    return _MODE_OFF


def _resolve_positive_float(*, environ: dict[str, str], name: str, default: float) -> float:
    raw = environ.get(name, "")
    if raw == "":
        return default
    parsed = parse_float(text=raw)
    if isinstance(parsed, FloatParseFailure):
        return default
    return parsed if parsed > 0 else default


def resolve_reflector_timeout_seconds(*, environ: dict[str, str]) -> float:
    """The per-candidate invocation ceiling."""
    return _resolve_positive_float(
        environ=environ,
        name=_REFLECTOR_TIMEOUT_ENV,
        default=_REFLECTOR_TIMEOUT_SECONDS,
    )


def acp_reflector_argv(*, candidate: AcpCandidate, prompt: str) -> list[str]:
    """Render a candidate invocation without selecting a provider or model here."""
    return [*shlex.split(candidate.adapter.command), *candidate.adapter.args, "-p", prompt]


def reflector_prompt(*, repo: Path) -> str:
    """The reference-anchored judgement request passed to each ACP candidate."""
    return (
        "You are the out-of-band reflector for the livespec dispatcher loop in "
        f"repo {repo.name}. Review the recent dispatch evidence available to you; "
        "sample failed and blocked runs, latency and cost outliers, and green runs "
        "as a control. Emit ONLY a JSON object of the shape "
        '{"findings": [{"category": str, "stage": str, "severity": '
        '"critical"|"warn"|"info", "subject": str, "detail": str, '
        '"occurrences": int, "work_item_id": str|null, "score": number, '
        '"label": str}]}. Never include credentials, tokens, or remote URLs '
        "with embedded credentials in any field."
    )


def _candidate_reply(
    *,
    candidate: AcpCandidate,
    prompt: str,
    repo: Path,
    runner: CommandRunner,
) -> str | None:
    result: CommandResult = runner.run(
        argv=acp_reflector_argv(candidate=candidate, prompt=prompt),
        cwd=repo,
        timeout_seconds=resolve_reflector_timeout_seconds(environ=dict(os.environ)),
        env=dict(candidate.adapter.env),
    )
    return result.stdout if result.exit_code == 0 else None


def run_pass(  # noqa: PLR0913
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
    """Run the resolved chain and file only a structured findings verdict."""
    prompt = reflector_prompt(repo=repo)
    reply = first_verdict(
        candidates=candidates,
        invoke=lambda *, candidate: _candidate_reply(
            candidate=candidate,
            prompt=prompt,
            repo=repo,
            runner=runner,
        ),
        is_verdict=lambda raw: parse_findings_verdict(raw=raw) is not None,
    )
    check_budget(deadline=deadline)
    if reply is None:
        journal.append(
            record={
                "stage": "reflector-oob-judgement-did-not-run",
                "reason": "no dod_gate candidate returned a structured findings verdict",
                "candidate_count": len(candidates),
            }
        )
        return None
    findings = parse_findings_verdict(raw=reply)
    if findings is None:
        journal.append(
            record={
                "stage": "reflector-oob-judgement-did-not-run",
                "reason": "accepted dod_gate reply could not be parsed as a verdict",
                "candidate_count": len(candidates),
            }
        )
        return None
    emit_spans(findings=findings, spans_path=spans_path)
    check_budget(deadline=deadline)
    if mode == _MODE_OBSERVE:
        journal.append(
            record={
                "stage": "reflector-oob",
                "mode": mode,
                "finding_count": len(findings),
            }
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
