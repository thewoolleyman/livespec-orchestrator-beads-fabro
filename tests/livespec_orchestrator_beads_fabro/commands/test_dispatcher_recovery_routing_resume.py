"""A drain wave routes a released item to a resume and its wave-mate to a plain run.

Scenario 185's first scenario, and the half of it a unit tier can observe. The
`contracts.md` section "Factory-configurable ACP fallback priority" →
"Recovery from the failed run's preserved work" puts *recovery routing* after the
pre-dispatch wall and BEFORE the admission valve, while the item is still
`ready`, and then has each launch path execute the assigned route on that item's
own copy of the dispatch arguments.

WHY TWO ITEMS AND NOT ONE. The per-item claim is the whole point of the clause:
"Route-specific state MUST NOT be written to arguments shared by the wave." A
one-item wave cannot fail that way — whatever is written to the shared namespace
IS that item's state — so the wave-mate is not decoration, it is the control. It
is a FIRST dispatch with no journaled history at all, which is what makes it
unreleased and therefore routed `fresh` with no remote measurement taken.

WHY THE RECLAIM'S ABSENCE IS ASSERTED AS WELL AS THE RESUME'S PRESENCE. The two
routes are exclusive per dispatch: one FINISHES the dead run's publication, the
other CLEARS it so a fresh start can publish. Running both would preserve the
head to a ref and then delete the very branch the resumed run was about to check
out — and the journal would read like a healthy recovery. Origin IS carrying that
branch here and the journal DOES record an earlier dispatch, so the reclaim was
fully available: its absence is a measurement rather than a vacuous pass.

WHY THE SUBPROCESS SEAM IS PATCHED ON THE CLASS. Three parties reach a shell in
this pass — the forge listing, the factory board, and the reclaim's `ls-remote` —
and each constructs its own `ShellCommandRunner`. Patching the construction site
of one leaves the others live; patching `run` on the class covers every one,
including the recovery routing's own, without this file having to know which
module builds which.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import pytest

# `_dispatcher_admission` is imported for `Admission` AND for its position: it is
# alphabetically first inside this one statement, so Python evaluates it first,
# and importing it ahead of the wave is what breaks a cycle the wave would
# otherwise hit on its own (`_dispatcher_acp_preflight` and
# `_dispatcher_provider_limit_outcome` import each other, and only one entry
# order resolves). Do NOT split this statement or reorder its names: a module
# that imports the wave first fails at COLLECTION, which looks like a Red and
# proves nothing.
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission as admission,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_loop_wave as loop_wave,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import ReworkPass
from livespec_orchestrator_beads_fabro.types import WorkItem

# The released item: a first stall cancel took its run down inside `proof_capture`
# and the disposition returned it to `ready`, so its cancel record anchors a
# resume at that stage on the head the dead run published.
_RELEASED_ID = "bd-ib-qgcpoc"
_RELEASED_RUN = "01M509HNX5KGKSRV04VQEYVWH6"
_RELEASED_DISPATCH = "a7395318d0c945589105940e7936139f"
_RELEASED_PR = 3001
_PUBLISHED_HEAD = "db9feb3900000000000000000000000000000001"

# The wave-mate: never dispatched, so nothing released it and nothing about the
# forge or the factory is measured for it.
_FRESH_ID = "bd-ib-3snvbf"

_RESUME_STAGE = "resume"
_RECLAIM_STAGE_PREFIX = "publish-branch-reclaim"

# The stage a cancel-anchored resume enters at, and the party that decided it.
# Spelled as literals because this file's Red predates the module that would
# export them, and a Red's test bytes are fixed across its Red-to-Green pair.
_CANCEL_ANCHOR_RESUMED_AT = "proof_capture"
_CANCEL_ANCHOR_SOURCE = "watchdog-stall-cancel-record"


class _Shell:
    """A scripted subprocess seam keyed by argv substring, recording every call.

    The script and the log are CLASS state because this stands in for
    `ShellCommandRunner.run` on the real class: every party in the pass builds
    its own runner instance, so instance state would be discarded on each
    construction. `_arm` resets both, which is what keeps one case's log out of
    the next one's assertions.

    Keyed by substring so a case states only what it scripts, and recording the
    joined argv is what lets "origin was never asked about this branch" be read
    as a measurement rather than inferred from a journal that happens to be
    empty.

    AN UNSCRIPTED ARGV FAILS rather than answering a silent success. A default
    answer here would make this seam unable to distinguish "the pass took the
    measurements this case scripted" from "the pass took some other measurement
    and got an empty exit-0 reply", which is exactly the instrument that cannot
    return a hit — and the second reading is how a route decided on a blank
    answer would pass for one decided on evidence.
    """

    answers: ClassVar[dict[str, CommandResult]] = {}
    argvs: ClassVar[list[list[str]]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        _Shell.argvs.append(list(argv))
        joined = " ".join(argv)
        for needle, result in _Shell.answers.items():
            if needle in joined:
                return result
        message = f"unscripted command reached the shell seam: {joined}"
        raise AssertionError(message)


def _arm(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Install the scripted seam for a world where all three measurements succeed.

    The forge names one OPEN pull request at exactly the head the cancel record
    names, so no head has moved; the pull request carries no Proof of Done
    record, which is what lets the cancel row anchor rather than being outranked;
    the factory board answers and holds nothing of this item alive; and origin
    still carries the publish branch.

    THE RECLAIM'S OWN TWO FORGE CALLS ARE SCRIPTED TOO, and that is what makes
    its absence a measurement. With the preserve and the delete unscripted, a
    build that reclaimed would die on the seam's unscripted-argv failure, and the
    case would pass for a build that merely crashed in the right place. Scripted,
    the reclaim can run to completion and journal its row — so the assertion that
    it journaled none is about a reclaim that was fully available and declined.
    """
    _Shell.answers = {
        f"gh pr list --head feat/{_RELEASED_ID}": CommandResult(
            exit_code=0,
            stdout=json.dumps(
                [{"number": _RELEASED_PR, "state": "OPEN", "headRefOid": _PUBLISHED_HEAD}]
            ),
            stderr="",
        ),
        f"gh pr view {_RELEASED_PR} --json comments": CommandResult(
            exit_code=0, stdout=json.dumps({"comments": []}), stderr=""
        ),
        "ps -a --json": CommandResult(exit_code=0, stdout="[]", stderr=""),
        f"ls-remote origin refs/heads/feat/{_RELEASED_ID}": CommandResult(
            exit_code=0,
            stdout=f"{_PUBLISHED_HEAD}\trefs/heads/feat/{_RELEASED_ID}\n",
            stderr="",
        ),
        "gh api --method POST": CommandResult(exit_code=0, stdout="", stderr=""),
        "gh api --method DELETE": CommandResult(exit_code=0, stdout="", stderr=""),
    }
    _Shell.argvs = []
    monkeypatch.setattr(ShellCommandRunner, "run", _Shell.run)


