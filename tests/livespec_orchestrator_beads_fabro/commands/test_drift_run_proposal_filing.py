"""The drift run files one proposal per finding, and a retry files no duplicate.

Assertion 2 of `bd-ib-yvjxo4`: "For each `partial` or `unstated` behaviour a
merge adds, the pass files one proposed change with a drift origin naming the
generalization target, with a stable finding identity so a retried pass files
no duplicate."

Four things are pinned, and each is a separate way the assertion fails.

A `stated` verdict files NOTHING, which is the control: a pass that filed on
every verdict would satisfy every positive assertion here while proposing a
change for behaviour the ratified text already states.

`partial` files exactly as `unstated` does. The independent review of this
plan's scoping (research note 005, finding 6) is explicit that counts cannot
discharge the anti-bloat assertions and that `partial` needs proposals too, so
a pass that filed only on `unstated` would leave every half-stated behaviour
unproposed while looking correct on the canonical scenario.

The DRIFT ORIGIN and the GENERALIZATION TARGET are read out of the filed
document rather than off a return value, because the document is what `revise`
adjudicates and a proposal whose origin lived only in the pass's own memory
would reach the human gate indistinguishable from one a session authored.

And the RETRY is driven by running the whole pass twice over the same merge,
not by calling an identity function twice. A stable identity is only worth
anything if the filing path consults it: an identity that is stable while the
filer never reads it files a second proposal under a second name on every
ten-minute tick of the root reconcile timer.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._drift_run import (
    DriftRunOutcome,
    DriftRunSeams,
    run_drift_pass,
)

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_TARGET = "## A governing heading"


@dataclass(kw_only=True)
class _GitRunner:
    """A `CommandRunner` answering the three git reads over one merge."""

    merges: tuple[str, ...] = ("aaaaaaa1",)
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        if argv[1] == "symbolic-ref":
            return CommandResult(exit_code=0, stdout="origin/master\n", stderr="")
        if argv[1] == "rev-list":
            return CommandResult(exit_code=0, stdout="\n".join(self.merges) + "\n", stderr="")
        return CommandResult(exit_code=0, stdout=f"a subject\n+ a hunk for {argv[-1]}\n", stderr="")


def _verdict(*, kind: str) -> str:
    target = "null" if kind == "stated" else f'"{_TARGET}"'
    return (
        f'{{"kind": "{kind}", "stated_by": [], '
        f'"generalization_target": {target}, "rationale": "r"}}'
    )


def _judge(*, kind: str) -> Callable[[str], str]:
    def run_model(prompt: str) -> str:
        _ = prompt
        return _verdict(kind=kind)

    return run_model


def _spec_tree(*, root: Path) -> Path:
    spec_root = root / "SPECIFICATION"
    (spec_root / "proposed_changes").mkdir(parents=True, exist_ok=True)
    (spec_root / "history" / "v001" / "proposed_changes").mkdir(parents=True, exist_ok=True)
    _ = (spec_root / "contracts.md").write_text(
        f"{_TARGET}\n\nSome ratified text.\n", encoding="utf-8"
    )
    return spec_root


def _run(*, root: Path, kind: str, merges: tuple[str, ...] = ("aaaaaaa1",)) -> DriftRunOutcome:
    return run_drift_pass(
        project_root=root,
        frontier="deadbeef",
        seams=DriftRunSeams(
            runner=_GitRunner(merges=merges),
            judge=_judge(kind=kind),
            author="reconcile-pass:test",
            now=lambda: "2026-10-22T00:00:00Z",
        ),
    )


def _filed(*, spec_root: Path) -> list[Path]:
    return sorted((spec_root / "proposed_changes").glob("*.md"))


def test_a_stated_verdict_files_nothing(tmp_path: Path) -> None:
    assert (_COMMANDS / "_drift_run_proposals.py").is_file()
    spec_root = _spec_tree(root=tmp_path)

    outcome = _run(root=tmp_path, kind="stated")

    assert _filed(spec_root=spec_root) == []
    assert outcome.filed == ()


@pytest.mark.parametrize("kind", ["partial", "unstated"])
def test_each_partial_or_unstated_behaviour_files_one_proposal(tmp_path: Path, kind: str) -> None:
    assert (_COMMANDS / "_drift_run_proposals.py").is_file()
    spec_root = _spec_tree(root=tmp_path)

    outcome = _run(root=tmp_path, kind=kind)

    filed = _filed(spec_root=spec_root)
    assert len(filed) == 1
    assert len(outcome.filed) == 1


@pytest.mark.parametrize("kind", ["partial", "unstated"])
def test_the_filed_proposal_carries_a_drift_origin_naming_the_target(
    tmp_path: Path, kind: str
) -> None:
    assert (_COMMANDS / "_drift_run_proposals.py").is_file()
    spec_root = _spec_tree(root=tmp_path)

    outcome = _run(root=tmp_path, kind=kind)

    document = _filed(spec_root=spec_root)[0].read_text(encoding="utf-8")
    assert "drift_origin:" in document
    assert _TARGET in document
    assert outcome.filed[0] in document


def test_a_retried_pass_files_no_duplicate(tmp_path: Path) -> None:
    assert (_COMMANDS / "_drift_run_proposals.py").is_file()
    spec_root = _spec_tree(root=tmp_path)

    first = _run(root=tmp_path, kind="unstated")
    second = _run(root=tmp_path, kind="unstated")

    assert len(_filed(spec_root=spec_root)) == 1
    assert first.filed == (second.filed[0],)


def test_two_merges_adding_unstated_behaviour_file_two_proposals(tmp_path: Path) -> None:
    assert (_COMMANDS / "_drift_run_proposals.py").is_file()
    spec_root = _spec_tree(root=tmp_path)

    outcome = _run(root=tmp_path, kind="unstated", merges=("aaaaaaa1", "bbbbbbb2"))

    # Two merges whose diffs differ only in the sha they name must not collapse
    # onto one identity: the second would read as a duplicate of the first and
    # the behaviour it adds would never be proposed.
    assert len(_filed(spec_root=spec_root)) == 2
    assert len(set(outcome.filed)) == 2
