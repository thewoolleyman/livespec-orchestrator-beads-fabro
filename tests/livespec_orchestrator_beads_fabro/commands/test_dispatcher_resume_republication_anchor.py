"""The retained-run republication anchor's factory-record bounds."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import ResumeAnchor

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_republication_anchor"
_OLD_HEAD = "a" * 40
_NEW_HEAD = "b" * 40


@dataclass(kw_only=True)
class _Runner:
    """A git ancestry answer plus the argv the anchor chose to ask."""

    exit_code: int = 0
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        return CommandResult(exit_code=self.exit_code, stdout="", stderr="")


def _anchor() -> ResumeAnchor:
    return ResumeAnchor(
        record=None,
        run_id="01M4XKJE3GZKJ739SRE9VTRDX2",
        head=_OLD_HEAD,
        resumed_at="review",
        source="pull-request-latest-record",
    )


def _payload(*, terminal_head: str = _NEW_HEAD, terminal_node: str = "proof_capture") -> object:
    return [
        {
            "stages": {
                "proof_capture@1": {"state": "succeeded"},
                "publish_draft@2": {"state": "succeeded"},
                "proof_capture@2": {"state": "failed"},
            },
            "checkpoint": {"current_node": terminal_node, "git_commit_sha": terminal_head},
        }
    ]


def test_only_a_retained_runs_terminal_republication_anchors_fresh_capture(tmp_path: Path) -> None:
    """The positive control requires all factory-record facts and ancestry."""
    module = importlib.import_module(_MODULE)
    runner = _Runner()

    result = module.republication_anchor(
        provisional=_anchor(),
        current_head=_NEW_HEAD,
        payload=_payload(),
        repo=tmp_path,
        runner=runner,
    )

    assert result is not None
    assert result.head == _NEW_HEAD
    assert result.resumed_at == "proof_capture"
    assert result.source == "factory-run-record"
    assert runner.argvs[0][1:] == ["merge-base", "--is-ancestor", _OLD_HEAD, _NEW_HEAD]


def test_missing_or_nonterminal_republication_evidence_never_calls_git(tmp_path: Path) -> None:
    """The anchor is factory-record-only, not an inference from a moved branch."""
    module = importlib.import_module(_MODULE)
    for provisional, current_head, payload in (
        (None, _NEW_HEAD, _payload()),
        (_anchor(), None, _payload()),
        (_anchor(), _OLD_HEAD, _payload()),
        (_anchor(), _NEW_HEAD, None),
        (_anchor(), _NEW_HEAD, _payload(terminal_head=_OLD_HEAD)),
        (_anchor(), _NEW_HEAD, _payload(terminal_node="review")),
        (
            _anchor(),
            _NEW_HEAD,
            [{"checkpoint": {"current_node": "proof_capture", "git_commit_sha": _NEW_HEAD}}],
        ),
        (
            _anchor(),
            _NEW_HEAD,
            [
                {
                    "stages": {"proof_capture@1": {"state": "succeeded"}},
                    "checkpoint": {"current_node": "proof_capture", "git_commit_sha": _NEW_HEAD},
                }
            ],
        ),
    ):
        runner = _Runner()
        assert (
            module.republication_anchor(
                provisional=provisional,
                current_head=current_head,
                payload=payload,
                repo=tmp_path,
                runner=runner,
            )
            is None
        )
        assert runner.argvs == []


def test_a_nonancestor_proof_head_keeps_the_moved_head_refusal(tmp_path: Path) -> None:
    """An unrelated new head is never the earlier run's continuation."""
    module = importlib.import_module(_MODULE)
    runner = _Runner(exit_code=1)

    assert (
        module.republication_anchor(
            provisional=_anchor(),
            current_head=_NEW_HEAD,
            payload=_payload(),
            repo=tmp_path,
            runner=runner,
        )
        is None
    )
    assert len(runner.argvs) == 1


def test_the_checkpoint_edge_target_also_proves_the_gap_before_capture(tmp_path: Path) -> None:
    """Between visits, the terminal checkpoint names capture as its selected edge target."""
    module = importlib.import_module(_MODULE)
    payload = _payload()
    assert isinstance(payload, list)
    record = payload[0]
    assert isinstance(record, dict)
    record["checkpoint"] = {"next_node_id": "proof_capture", "git_commit_sha": _NEW_HEAD}

    result = module.republication_anchor(
        provisional=_anchor(),
        current_head=_NEW_HEAD,
        payload=payload,
        repo=tmp_path,
        runner=_Runner(),
    )

    assert result is not None
