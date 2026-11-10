"""Recovery routing seeds a released item from its current seed ruling.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" → "A ruled seed names the tree a
released item's next dispatch starts from": "Routing MUST take its seed from a
current seed ruling ahead of a `resume` and ahead of the preference order this
clause states. When the ruled ref exists at the ruled SHA and no non-fallback
refusal applies, the route MUST be `seeded`, and the seed record MUST name the
ruled ref as its preservation reference and the ruled SHA as its immutable
commit." And: "Recovery routing MUST read current rulings from the item's ledger
comments and never from a host's journal alone."

EVERY CASE STANDS A COMPETING OLDER TREE ON ORIGIN BESIDE THE RULED REF. A world
holding only the ruled ref is satisfied by a build that ignores rulings and seeds
from whatever preserved tree it finds, because that tree IS the ruled one. The
needs-human ref here is a different commit at a rank the preference order would
take, so only a build that actually reads the ruling lands on the ruled commit.

THE RULING IS WRITTEN ONLY TO THE LEDGER. The journal carries no `seed-ruling`
record in any case below, which is the instrument for "a ruling written from
another checkout": the routing pass has to find the ruling on the item's comments
or not find it at all.

The origin, forge and factory board are scripted, and an argv no case scripted
FAILS, so a route decided on a blank reply cannot pass for one decided on
evidence.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import IssueDraft, make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_launch import (
    LaunchPins,
    recovery_launch_args,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_SEEDED,
    RecoveryRoute,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routing import (
    route_recovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    resume_checkout_for,
    resume_checkout_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import (
    seed_ruling_comment_body,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM = "bd-ib-ruled"
_RUN = "01RULEDRUN00000000000000A"
_DISPATCH = "d" * 32
_BRANCH = f"feat/{_ITEM}"

_NH_REF = f"refs/heads/needs-human/{_RUN}"
_NH_COMMIT = "a1" * 20
_RULED_REF = f"refs/heads/rescue/{_ITEM}"
_RULED_SHA = "b2" * 20


class _Origin:
    """A scripted origin, forge and factory board; an unscripted argv FAILS."""

    def __init__(self, *, refs: dict[str, str]) -> None:
        self.refs = refs
        self.calls: list[str] = []

    def answer(self, *, argv: list[str]) -> CommandResult:
        joined = " ".join(argv)
        self.calls.append(joined)
        if argv[:3] == ["git", "ls-remote", "origin"]:
            lines = [
                f"{commit}\t{ref}"
                for ref, commit in sorted(self.refs.items())
                if any(fnmatch.fnmatchcase(ref, pattern) for pattern in argv[3:])
            ]
            return CommandResult(exit_code=0, stdout="\n".join(lines), stderr="")
        if joined.startswith(f"gh pr list --head {_BRANCH}"):
            return CommandResult(exit_code=0, stdout="[]", stderr="")
        if "ps -a --json" in joined:
            return CommandResult(exit_code=0, stdout="[]", stderr="")
        message = f"unscripted command reached the shell seam: {joined}"
        raise AssertionError(message)


def _work_item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="bug",
        status="ready",
        title="A released item an operator ruled a seed for",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _journal(*, tmp_path: Path) -> JournalFile:
    """A journal whose newest dispatch of the item ended in a first-stall release.

    It carries NO `seed-ruling` record: the ruling lives on the ledger alone.
    """
    records = (
        {"stage": "dispatch-id", "work_item_id": _ITEM, "dispatch_id": _DISPATCH},
        {"stage": "fabro-run", "work_item_id": _ITEM, "run_id": _RUN},
        {
            "stage": "watchdog-stall-cancel",
            "work_item_id": _ITEM,
            "dispatch_id": _DISPATCH,
            "run_id": _RUN,
            "factory": "hp",
            "executing_stage": "proof_capture",
        },
        {"stage": "stall-cancel-release", "work_item_id": _ITEM, "status": "ready"},
    )
    journal = JournalFile(path=tmp_path / "fabro-dispatch-journal.jsonl")
    _ = journal.path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8"
    )
    return journal


def _ruling_comment(*, ref: str, sha: str, instant: str) -> str:
    return seed_ruling_comment_body(
        work_item_id=_ITEM,
        preservation_ref=ref,
        commit_sha=sha,
        invoker="coordinator",
        reason="the ruled tree carries the checked work",
        instant=instant,
    )


def _seed_ledger(*, tmp_path: Path, comments: tuple[str, ...]) -> None:
    """Put the item in the tenant with these comments, oldest first."""
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    client = make_beads_client(config=store_config(repo=tmp_path))
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM,
            issue_type="task",
            title="A released item an operator ruled a seed for",
            description="",
            assignee=None,
            created_at="2026-11-10T00:00:00Z",
        )
    )
    for body in comments:
        client.add_comment(issue_id=_ITEM, body=body)


def _args(*, tmp_path: Path, journal: JournalFile) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(tmp_path),
        journal=str(journal.path),
        item=None,
        items=None,
        skip_ledger_check=True,
        workflow_name=None,
        fabro_bin="/usr/local/bin/fabro",
    )


def _route(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refs: dict[str, str]
) -> tuple[RecoveryRoute, JournalFile]:
    origin = _Origin(refs=refs)

    def _run(
        _self: ShellCommandRunner,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        return origin.answer(argv=argv)

    monkeypatch.setattr(ShellCommandRunner, "run", _run)
    journal = _journal(tmp_path=tmp_path)
    routing = route_recovery(
        args=_args(tmp_path=tmp_path, journal=journal),
        repo=tmp_path,
        candidates=[_work_item()],
        journal=journal,
    )
    route = routing.route_for(work_item_id=_ITEM)
    assert route is not None
    return route, journal


def test_the_scripted_origin_refuses_a_command_no_case_scripted() -> None:
    """The instrument's own control: every claim below rests on this refusal firing."""
    with pytest.raises(AssertionError, match="unscripted command"):
        _ = _Origin(refs={}).answer(argv=["git", "fetch", "origin"])


