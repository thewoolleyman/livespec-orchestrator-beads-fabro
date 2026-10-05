"""`dispatcher.py post-plan-record` driven as an operator drives it.

Covers `_plan_record_cli` and the refusal ladder of `_plan_record_post`. The
happy path runs through the REAL `dispatcher.main(argv=[...])` supervisor — argv
parse, config resolution, tenant read, render and ledger append — over the
in-memory tenant, so the subcommand's wiring is observed rather than assumed; a
primitive exercised in isolation would pass just as well while `post-plan-record`
was absent from the parser.

WHY THE VERDICT CHOICE IS ASSERTED WITH A REAL PROOF-OF-DONE WORD. `argparse`
refusing `banana` proves nothing an empty choice list would not. The control is
`host_verified`: a genuine Proof-of-Done verdict, just not a PLAN one, which a
primitive accepting any string would publish as a permanent record the archive
gate cannot read — indistinguishable, from the publisher's side, from success.

WHY EVERY REFUSAL IS READ OFF THE COMMENT COUNT. A record comment must not be
edited after posting, so the ladder's guarantee is that nothing is appended. An
exit code cannot establish that; the ledger can.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_HOST_VERIFIED,
    VERDICT_NOT_REPRODUCED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import plan_proof_entries
from livespec_orchestrator_beads_fabro.commands._plan_record_post import (
    PlanRecordPost,
    run_post_plan_record_command,
)
from livespec_orchestrator_beads_fabro.commands.plan import create_thread
from livespec_orchestrator_beads_fabro.types import StoreConfig

_SLUG = "cli-record-thread"
_ASSERTION = "The released build runs in a real operator session."
_SESSION_ENV = "CLAUDE_CODE_SESSION_ID"
_CAPTURING = "capturing-session"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


class _Runner:
    """A runner whose only possible call is the forge-login identity read."""

    def __init__(self, *, login: str, exit_code: int = 0) -> None:
        self.login = login
        self.exit_code = exit_code
        self.calls: list[list[str]] = []

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        _ = (cwd, timeout_seconds)
        self.calls.append(argv)
        return CommandResult(exit_code=self.exit_code, stdout=self.login, stderr="")


@pytest.fixture(autouse=True)
def _fake_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()


def _govern(*, repo: Path) -> None:
    """The minimum committed configuration the production config path resolves."""
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )


def _plan(*, repo: Path, assertions: tuple[str, ...] = (_ASSERTION,)) -> str:
    created = create_thread(
        project_root=repo,
        config=_config(),
        slug=_SLUG,
        title="CLI record thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-10-05T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the released build has been run in a real session.",
            assertions=assertions,
        ),
    )
    return created["epic_id"]


def _payload(*, repo: Path, text: str = _ASSERTION, name: str = "record.json") -> Path:
    target = repo / name
    _ = target.write_text(
        json.dumps(
            {
                "build": {"release_tag": "v0.167.0"},
                "assertions": [{"text": text, "steps": ["Run it."], "proof": "ok\n"}],
            }
        ),
        encoding="utf-8",
    )
    return target


def _post(
    *,
    repo: Path,
    epic_id: str,
    verdict: str,
    record: Path,
    env: dict[str, str],
    runner: _Runner | None = None,
) -> tuple[int, str]:
    emitted: list[str] = []
    exit_code = run_post_plan_record_command(
        post=PlanRecordPost(repo=repo, epic_id=epic_id, verdict=verdict, record_path=record),
        config=_config(),
        runner=runner or _Runner(login=""),
        env=env,
        emit=emitted.append,
    )
    return exit_code, "".join(emitted)


def test_the_dispatcher_subcommand_publishes_the_record_on_the_epic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _govern(repo=tmp_path)
    epic_id = _plan(repo=tmp_path)
    monkeypatch.setenv(_SESSION_ENV, _CAPTURING)
    record = _payload(repo=tmp_path)

    exit_code = dispatcher.main(
        argv=[
            "post-plan-record",
            "--repo",
            str(tmp_path),
            "--epic",
            epic_id,
            "--verdict",
            VERDICT_CAPTURED,
            "--record",
            str(record),
        ]
    )

    assert exit_code == 0
    # The body the primitive rendered is echoed, so what was posted and what was
    # reported are one artifact.
    assert "Plan Proof of Done — captured" in capsys.readouterr().out
    entries = plan_proof_entries(comments=_fake().list_comments(issue_id=epic_id))
    assert [(one.record.verdict, one.record.run_id) for one in entries] == [
        (VERDICT_CAPTURED, _CAPTURING)
    ]


def test_a_real_but_non_plan_verdict_word_is_refused_by_the_parser(tmp_path: Path) -> None:
    _govern(repo=tmp_path)

    with pytest.raises(SystemExit) as exited:
        _ = dispatcher.main(
            argv=[
                "post-plan-record",
                "--repo",
                str(tmp_path),
                "--epic",
                "bd-ib-epic",
                "--verdict",
                VERDICT_HOST_VERIFIED,
                "--record",
                str(tmp_path / "record.json"),
            ]
        )

    assert exited.value.code == 2


def test_an_epic_the_tenant_does_not_hold_is_refused(tmp_path: Path) -> None:
    exit_code, emitted = _post(
        repo=tmp_path,
        epic_id="bd-ib-absent",
        verdict=VERDICT_CAPTURED,
        record=_payload(repo=tmp_path),
        env={_SESSION_ENV: _CAPTURING},
    )

    assert exit_code != 0
    assert "no work-item bd-ib-absent" in emitted


def test_an_epic_with_no_gradeable_section_is_refused(tmp_path: Path) -> None:
    epic_id = _plan(repo=tmp_path)
    _fake().update_issue(issue_id=epic_id, description="Plan anchor only.")

    exit_code, emitted = _post(
        repo=tmp_path,
        epic_id=epic_id,
        verdict=VERDICT_CAPTURED,
        record=_payload(repo=tmp_path),
        env={_SESSION_ENV: _CAPTURING},
    )

    assert exit_code != 0
    assert "no gradeable Definition of Done section" in emitted
    assert _fake().list_comments(issue_id=epic_id) == []


def test_a_payload_naming_an_assertion_the_plan_does_not_declare_is_refused(
    tmp_path: Path,
) -> None:
    epic_id = _plan(repo=tmp_path)

    exit_code, emitted = _post(
        repo=tmp_path,
        epic_id=epic_id,
        verdict=VERDICT_CAPTURED,
        record=_payload(repo=tmp_path, text="An assertion nobody declared."),
        env={_SESSION_ENV: _CAPTURING},
    )

    assert exit_code != 0
    assert "An assertion nobody declared." in emitted
    assert _fake().list_comments(issue_id=epic_id) == []


def test_an_invocation_with_no_resolvable_identity_is_refused(tmp_path: Path) -> None:
    epic_id = _plan(repo=tmp_path)
    # No session variable and a forge read that fails: the computation is partial
    # by design, because a record that cannot name its publisher compares EQUAL to
    # every other such record and would defeat the independence refusal in both
    # directions at once.
    exit_code, emitted = _post(
        repo=tmp_path,
        epic_id=epic_id,
        verdict=VERDICT_CAPTURED,
        record=_payload(repo=tmp_path),
        env={},
        runner=_Runner(login="", exit_code=1),
    )

    assert exit_code != 0
    assert "no publishing identity could be computed" in emitted
    assert _fake().list_comments(issue_id=epic_id) == []


def test_a_replay_with_no_capture_to_replay_is_refused(tmp_path: Path) -> None:
    epic_id = _plan(repo=tmp_path)

    exit_code, emitted = _post(
        repo=tmp_path,
        epic_id=epic_id,
        verdict=VERDICT_NOT_REPRODUCED,
        record=_payload(repo=tmp_path),
        env={_SESSION_ENV: "replaying-session"},
    )

    assert exit_code != 0
    assert "carries no captured plan Proof of Done record" in emitted
    assert _fake().list_comments(issue_id=epic_id) == []


def test_a_human_attested_record_is_published_without_owning_a_capture(tmp_path: Path) -> None:
    """An attestation is its own independent leg, not a replay of anything.

    It therefore owes no prior capture and has no capturing identity to collide
    with — and it DOES carry a reproduction verdict, because the archive gate
    reads that line to decide whether the human-attested assertion is covered.
    """
    human = "The maintainer agrees the console reads well."
    epic_id = _plan(repo=tmp_path, assertions=(human,))
    # The section's single bullet is host_captured by the plan default, so the
    # attestation is published under a `Human-attested` sub-heading instead.
    _fake().update_issue(
        issue_id=epic_id,
        description=f"## Definition of Done\n\n### Human-attested\n\nReason: taste.\n\n- {human}",
    )

    exit_code, _ = _post(
        repo=tmp_path,
        epic_id=epic_id,
        verdict="human_attested",
        record=_payload(repo=tmp_path, text=human),
        env={_SESSION_ENV: "maintainer"},
    )

    assert exit_code == 0
    [entry] = plan_proof_entries(comments=_fake().list_comments(issue_id=epic_id))
    assert entry.record.verdict == "human_attested"
    assert "Proof mode: human_attested" in entry.record.body


def test_a_human_at_a_terminal_publishes_under_the_forge_login(tmp_path: Path) -> None:
    epic_id = _plan(repo=tmp_path)
    runner = _Runner(login="thewoolleyman\n")

    exit_code, _ = _post(
        repo=tmp_path,
        epic_id=epic_id,
        verdict=VERDICT_CAPTURED,
        record=_payload(repo=tmp_path),
        env={},
        runner=runner,
    )

    assert exit_code == 0
    [entry] = plan_proof_entries(comments=_fake().list_comments(issue_id=epic_id))
    assert entry.record.run_id == "thewoolleyman"
    # The forge read is the one command this surface may run, and only when no
    # agent session answers first.
    assert runner.calls == [["gh", "api", "user", "--jq", ".login"]]


def test_a_replay_by_a_different_identity_lands_after_the_capture(tmp_path: Path) -> None:
    epic_id = _plan(repo=tmp_path)
    captured, _ = _post(
        repo=tmp_path,
        epic_id=epic_id,
        verdict=VERDICT_CAPTURED,
        record=_payload(repo=tmp_path),
        env={_SESSION_ENV: _CAPTURING},
    )
    assert captured == 0

    exit_code, _ = _post(
        repo=tmp_path,
        epic_id=epic_id,
        verdict=VERDICT_VERIFIED,
        record=_payload(repo=tmp_path, name="replay.json"),
        env={_SESSION_ENV: "replaying-session"},
    )

    assert exit_code == 0
    entries = plan_proof_entries(comments=_fake().list_comments(issue_id=epic_id))
    assert [one.record.verdict for one in entries] == [VERDICT_CAPTURED, VERDICT_VERIFIED]
