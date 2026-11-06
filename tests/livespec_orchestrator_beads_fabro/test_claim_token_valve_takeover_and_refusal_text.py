"""What a valve press does about an unapplied transition, and what a refused press says.

Two properties of the human valves under the claim-token cutover
(`SPECIFICATION/contracts.md`, "Claim tokens"), each driven through the valve
itself against the in-memory tenant.

ONE PRESS CAN TAKE A STRANDED TRANSITION OVER. Step 5 of the protocol lets a
writer take over the successor of a token whose winner never wrote the item,
once that writer has itself watched the unapplied transition for 180 seconds.
A valve press is one process, so it has to do the watching inside the press:
it says so on stderr, waits, and writes again. A press that only reported
`claim-transition-pending` would leave the item unwritable by any valve, for
ever, because the next press starts with no observation of its own. No case
here sleeps: the wait the valve builds is replaced by one on a clock the case
owns, whose sleep ages this process's recorded observations by the time slept.

A REFUSED PRESS SAYS WHAT IT DID. Four valves do something before the guarded
write their order ends in: `reject:regroom` reverts the merged change,
`resolve-blocked` writes the operator's answer, `accept` rewrites the proof
pointer, and `approve` records its Definition-of-Done judgement. When the
guarded write then loses its token, that earlier effect stands. Each case
checks the effect really is still there, and that the refusal names it and
does not say "nothing was written".
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import _intake_valve_claim_writes as writes
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._drive_accept_valve import accept_item
from livespec_orchestrator_beads_fabro.commands._intake_valve_claim_writes import TakeoverWait
from livespec_orchestrator_beads_fabro.commands.drive import CommandRun, run_action
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import AuditRecord, StoreConfig, WorkItem

_ITEM_ID = "bd-ib-valvetext"
_HEADING = "## Effective acceptance criteria"
_ANOTHER_WRITER = "another writer won this token"
_JUDGEMENT_MARKER = "dod-judgement:recorded"
_NOT_WRITTEN = f"the status and claim of {_ITEM_ID} were not written."
_NOTHING_WRITTEN = f"nothing was written to {_ITEM_ID}."
_HUMAN_ASSERTION = "The production console renders the capacity banner."
_ATTESTED_BODY = "Proof of Done — human_attested — run alice — 2026-10-01T10:00:00Z\n\nDone.\n"
_CONNECTION = {
    "tenant": "livespec-impl-beads",
    "prefix": "bd-ib",
    "server_user": "livespec-impl-beads",
    "database": "livespec-impl-beads",
    "bd_path": "bd",
    "fake": True,
}


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    TRANSITION_OBSERVATIONS.clear()
    yield
    TRANSITION_OBSERVATIONS.clear()
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    """A repository with a readable spec tree, cut over to claim tokens."""
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    block = {"connection": _CONNECTION, "dispatcher": {"claim_tokens": True}}
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": block}), encoding="utf-8"
    )
    return repo


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="backlog",
        title="A slice a valve is pressed on",
        description=(
            "Do the thing.\n\n## Definition of Done\n\n"
            f"- The dispatched slice lands its change.\n\nReferences: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


def _seed(*, item: WorkItem) -> tuple[FakeBeadsClient, str]:
    """File the item through a descriptor naming no repository, naming a fresh open token."""
    append_work_item(path=_config(), item=item)
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    token = create_claim_token(client=client)
    metadata = dict(client.show_issue(issue_id=_ITEM_ID)["metadata"])
    metadata[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=_ITEM_ID, metadata=metadata, names_claim_token=True)
    return client, token


def _stored() -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]


def _lose_the_token(
    *, client: FakeBeadsClient, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Have an unnamed writer close `token` at the instant the valve closes it."""
    close = client.close_issue_without_verdict

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == token:
            close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


def _press(*, repo: Path, action_id: str, **inputs: object) -> dict[str, object]:
    """One operator press of a valve, through the surface an operator uses."""
    return run_action(
        repo=repo,
        action_id=action_id,
        identity=InvokerIdentity(invoker="human:cw", invoker_source="flag"),
        **inputs,
    )


def _refused(*, result: dict[str, object]) -> str:
    """The summary of a press the claim-token protocol refused as `claim-changed`."""
    assert (result["status"], result["domain_error"]) == ("failed", "claim-changed")
    return str(result["summary"])


@dataclass(kw_only=True)
class _Time:
    """A clock a case owns, on which only its own `sleep` makes time pass."""

    now: float = 0.0
    slept: list[float] = field(default_factory=list)

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds
        for observation in TRANSITION_OBSERVATIONS:
            TRANSITION_OBSERVATIONS[observation] -= seconds


def _move_to_ready(*, repo: Path) -> dict[str, object]:
    return _press(repo=repo, action_id=f"move:{_ITEM_ID}:ready")