def _work_item(*, item_id: str) -> WorkItem:
    """A ready candidate carrying nothing these seams read but its id and status."""
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="An ordinary re-dispatch after a first stall cancel",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-17T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _journal(*, tmp_path: Path) -> JournalFile:
    """A journal whose newest dispatch of the released item ended in a stall release.

    The record shapes are the production ones — `dispatch-id` at launch,
    `fabro-run` carrying the run id, `watchdog-stall-cancel` carrying the pull
    request and the published head, and `stall-cancel-release` returning the item
    to `ready`. Written directly rather than through `append`, which stamps an
    invoker no writer may supply.

    The wave-mate appears NOWHERE in it, which is what makes it a first dispatch.
    """
    journal = JournalFile(path=tmp_path / "fabro-dispatch-journal.jsonl")
    records: Sequence[dict[str, object]] = (
        {
            "stage": "dispatch-id",
            "work_item_id": _RELEASED_ID,
            "dispatch_id": _RELEASED_DISPATCH,
            "workflow_name": "implement-work-item",
        },
        {"stage": "fabro-run", "work_item_id": _RELEASED_ID, "run_id": _RELEASED_RUN},
        {
            "stage": "watchdog-stall-cancel",
            "work_item_id": _RELEASED_ID,
            "dispatch_id": _RELEASED_DISPATCH,
            "run_id": _RELEASED_RUN,
            "factory": "hp",
            "executing_stage": _CANCEL_ANCHOR_RESUMED_AT,
            "pull_request": _RELEASED_PR,
            "published_head": _PUBLISHED_HEAD,
        },
        {
            "stage": "stall-cancel-release",
            "work_item_id": _RELEASED_ID,
            "status": "ready",
            "run_id": _RELEASED_RUN,
            "factory": "hp",
            "executing_stage": _CANCEL_ANCHOR_RESUMED_AT,
        },
    )
    _ = journal.path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8"
    )
    return journal


def _rows(*, journal: JournalFile, stage_prefix: str) -> tuple[dict[str, Any], ...]:
    """Every row of the journal whose stage starts with `stage_prefix`."""
    written = (
        json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line
    )
    return tuple(record for record in written if str(record.get("stage")).startswith(stage_prefix))


def _args(*, repo: Path, journal: JournalFile) -> argparse.Namespace:
    """The dispatch namespace every seam below reads its own inputs off."""
    return argparse.Namespace(
        repo=str(repo),
        journal=str(journal.path),
        item=None,
        items=None,
        budget=2,
        parallel=1,
        as_json=False,
        dry_run=False,
        skip_ledger_check=True,
        workflow_name=None,
        fabro_bin="/usr/local/bin/fabro",
    )


@dataclass(kw_only=True)
class _Wave:
    """One drain wave's journal, plus the per-item namespaces its launches saw."""

    journal: JournalFile
    launched: dict[str, argparse.Namespace]