def test_a_ruled_ref_at_the_ruled_commit_seeds_the_dispatch_over_an_older_preserved_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_ledger(
        tmp_path=tmp_path,
        comments=(_ruling_comment(ref=_RULED_REF, sha=_RULED_SHA, instant="2026-11-10T01:00:00Z"),),
    )

    route, _ = _route(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        refs={_NH_REF: _NH_COMMIT, _RULED_REF: _RULED_SHA},
    )

    assert route.route == ROUTE_SEEDED
    assert route.seed is not None
    assert route.seed.preservation_ref == _RULED_REF
    assert route.seed.commit_sha == _RULED_SHA
    assert route.seed.remote == "origin"


def test_the_sandbox_of_a_ruled_seed_checks_out_the_ruled_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_ledger(
        tmp_path=tmp_path,
        comments=(_ruling_comment(ref=_RULED_REF, sha=_RULED_SHA, instant="2026-11-10T01:00:00Z"),),
    )
    route, journal = _route(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        refs={_NH_REF: _NH_COMMIT, _RULED_REF: _RULED_SHA},
    )

    launched = recovery_launch_args(
        args=_args(tmp_path=tmp_path, journal=journal),
        repo=tmp_path,
        work_item_id=_ITEM,
        route=route,
        pins=LaunchPins(
            factory=lambda **kwargs: kwargs["args"], workflow=lambda **kwargs: kwargs["args"]
        ),
    )

    block = resume_checkout_prepare_steps_block(
        checkout=resume_checkout_for(args=launched, branch=_BRANCH)
    )
    assert f"git fetch --no-tags origin {_RULED_REF}" in block
    assert f"git checkout --detach {_RULED_SHA}" in block
    assert _NH_COMMIT not in block


def test_a_ruling_is_found_on_the_ledger_when_the_journal_holds_no_seed_ruling_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ruling written from another checkout governs a dispatch from this one."""
    _seed_ledger(
        tmp_path=tmp_path,
        comments=(_ruling_comment(ref=_RULED_REF, sha=_RULED_SHA, instant="2026-11-10T01:00:00Z"),),
    )

    route, journal = _route(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        refs={_NH_REF: _NH_COMMIT, _RULED_REF: _RULED_SHA},
    )

    stages = [
        json.loads(line).get("stage")
        for line in journal.path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert "seed-ruling" not in stages
    assert route.seed is not None
    assert route.seed.preservation_ref == _RULED_REF