def _strand_a_transition(
    *, client: FakeBeadsClient, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `move` press wins the item's current token, and its item write then fails."""
    real = client.update_issue

    def _failing_on_the_item(**fields: object) -> None:
        if fields["issue_id"] == _ITEM_ID:
            raise BeadsCommandError(command="bd update", exit_code=1, stderr="server gone")
        real(**fields)

    with monkeypatch.context() as patched:
        patched.setattr(client, "update_issue", _failing_on_the_item)
        with pytest.raises(BeadsCommandError):
            _ = _move_to_ready(repo=repo)


def test_one_press_takes_over_a_transition_a_failed_writer_left_unapplied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The item names a closed token. One press waits out the takeover wait and writes."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed(item=_item())
    _strand_a_transition(client=client, repo=repo, monkeypatch=monkeypatch)
    stranded = json.loads(client.show_issue(issue_id=token)["close_reason"])["successor"]
    assert client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY] == token
    clock = _Time()
    monkeypatch.setattr(
        writes, "TakeoverWait", lambda: TakeoverWait(clock=clock.clock, sleep=clock.sleep)
    )

    result = _move_to_ready(repo=repo)

    record = client.show_issue(issue_id=_ITEM_ID)
    took_over = json.loads(client.show_issue(issue_id=stranded)["close_reason"])
    assert result["status"] == "green"
    assert clock.slept == [180.0]
    assert record["status"] == "ready"
    assert (took_over["writer"], took_over["intent"]) == ("human-valve", "move:ready")
    assert took_over["successor"] == record["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert "Waiting 180 seconds, the protocol's takeover wait" in capsys.readouterr().err


@dataclass(kw_only=True)
class _Git:
    """The command runner a `reject` press is handed: every command succeeds."""

    calls: list[tuple[str, ...]] = field(default_factory=list)

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        _ = cwd
        self.calls.append(argv)
        return CommandRun(argv=argv, returncode=0, stdout="", stderr="")


def _merged(*, merge_sha: str) -> AuditRecord:
    return AuditRecord(
        verification_timestamp="2026-11-06T01:00:00Z",
        commits=(),
        files_changed=(),
        merge_sha=merge_sha,
        pr_number=7,
    )


@pytest.mark.parametrize(
    ("kind", "reverted", "said"),
    [
        (
            "regroom",
            [("git", "revert", "--no-edit", "feed01")],
            "the merged change was already reverted in the repository checkout (git revert) "
            "and that revert stands, so a second press would run the revert again; " + _NOT_WRITTEN,
        ),
        ("rework", [], _NOTHING_WRITTEN),
    ],
)
def test_a_refused_reject_says_whether_it_had_already_reverted_the_merge(
    kind: str,
    reverted: list[tuple[str, ...]],
    said: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed(item=_item(status="acceptance", audit=_merged(merge_sha="feed01")))
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)
    git = _Git()

    result = _press(repo=repo, action_id=f"reject:{_ITEM_ID}:{kind}", runner=git)

    summary = _refused(result=result)
    assert git.calls == reverted
    assert summary == f"reject refused: the claim-token protocol reported claim-changed; {said}"
    assert _stored().status == "acceptance"


@pytest.mark.parametrize(
    ("answer", "delivered", "said"),
    [
        (
            "Take option B.",
            1,
            "the answer was already written to the item as a ledger comment and journaled, "
            "and it stays there; " + _NOT_WRITTEN,
        ),
        (None, 0, _NOTHING_WRITTEN),
    ],
)
def test_a_refused_resolve_blocked_says_whether_the_answer_had_already_landed(
    answer: str | None,
    delivered: int,
    said: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed(item=_item(status="blocked", blocked_reason="needs-human"))
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    result = _press(repo=repo, action_id=f"resolve-blocked:{_ITEM_ID}:ready", answer=answer)

    summary = _refused(result=result)
    answers = [
        comment.text
        for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
        if "Take option B." in comment.text
    ]
    assert len(answers) == delivered
    assert summary == (
        f"resolve-blocked refused: the claim-token protocol reported claim-changed; {said}"
    )
    assert _stored().status == "blocked"


@dataclass(kw_only=True)
class _Forge:
    """The command runner an `accept` press reads the pull request's records through."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = argv, cwd, timeout_seconds, env, stdin
        comments = [{"url": "https://example.test/c/2", "body": _ATTESTED_BODY}]
        return CommandResult(exit_code=0, stdout=json.dumps({"comments": comments}), stderr="")


_PLAIN = "## Definition of Done\n\n- It works.\n\nReferences: ## Something\n"
_HUMAN_ATTESTED = textwrap.dedent(f"""\
    ## Definition of Done

    - The projection carries the parent field.

    ### Human-attested

    Reason: the sandbox has no session on the production console.

    - {_HUMAN_ASSERTION}

    References: ## Something

    ## Proof of Done

    - Pull request: #11
    - Verified record: https://example.test/c/1
    - Run: 01M3RUN
    - Timestamp: 2026-10-01T09:00:00Z
    - Verdict: verified
    """)


@pytest.mark.parametrize(
    ("description", "rewritten", "said"),
    [
        (
            _HUMAN_ATTESTED,
            True,
            "the proof pointer in the item's description was already rewritten to cite the "
            "human-attested record, and that rewrite stands; " + _NOT_WRITTEN,
        ),
        (_PLAIN, False, _NOTHING_WRITTEN),
    ],
)
def test_a_refused_accept_says_whether_it_had_already_rewritten_the_proof_pointer(
    *,
    description: str,
    rewritten: bool,
    said: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item(status="acceptance", description=description, acceptance_criteria=None)
    client, token = _seed(item=item)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    result = accept_item(
        repo=repo, config=_config(), item=item, action_id=f"accept:{_ITEM_ID}", runner=_Forge()
    )

    summary = _refused(result=result)
    stored = _stored()
    assert ("- Human-attested record: https://example.test/c/2" in stored.description) is rewritten
    assert summary == f"accept refused: the claim-token protocol reported claim-changed; {said}"
    assert stored.status == "acceptance"


def test_a_refused_approve_says_its_definition_of_done_judgement_stays_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed(item=_item(status="pending-approval"))
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    result = _press(repo=repo, action_id=f"approve:{_ITEM_ID}")

    summary = _refused(result=result)
    record = client.show_issue(issue_id=_ITEM_ID)
    assert _JUDGEMENT_MARKER in record["labels"]
    assert summary == (
        "approve refused: the claim-token protocol reported claim-changed; "
        "any Definition-of-Done judgement this press ran is already recorded on the item "
        "and stays there; " + _NOT_WRITTEN
    )
    assert record["status"] == "pending-approval"
