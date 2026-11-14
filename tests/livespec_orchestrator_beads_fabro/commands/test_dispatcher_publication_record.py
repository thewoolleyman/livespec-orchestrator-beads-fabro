"""The pull-request publication binding used by resume and recovery routing."""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import ProofRecord
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_run_age import (
    published_head_relation,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_publication_record"
_GATHER_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_publication_record.py"
)
_BOT = "thewoolleyman-factory-bot[bot]"
_HEAD = "a" * 40
_OTHER_HEAD = "b" * 40
_RUN = "01M7PUBLICATIONRUN"
_LATER_RUN = "01M7LATERPUBLICATIONRUN"
_PROOF_RUN = "01M7PROOFRUN"
_ITEM_ID = "bd-ib-st4obs"
_PR = 4515


def _record_body(*, run: str = _RUN, head: str = _HEAD, stage: str = "publish_draft") -> str:
    return "\n".join(
        (
            "livespec-publication-record",
            f"run-id: {run}",
            f"head: {head}",
            f"pull-request: {_PR}",
            f"stage: {stage}",
            "pushed-at: 2026-11-13T12:37:00Z",
        )
    )


def _comment(*, body: object, login: str | None = _BOT) -> dict[str, object]:
    comment: dict[str, object] = {"body": body}
    if login is not None:
        comment["author"] = {"login": login}
    return comment


def _proof_record(*, run: str, head: str) -> ProofRecord:
    return ProofRecord(
        verdict="captured",
        run_id=run,
        timestamp="2026-11-13T12:50:00Z",
        body="\n".join(
            (
                f"Proof of Done — captured — run {run} — 2026-11-13T12:50:00Z",
                "",
                f"Publish-branch head: {head}",
                "",
            )
        ),
        url="https://github.test/c/1",
    )


def _config(*, dispatcher: dict[str, object]) -> str:
    return json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}})


def _module() -> Any:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE)


def test_a_record_by_the_configured_identity_binds_its_pushed_head_to_its_run() -> None:
    """A durable publication comment can attribute a head before proof exists."""
    records = _module()
    comments = (_comment(body=_record_body()),)

    assert records.publication_pairs(comments=comments, publication_identity=_BOT) == (
        (_HEAD, _RUN),
    )


def test_a_marker_comment_by_another_identity_binds_nothing() -> None:
    """The maintainer's own login, or no author at all, never attributes a head."""
    records = _module()
    comments = (
        _comment(body=_record_body(), login="the-maintainer"),
        _comment(body=_record_body(), login=None),
        {"body": _record_body(), "author": "not-a-mapping"},
        {"body": _record_body(), "author": {"login": ""}},
    )

    assert records.publication_pairs(comments=comments, publication_identity=_BOT) == ()


def test_with_no_configured_identity_no_comment_is_a_publication_record() -> None:
    """An unset key fails closed: the factory's own login is not trusted by default."""
    records = _module()
    comments = (_comment(body=_record_body()),)

    assert records.publication_pairs(comments=comments, publication_identity="") == ()


def test_the_most_recently_posted_record_of_a_head_comes_first() -> None:
    """Readers take the first pair naming a head, so the newest record leads."""
    records = _module()
    comments = (
        _comment(body=_record_body(run=_RUN)),
        _comment(body=_record_body(run=_LATER_RUN)),
    )

    assert records.publication_pairs(comments=comments, publication_identity=_BOT) == (
        (_HEAD, _LATER_RUN),
        (_HEAD, _RUN),
    )


@pytest.mark.parametrize(
    "body",
    [
        None,
        "",
        "some other comment",
        "livespec-publication-record\nrun-id: R\nhead: " + _HEAD,
        _record_body(head="abc"),
        _record_body(head="A" * 40),
        _record_body(head="z" * 40),
        _record_body().replace("run-id: " + _RUN, "run-id:   "),
        "preamble\n" + _record_body(),
    ],
)
def test_a_malformed_record_binds_nothing(body: object) -> None:
    """A record must open with the marker and name every field with a full sha."""
    records = _module()

    assert (
        records.publication_pairs(comments=(_comment(body=body),), publication_identity=_BOT) == ()
    )


def test_resume_ranks_a_configured_publication_comment_without_a_proof_record() -> None:
    """The durable record survives on a host whose journal has no publishing run."""
    assert _module().publications_of(
        records=(), comments=(_comment(body=_record_body()),), publication_identity=_BOT
    ) == ((_HEAD, _RUN),)


def test_a_publication_record_outranks_a_proof_record_of_the_same_head() -> None:
    """The clause: a head with a publication record belongs to the run that record names."""
    pairs = _module().publications_of(
        records=(_proof_record(run=_PROOF_RUN, head=_HEAD),),
        comments=(_comment(body=_record_body()),),
        publication_identity=_BOT,
    )

    assert pairs == ((_HEAD, _RUN), (_HEAD, _PROOF_RUN))
    assert (
        published_head_relation(
            records=(), preserved_run_id=_RUN, published_head=_HEAD, publications=pairs
        )
        is False
    )


def test_a_head_bound_by_a_publication_record_is_ranked_as_one_a_proof_record_names() -> None:
    """Recovery routing reads the same pair whichever record produced it."""
    bound = _module().publications_of(
        records=(), comments=(_comment(body=_record_body()),), publication_identity=_BOT
    )
    proved = _module().publications_of(
        records=(_proof_record(run=_RUN, head=_HEAD),), comments=(), publication_identity=""
    )

    assert bound == proved
    assert (
        published_head_relation(
            records=(), preserved_run_id=_RUN, published_head=_HEAD, publications=bound
        )
        is False
    )


