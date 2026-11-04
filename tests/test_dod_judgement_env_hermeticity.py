"""The suite never takes a LIVE Definition-of-Done judgement on its own host.

WHAT THIS BINDS. `tests/conftest.py`'s `_hermetic_dod_judgement_judge` points
`LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH` at a path that does not exist, for every
case that does not set the name itself. `run_dod_judgement` defaults to a real
`ShellCommandRunner` when no runner is injected, and `resolve_judge_path`
resolves the override, then `PATH`, then the conventional `~/.local/bin/claude`
install — so on a host where ANY of the last two resolves, the pre-admission
judgement every filing takes is a live model call. The override is the only
layer a test process can occupy without touching `PATH` or `HOME`, which is why
it rather than either of those is what this fixture sets.

WHY THIS EXISTS AT ALL. The asymmetry hides the defect in the one place it costs
the most, exactly as it does for `_hermetic_operator_attribution_env` beside it.
Continuous integration, the delegated cluster gate and every factory sandbox
carry no `claude` executable, so the suite is permanently green there; the vps
operator host DOES carry one, so `just check` run on it both spends real tokens
and reds a case whose fixture item the live judge declines. Measured on vps at
master f7ce3eea:
`test_factory_size_justification_gate_scenario153.py::test_consensus_first_cut_requires_an_adopted_ceiling_and_has_no_size_exception`
filed its fixture item at `pending-approval` instead of `ready`, because the live
judge rejected its placeholder assertions as having no observable subject. That
red blocks every local commit staging a `.py` on such a host (work-item
bd-ib-7xkeko).

HOW THE JUDGE IS STOOD IN, AND WHY NOT AT THE SEAM. The judgement reaches the
model through a subprocess, so an in-process double would leave `PATH`
resolution — the layer the defect actually arrives through — unexercised. A
REAL executable named `claude`, first on `PATH`, that records each invocation to
a file is what makes "the judge was never executed" an observation rather than
an inference: without the fixture it runs, writes its log, and its declining
verdict holds the filed item back, so both halves of the second case fail.

ONE ASSERTION SHAPE IS LOAD-BEARING. `UNAVAILABLE_COMMENT_MARKER` CONTAINS
`JUDGEMENT_COMMENT_MARKER` as a prefix, so "no verdict was taken" cannot be
asserted by containment — a did-not-run record satisfies it. It is asserted on
each comment's FIRST LINE being exactly the taken-verdict marker, which is the
same discrimination `_marker_of` performs in production.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    JUDGEMENT_COMMENT_MARKER,
    UNAVAILABLE_COMMENT_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    CAUSE_NO_ELIGIBLE_MODEL,
    resolve_judge_path,
)
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    file_captured_work_item,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

# THE OVERRIDE'S NAME, SPELLED AS A LITERAL AND BOUND BELOW. Reaching for the
# production constant would make this module agree with it whatever it said —
# including after a rename that left the conftest fixture behind, which is the
# drift that causes this class of defect. The name is private to
# `_dispatcher_dod_judgement_run`, so the literal is kept honest by handing it
# to the production resolver instead of by comparing it to an import.
_JUDGE_PATH_ENV = "LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH"

# The reference the fixture item's Definition of Done names, and the heading the
# fixture spec tree carries for it to resolve against. An unresolved reference is
# a MECHANICAL finding, which withholds `ready` before the judgement is reached
# at all — so a fixture whose reference did not resolve would route to
# `pending-approval` for a reason that has nothing to do with the judge.
_HEADING = "## Scenario 174 — The Definition-of-Done judgement runs before admission"


def _config(*, repo_root: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    _ = (spec / "scenarios.md").write_text(f"{_HEADING}\n", encoding="utf-8")
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-judge-hermeticity",
        type="bug",
        status="backlog",
        title="A filed slice whose judgement must not reach a model",
        description=(
            "## Definition of Done\n"
            "\n"
            "- The filed slice lands its change.\n"
            "\n"
            f"References: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-20T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


_CHECKLIST = DefinitionOfReadyChecklist(
    single_coherent_done=True,
    autonomously_verifiable=True,
    autonomy_tiered=True,
    dependency_linked=True,
    repo_targeted=True,
    above_floor=True,
)


@pytest.fixture
def _fake_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _install_recording_judge(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put a real, declining `claude` first on `PATH` that logs each invocation.

    Its reply DECLINES, so a judgement that does reach it holds the filed item
    back: the routing assertion and the invocation-log assertion then fail
    together rather than one of them carrying the case alone.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "judge-invocations.log"
    script = bin_dir / "claude"
    _ = script.write_text(
        "#!/bin/sh\n"
        f"printf 'invoked\\n' >> \"{log}\"\n"
        "cat <<'REPLY'\n"
        '{"outcome": "failed", "failure_reason": "a live judge ran in the test suite."}\n'
        "REPLY\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return log


def _comment_bodies(*, config: StoreConfig, item_id: str) -> tuple[str, ...]:
    """Every comment body on one item, read through the surface that carries them.

    `bd show --json` carries no comments at all, so the comment listing is the
    only read that can distinguish a landed record from a lost one, and the body
    lives under `text` rather than `body`.
    """
    return tuple(
        str(comment["text"])
        for comment in make_beads_client(config=config).list_comments(issue_id=item_id)
        if isinstance(comment.get("text"), str)
    )


def test_the_resolved_judge_path_is_a_path_no_host_carries() -> None:
    """Every case starts from an override naming an executable that cannot run.

    This is the red local `just check`'s own failure condition, caught at its
    source: the production resolver reads the override out of `os.environ`, so
    an unrunnable answer here is what makes a filing answer the same way on the
    vps operator host, on a developer host, in continuous integration and
    inside a factory sandbox.
    """
    resolved = resolve_judge_path(environ=dict(os.environ))

    assert resolved == os.environ[_JUDGE_PATH_ENV]
    assert not Path(resolved).exists()


@pytest.mark.usefixtures("_fake_tenant")
def test_a_filing_never_executes_a_judge_resolvable_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A filing routes to `ready` on an unavailable judgement, spending nothing.

    The `PATH` judge is the one a host actually carries, so a filing that leaves
    its log absent is a filing that never reached a model — and the item still
    routes exactly as it does where no judge exists, with the record on it
    saying the judgement did not happen.
    """
    repo = _repo(tmp_path=tmp_path)
    log = _install_recording_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)
    config = _config(repo_root=repo)
    item = _item()

    routed = file_captured_work_item(path=config, item=item, checklist=_CHECKLIST)

    assert not log.exists()
    assert is_successful(routed)
    assert unsafe_perform_io(routed.unwrap()) == "ready"
    bodies = _comment_bodies(config=config, item_id=item.id)
    unavailable = [body for body in bodies if body.startswith(UNAVAILABLE_COMMENT_MARKER)]
    assert len(unavailable) == 1
    assert CAUSE_NO_ELIGIBLE_MODEL in unavailable[0]
    # Containment cannot carry this one: the unavailable marker has the taken
    # marker as its prefix, so the discrimination is the first line, exactly as
    # the production reader performs it.
    assert [
        body for body in bodies if body.strip().partition("\n")[0] == JUDGEMENT_COMMENT_MARKER
    ] == []


def test_a_case_that_sets_the_override_still_has_its_own_value_honoured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the fixture occupies the override, it does not seize it.

    Without this, the assertions above would be satisfied just as well by a
    fixture that made the name permanently unsettable — which would break every
    case that names its own judge deliberately, from the two Scenario 174
    modules to `test_groom_variant_dod_judgement.py`. It also binds the literal
    this module spells: the value comes back through the production resolver, so
    a rename of the production name reds this case rather than leaving the
    fixture quietly pointing at nothing.
    """
    own = tmp_path / "my-own-judge"
    monkeypatch.setenv(_JUDGE_PATH_ENV, str(own))

    assert resolve_judge_path(environ=dict(os.environ)) == str(own)