def _drive_wave(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Wave:
    """One wave over both candidates, with recovery routing and the reclaim live.

    Everything that would reach a provider, the ledger or a real factory is stood
    in; the forge, the factory board and origin answer through the one scripted
    shell. `dispatch_one` records the namespace each item was launched with,
    which is where the per-item claim is read.
    """
    journal = _journal(tmp_path=tmp_path)
    launched: dict[str, argparse.Namespace] = {}
    items = [_work_item(item_id=_RELEASED_ID), _work_item(item_id=_FRESH_ID)]

    _arm(monkeypatch=monkeypatch)
    monkeypatch.setattr(loop_wave, "await_usable_credential", lambda **_kwargs: None)
    monkeypatch.setattr(loop_wave, "resolve_acp_preflight", lambda **_kwargs: None)
    monkeypatch.setattr(
        loop_wave,
        "admit_and_select",
        lambda **_kwargs: admission.Admission(admitted=list(items), deferred=[], refused=[]),
    )
    monkeypatch.setattr(
        loop_wave, "args_with_dispatch_factory_target", lambda **kwargs: kwargs["args"]
    )
    monkeypatch.setattr(
        loop_wave, "args_with_dispatch_workflow_name", lambda **kwargs: kwargs["args"]
    )

    def _launch(**kwargs: Any) -> DispatchOutcome:
        item_id = str(kwargs["item"].id)
        launched[item_id] = kwargs["args"]
        return DispatchOutcome(
            work_item_id=item_id,
            status="green",
            stage="done",
            pr_number=_RELEASED_PR,
            merge_sha="deadbeef",
            detail="merged",
        )

    monkeypatch.setattr(loop_wave, "dispatch_one", _launch)
    _ = loop_wave.dispatch_loop_wave(
        args=_args(repo=tmp_path, journal=journal),
        repo=tmp_path,
        items=items,
        selected_candidates=items,
        journal=journal,
        janitor=None,
        rework=ReworkPass(scope_ids=frozenset()),
    )
    return _Wave(journal=journal, launched=launched)


def test_the_shell_seam_refuses_a_command_no_case_scripted() -> None:
    """The instrument's own control, which the case below depends on.

    Every claim in this file about what the pass measured rests on the seam
    failing an argv no case scripted. An unexercised refusal is one nobody has
    established fires at all — the same omission the refusal exists to catch —
    and a seam that silently answered exit 0 would make "the route was decided
    on this evidence" indistinguishable from "the route was decided on a blank
    reply".
    """
    _Shell.answers = {}
    _Shell.argvs = []

    with pytest.raises(AssertionError, match="unscripted command"):
        _ = _Shell().run(
            argv=["git", "ls-remote", "origin", "refs/heads/feat/x"],
            cwd=Path("/repo"),
            timeout_seconds=1.0,
        )


def test_a_released_item_resumes_while_its_wave_mate_dispatches_plainly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole first scenario of 185, read off one wave.

    FOUR claims, and each needs the others. The released item's run enters at the
    anchored node on the anchored head — not at `start`, and not on the default
    branch. Its `resume` record is journaled by the drain's OWN journal, so the
    attribution the acceptance pass reads is the Dispatcher's rather than an
    operator's. Neither reclaim row was written for it, though origin was
    carrying its branch and the journal recorded an earlier dispatch. And the
    wave-mate's namespace carries no resume state at all, which is what makes the
    first claim per-item rather than a property of the shared namespace.
    """
    wave = _drive_wave(monkeypatch=monkeypatch, tmp_path=tmp_path)

    resumed = _rows(journal=wave.journal, stage_prefix=_RESUME_STAGE)
    assert [
        {
            key: record[key]
            for key in ("stage", "work_item_id", "pull_request", "head", "resumed_at")
        }
        for record in resumed
    ] == [
        {
            "stage": _RESUME_STAGE,
            "work_item_id": _RELEASED_ID,
            "pull_request": _RELEASED_PR,
            "head": _PUBLISHED_HEAD,
            "resumed_at": _CANCEL_ANCHOR_RESUMED_AT,
        }
    ]
    assert resumed[0]["resumed_at_source"] == _CANCEL_ANCHOR_SOURCE
    assert _RELEASED_RUN in resumed[0]["earlier_run_ids"]
    # The drain's own identity, stamped once by the journal the drain holds.
    assert resumed[0]["invoker"] == wave.journal.identity.invoker
    # The released item enters at the anchored node, on the anchored head.
    assert (
        getattr(wave.launched[_RELEASED_ID], "resume_entry_node", None) == _CANCEL_ANCHOR_RESUMED_AT
    )
    assert getattr(wave.launched[_RELEASED_ID], "resume_head", None) == _PUBLISHED_HEAD
    # Neither reclaim row, for either item, and origin never asked about either
    # branch — though it carries the released item's.
    assert _rows(journal=wave.journal, stage_prefix=_RECLAIM_STAGE_PREFIX) == ()
    assert [argv for argv in _Shell.argvs if "ls-remote" in " ".join(argv)] == []
    # The wave-mate starts at `start`, on the default branch, with no resume head.
    assert getattr(wave.launched[_FRESH_ID], "resume_entry_node", None) is None
    assert getattr(wave.launched[_FRESH_ID], "resume_head", None) is None