_DISPATCH_ID = "5050cbf4d5e04322b8247d8125016192"
_FABRO_RUN = "01M7DE3JH6D2X5S68HME1E2GM5"
_LATER_FABRO_RUN = "01M7LATERFABRORUN00000000"


@pytest.mark.parametrize("preserved", [_DISPATCH_ID, _FABRO_RUN])
def test_a_binding_naming_both_run_identifiers_ranks_the_head_as_the_preserved_runs_own(
    preserved: str,
) -> None:
    """A preserved ref names its run by the dispatch id or the Fabro run id, never both.

    The binding is posted from inside the run's sandbox, which knows both
    identifiers; the ref may carry either. With an empty journal (a host that did
    not dispatch the run) the head is still the preserved run's own publication.
    """
    pairs = _module().publications_of(
        records=(),
        comments=(_comment(body=_record_body(run=f"{_DISPATCH_ID} {_FABRO_RUN}")),),
        publication_identity=_BOT,
    )

    assert (
        published_head_relation(
            records=(), preserved_run_id=preserved, published_head=_HEAD, publications=pairs
        )
        is False
    )


def test_a_binding_naming_neither_identifier_of_the_preserved_run_stays_unattributed() -> None:
    """Another run's identifiers never read as the preserved run's, and nothing orders them."""
    pairs = _module().publications_of(
        records=(),
        comments=(_comment(body=_record_body(run=f"{_LATER_RUN} {_LATER_FABRO_RUN}")),),
        publication_identity=_BOT,
    )

    assert (
        published_head_relation(
            records=(), preserved_run_id=_FABRO_RUN, published_head=_HEAD, publications=pairs
        )
        is None
    )


def test_a_binding_ranks_a_later_run_through_whichever_identifier_the_journal_names() -> None:
    """The journal names runs by Fabro run id; the binding's dispatch id is not found there."""
    journal: tuple[dict[str, object], ...] = (
        {"run_id": _FABRO_RUN, "work_item_id": _ITEM_ID},
        {"run_id": _LATER_FABRO_RUN, "work_item_id": _ITEM_ID},
    )
    pairs = ((_HEAD, f"{_LATER_RUN} {_LATER_FABRO_RUN}"),)

    assert (
        published_head_relation(
            records=journal, preserved_run_id=_FABRO_RUN, published_head=_HEAD, publications=pairs
        )
        is True
    )


def test_a_head_that_nothing_names_stays_unattributed() -> None:
    """With no record of any kind the ranking is still the unobservable `None`."""
    pairs = _module().publications_of(
        records=(),
        comments=(_comment(body=_record_body(head=_OTHER_HEAD)),),
        publication_identity=_BOT,
    )

    assert (
        published_head_relation(
            records=(), preserved_run_id=_RUN, published_head=_HEAD, publications=pairs
        )
        is None
    )


def test_the_publication_identity_is_read_from_the_committed_dispatcher_block(
    tmp_path: Path,
) -> None:
    """Absent, unparseable or non-string values all read as no identity."""
    records = _module()
    config = tmp_path / ".livespec.jsonc"

    assert records.publication_identity(repo=tmp_path) == ""
    _ = config.write_text(_config(dispatcher={}), encoding="utf-8")
    assert records.publication_identity(repo=tmp_path) == ""
    _ = config.write_text(_config(dispatcher={"publication_identity": _BOT}), encoding="utf-8")
    assert records.publication_identity(repo=tmp_path) == _BOT
    _ = config.write_text(_config(dispatcher={"publication_identity": 7}), encoding="utf-8")
    assert records.publication_identity(repo=tmp_path) == ""
    _ = config.write_text("{ not json", encoding="utf-8")
    assert records.publication_identity(repo=tmp_path) == ""


@dataclass(kw_only=True)
class _StubRunner:
    answers: dict[str, CommandResult]
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
        key = argv[2] if Path(argv[0]).name == "gh" else argv[1]
        return self.answers.get(key, CommandResult(exit_code=1, stdout="", stderr=""))


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="ready",
        title="A resume ranks its own published head",
        description="## Definition of Done\n\n- The resume ranks the head.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-13T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _gather(
    *, repo: Path, comments: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch, identity: str
) -> Any:
    answers = {
        "list": CommandResult(
            exit_code=0,
            stdout=json.dumps([{"number": _PR, "state": "OPEN", "headRefOid": _HEAD}]),
            stderr="",
        ),
        "view": CommandResult(exit_code=0, stdout=json.dumps({"comments": comments}), stderr=""),
    }
    journal = repo / "journal.jsonl"
    _ = journal.write_text("", encoding="utf-8")
    module = importlib.import_module(_GATHER_MODULE)

    def configured_identity(*, repo: Path) -> str:
        _ = repo
        return identity

    monkeypatch.setattr(module, "publication_identity", configured_identity)
    return module.gather_resume(
        args=argparse.Namespace(fabro_bin="fabro", fabro_factory_target=None),
        repo=repo,
        item=_item(),
        journal_path=journal,
        runner=_StubRunner(answers=answers),
    )


def test_a_resume_gather_binds_the_published_head_from_the_forge_comment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No proof record and no journal row name the head, yet the gather attributes it."""
    gather = _gather(
        repo=tmp_path,
        comments=[_comment(body=_record_body())],
        monkeypatch=monkeypatch,
        identity=_BOT,
    )

    assert gather.publications == ((_HEAD, _RUN),)


def test_a_resume_gather_without_a_committed_identity_binds_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The factory's marker comment is ignored when the repository commits no identity."""
    gather = _gather(
        repo=tmp_path,
        comments=[_comment(body=_record_body())],
        monkeypatch=monkeypatch,
        identity="",
    )

    assert gather.publications == ()
