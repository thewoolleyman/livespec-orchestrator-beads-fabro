"""Integration-tier acceptance for `SPECIFICATION/scenarios.md` Scenario 146.

Binds "Scenario 146 — Authoritative result readers distinguish fulfillment from
observation failure" and the shared-authoritative-result-reader clause it governs
in `SPECIFICATION/contracts.md`. The scenario outline runs the shared reader over
all five typed kinds with a fulfilled and an unmet example each, and its second
sub-scenario requires an observation failure to be `unobservable` with the failed
source named.

EVERY CASE DRIVES THE SHARED READER ITSELF — `read_result` — against the in-memory
`FakeBeadsClient` (`LIVESPEC_BEADS_FAKE=1`), which is this repository's hermetic
ledger surface, and against a recording `CommandRunner` standing in for the one
`gh` seam the forge, proof and branch adapters shell through. The reference parse,
the repository resolution, every adapter and every observation are production
code; no adapter is mocked out from under the reader.

THE NEGATIVE CONTROLS ARE ASSERTED AS "NOT SATISFIED" RATHER THAN BY AN EXACT
STATUS, where that is all the slice under test has delivered. The reader's
`unsatisfied` and `unobservable` statuses arrive in their own Red-Green cycles, so
a case written against the exact status would have to be rewritten by a later
cycle — and a rewritten test cannot be re-run against the commit that first made
it pass. `_status` is the one accessor every case reads through, so the controls
stay true across all three cycles while the cycle-specific cases assert the exact
status their own assertion names.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, urlopen

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    RELEASE_TAG_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer import (
    ProofPointer,
    description_with_pointer,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    PUBLISH_HEAD_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    SOURCE_PROOF_RECORD,
    ResultObservation,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_reader import read_result

_PROJECT_NAME = "repo"
_ITEM_ID = "bd-ib-result1"
_SUBJECT_ID = "bd-ib-result2"
_MARKER = "relay-delivery-and-progress-deadline: delivered"
_PR_NUMBER = 146
_BRANCH = "master"
_FILE_PATH = "SPECIFICATION/contracts.md"
_BLOB = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
# Three targets a RAW URL interpolation corrupts, each in its own way. A `#` is a
# legal Git branch character — `git check-ref-format --branch proof#variant`
# succeeds — and a legal path character, but in a URL it opens a FRAGMENT, which
# RFC 3986 says is never transmitted. A space is legal in a path and illegal in a
# URL outright.
_VARIANT_BRANCH = "proof#variant"
_FRAGMENT_PATH = "docs/a#b.md"
_SPACED_PATH = "docs/a b.md"
# The loopback forge answers `_BLOB_EXACT` for the ONE requested (path, ref) pair
# and `_BLOB_SHADOW` for every other, so a reference naming the shadow blob is
# satisfied only by a request that reached the WRONG target.
_BLOB_EXACT = "b" * 40
_BLOB_SHADOW = "a" * 40
_BUILD = "v0.170.0"
_ASSERTION = "The result reader reports an observable unmet target as unsatisfied."
_RECORD_URL = f"https://example.test/owner/repo/pull/{_PR_NUMBER}#issuecomment-146"
_PR_UPDATED_AT = "2026-10-08T09:00:00Z"
_NOW = "2026-10-08T12:00:00Z"
# Each stub answer is selected by a substring of one argv token, so the two
# `gh pr view` reads are told apart by the `--json` field list they ask for
# rather than by call order — a reader that asked for comments where it meant
# state would otherwise be handed the answer it expected.
_PR_STATE_KEY = "state,updatedAt"
_PR_COMMENTS_KEY = "comments"
_BLOB_KEY = "contents/"
# The verified-proof read's build comparison. It shares the `gh api` verb with the
# blob read, so it is keyed on its own endpoint segment rather than on the verb.
_COMPARE_KEY = "/compare/"
# A capture's publishing identity and an INDEPENDENT replayer's. The host-leg rule
# admits a replay only from a party other than the one that recorded the capture,
# so the refusal cases reuse one identity and the control uses two.
_CAPTURE_IDENTITY = "session 1e14094a-0000-4000-8000-000000000001"
_REPLAY_IDENTITY = "session b1e14094-0000-4000-8000-000000000002"
# The publish-branch head an ORDINARY FACTORY record declares, and a second one for
# the other-build control. A factory record carries no host `Build identity` section
# at all: that section names a RELEASE, and the capture and verify stages run on the
# DRAFT pull request, before the merge any release could contain.
_FACTORY_HEAD = "f" * 40
_OTHER_FACTORY_HEAD = "e" * 40
# The dispatch the subject's own proof pointer names, which is the factory leg's
# whole attribution anchor. Spelled once so the pointer and the records cannot drift.
_RUN_ID = "01M4RESULTREADER"
# The merge the subject records once its work closed. It is what the HOST leg
# additionally requires a released build to contain — and what a PRE-MERGE factory
# candidate cannot contain, since that candidate is the head the merge was made from.
_MERGE_SHA = "c" * 40
# The ancestry these fixtures model, DECLARED pair by pair rather than answered
# blanket. `_FACTORY_HEAD` is a commit on the draft branch of the work released as
# `_BUILD`, so it carries `_BUILD`; and `_BUILD` is the release cut after the
# subject's merge, so it carries `_MERGE_SHA`. Every other pair that is not
# literally the same ref answers `behind`, because inventing containment between two
# unrelated identities is what made this module's build control vacuous once already.
_CONTAINING_PAIRS = frozenset({(_BUILD, _FACTORY_HEAD), (_MERGE_SHA, _BUILD)})
# Spelled as a LITERAL rather than imported from the observation module, and that
# is deliberate. Each status arrives in its own Red-Green cycle, so a Red that
# imported the not-yet-existing constant would die at COLLECTION — proving only
# that a name is missing, never that the behaviour is unimplemented. The literal
# is bound back to the production constant by an assertion in
# `tests/livespec_orchestrator_beads_fabro/commands/test_plan_result_observation.py`,
# so a renamed constant still fails somewhere rather than drifting silently.
_UNSATISFIED = "unsatisfied"
_UNOBSERVABLE = "unobservable"


@pytest.fixture(autouse=True)
def _hermetic_ledger(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The hermetic in-memory tenant, emptied around every case.

    There is no shared conftest at this tier, so each file owns its backend
    isolation. The singleton is reset BOTH before and after, because the
    accumulation-within-one-invocation behaviour the runtime relies on must not
    leak between cases that seed the same item ids.
    """
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _Runner:
    """A `CommandRunner` that answers by argv substring and records every call.

    THE BUILD COMPARISON IS DERIVED FROM THE ARGV RATHER THAN CANNED. A fixture
    answering one status for every comparison makes the build leg VACUOUS: the "a
    record naming another build cannot satisfy the requested build" control passed
    its record through a comparison that said `identical` about two builds that are
    nothing of the kind, so the control would have reported a clean pass against a
    reader that ignored the build entirely — the exact reading it exists to exclude.
    Deriving the answer from the two refs the adapter actually asked about makes the
    fixture incapable of that lie, and leaves no canned value for a later case to
    reach for by accident.
    """

    answers: dict[str, CommandResult]
    calls: list[tuple[tuple[str, ...], Path]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del timeout_seconds, env, stdin
        self.calls.append((tuple(argv), cwd))
        derived = _derived_containment(argv=argv)
        if derived is not None:
            return derived
        for key, result in self.answers.items():
            if any(key in token for token in argv):
                return result
        return CommandResult(exit_code=1, stdout="", stderr=f"no stub answers {argv}")


def _status(*, observation: ResultObservation | None) -> str | None:
    """The observed status, or `None` when the reader reported no observation."""
    return None if observation is None else observation.status


def _project(*, tmp_path: Path) -> Path:
    """A project root whose directory name is the canonical repository identity."""
    repo = tmp_path / _PROJECT_NAME
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _seed_item(
    *,
    repo: Path,
    issue_id: str,
    status: str,
    description: str = "",
    merge_sha: str | None = None,
) -> None:
    """Seed one item, optionally recording the merge a HOST build must contain.

    The merge goes into the audit metadata the store maps an item's `audit` from,
    written through the client's own public create verb. It is what makes the
    verified-proof cases discriminating about WHICH containment each leg owes: the
    host leg requires a released build to carry it, and the factory leg must not,
    because a factory candidate is the pre-merge head the merge was made from.
    """
    metadata: dict[str, object] = {}
    if merge_sha is not None:
        metadata["audit"] = {
            "merge_sha": merge_sha,
            "pr_number": _PR_NUMBER,
            "verification_timestamp": "2026-10-08T08:00:00Z",
            "commits": [merge_sha],
            "files_changed": ["fixture.txt"],
        }
    config = store_config(repo=repo)
    client = make_beads_client(config=config)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="feature",
            title=issue_id,
            description=description,
            assignee=None,
            created_at="2026-10-08T00:00:00Z",
            metadata=metadata,
        )
    )
    client.update_issue(issue_id=issue_id, status=status)


def _seed_comment(*, repo: Path, issue_id: str, text: str) -> None:
    make_beads_client(config=store_config(repo=repo)).add_comment(issue_id=issue_id, body=text)


def _proof_body(
    *,
    verdict: str = "host_verified",
    build: str = _BUILD,
    reproduced: str = "yes",
    identity: str = _REPLAY_IDENTITY,
    minute: str = "00",
) -> str:
    """One HOST record, declaring its build through the host `Build identity` bullet."""
    return (
        f"Proof of Done — {verdict} — {identity} — 2026-10-08T08:{minute}:00Z\n"
        "\n"
        f"- {RELEASE_TAG_LABEL}: {build}\n"
        "\n"
        f"## Assertion 1 — {_ASSERTION}\n"
        f"Reproduced: {reproduced}.\n"
    )


def _factory_proof_body(
    *,
    verdict: str = "verified",
    head: str = _FACTORY_HEAD,
    reproduced: str = "yes",
    run_id: str = _RUN_ID,
    minute: str = "00",
) -> str:
    """One ORDINARY FACTORY record, declaring its build the way the capture prompts do.

    SEPARATE FROM `_proof_body` BECAUSE THE TWO SHAPES ARE GENUINELY DIFFERENT, and
    rendering a factory record with a host build-identity bullet is what hid this
    reader's factory defect: every factory case in this module passed through the
    HOST parser, so the reader looked correct while no real factory record has ever
    carried that section.
    """
    return (
        f"Proof of Done — {verdict} — run {run_id} — 2026-10-08T08:{minute}:00Z\n"
        f"{PUBLISH_HEAD_LABEL}: {head}\n"
        "\n"
        f"## Assertion 1 — {_ASSERTION}\n"
        f"Reproduced: {reproduced}.\n"
    )


def _pr_comments_payload(*, body: str) -> str:
    return '{"comments": [{"body": ' + _json_string(text=body) + ', "url": "' + _RECORD_URL + '"}]}'


def _comments(*, bodies: tuple[str, ...]) -> CommandResult:
    """A comments payload over SEVERAL records, each carrying its own url.

    The single-body helper above gives every comment one url, which is fine while a
    case publishes one record. The host-leg cases publish two or three and turn on
    WHICH of them an observation rested on, so each needs a distinct url.
    """
    entries = ", ".join(
        '{"body": ' + _json_string(text=one) + ', "url": "' + f"{_RECORD_URL}{index}" + '"}'
        for index, one in enumerate(bodies, start=1)
    )
    return CommandResult(exit_code=0, stdout='{"comments": [' + entries + "]}", stderr="")


def _json_string(*, text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _derived_containment(*, argv: list[str]) -> CommandResult | None:
    """The forge's own answer about two refs, derived from the refs it was asked.

    `None` for any argv that is not the build comparison, so the caller falls
    through to its keyed answers. `identical` when the two refs are the same,
    `ahead` for the two pairs `_CONTAINING_PAIRS` declares, and `behind` for
    everything else — which is the honest answer for every fixture in this module.
    Inventing containment for two unrelated identities is what made the build
    control vacuous, so the containing relation is ENUMERATED rather than assumed:
    a reader aiming the comparison at some other pair collects `behind` and the
    case fails rather than passing on a canned answer.
    """
    endpoint = next((token for token in argv if _COMPARE_KEY in token), None)
    if endpoint is None:
        return None
    base, _, head = endpoint.split(_COMPARE_KEY, 1)[1].partition("...")
    if base == head:
        status = "identical"
    elif (base, head) in _CONTAINING_PAIRS:
        status = "ahead"
    else:
        status = "behind"
    return CommandResult(exit_code=0, stdout=f"{status}\n", stderr="")


def _runner(
    *, pr_state: str = "MERGED", proof_body: str | None = None, blob: str = _BLOB
) -> _Runner:
    """The three keyed forge reads this reader can issue.

    The build comparison carries no key, because `_Runner` derives it from the refs
    the adapter actually asked about — see its docstring for why a canned answer
    would make the build leg vacuous.
    """
    body = _factory_proof_body() if proof_body is None else proof_body
    return _Runner(
        answers={
            _PR_STATE_KEY: CommandResult(
                exit_code=0,
                stdout=f'{{"state": "{pr_state}", "updatedAt": "{_PR_UPDATED_AT}"}}',
                stderr="",
            ),
            _PR_COMMENTS_KEY: CommandResult(
                exit_code=0, stdout=_pr_comments_payload(body=body), stderr=""
            ),
            _BLOB_KEY: CommandResult(exit_code=0, stdout=f"{blob}\n", stderr=""),
        },
    )


def _reference(*, kind: str, target: dict[str, object]) -> dict[str, object]:
    return {"repo": _PROJECT_NAME, kind: target}


def _fulfilled_references() -> dict[str, dict[str, object]]:
    """One reference per kind, each naming the target the fixtures fulfil."""
    return {
        "item_status": _reference(
            kind="item_status", target={"item_id": _ITEM_ID, "status": "ready"}
        ),
        "item_comment": _reference(
            kind="item_comment", target={"item_id": _ITEM_ID, "marker": _MARKER}
        ),
        "pull_request_state": _reference(
            kind="pull_request_state", target={"number": _PR_NUMBER, "state": "MERGED"}
        ),
        "verified_proof": _reference(
            kind="verified_proof",
            target={"subject_id": _SUBJECT_ID, "build": _BUILD, "assertions": [_ASSERTION]},
        ),
        "file_on_branch": _reference(
            kind="file_on_branch",
            target={"branch": _BRANCH, "path": _FILE_PATH, "blob": _BLOB},
        ),
    }


def _unmet_references() -> dict[str, dict[str, object]]:
    """One reference per kind whose target the SAME fixtures demonstrably do not meet."""
    return {
        "item_status": _reference(
            kind="item_status", target={"item_id": _ITEM_ID, "status": "done"}
        ),
        "item_comment": _reference(
            kind="item_comment", target={"item_id": _ITEM_ID, "marker": "never-written-marker"}
        ),
        "pull_request_state": _reference(
            kind="pull_request_state", target={"number": _PR_NUMBER, "state": "OPEN"}
        ),
        "verified_proof": _reference(
            kind="verified_proof",
            target={
                "subject_id": _SUBJECT_ID,
                "build": _BUILD,
                "assertions": ["An assertion the record never lists."],
            },
        ),
        "file_on_branch": _reference(
            kind="file_on_branch",
            target={
                "branch": _BRANCH,
                "path": _FILE_PATH,
                "blob": "0000000000000000000000000000000000000000",
            },
        ),
    }


def _seeded_project(*, tmp_path: Path) -> Path:
    repo = _project(tmp_path=tmp_path)
    _seed_item(repo=repo, issue_id=_ITEM_ID, status="ready")
    _seed_comment(repo=repo, issue_id=_ITEM_ID, text=f"handoff\n\n{_MARKER}\n")
    _seed_item(
        repo=repo,
        issue_id=_SUBJECT_ID,
        status="acceptance",
        merge_sha=_MERGE_SHA,
        description=description_with_pointer(
            description="## Definition of Done\n\n- Something.\n",
            pointer=ProofPointer(
                pull_request=_PR_NUMBER,
                record_url=_RECORD_URL,
                run_id=_RUN_ID,
                timestamp="2026-10-08T08:00:00Z",
                verdict="verified",
            ),
        ),
    )
    return repo


def test_each_typed_result_reports_satisfaction_with_source_identity_and_evidence(
    tmp_path: Path,
) -> None:
    """Assertion 1: a fulfilled target of every kind is satisfied, with full provenance.

    One case per row of the scenario outline's `Examples` table. The scenario
    requires each observation to carry "repository, target, observation time and
    authoritative evidence identity", so every field is asserted rather than only
    the status — an observation that reported satisfaction with no evidence would
    otherwise pass a status-only assertion.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    for kind, reference in _fulfilled_references().items():
        observation = read_result(
            project_root=repo, reference=reference, runner=_runner(), now=_NOW
        )
        assert observation is not None, kind
        assert observation.status == OBSERVATION_SATISFIED, kind
        assert observation.repo == _PROJECT_NAME, kind
        assert kind in observation.target, kind
        assert observation.observed_at == _NOW, kind
        assert observation.evidence != "", kind
        assert observation.source != "", kind


def test_a_satisfied_comment_marker_states_that_it_proves_only_the_marker(
    tmp_path: Path,
) -> None:
    """Assertion 1, the narrowing the clause attaches to one kind.

    "Comment-marker satisfaction proves only the requested marker's presence; it
    MUST NOT stand in for completed implementation or verified proof." A satisfied
    observation is the thing that gets quoted onward, so the narrowing has to ride
    on the observation rather than live only in the clause.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    observation = read_result(
        project_root=repo,
        reference=_fulfilled_references()["item_comment"],
        runner=_runner(),
        now=_NOW,
    )
    assert observation is not None
    assert observation.status == OBSERVATION_SATISFIED
    assert "marker" in observation.detail
    assert "verified proof" in observation.detail


def test_an_observable_unmet_target_is_never_reported_satisfied(tmp_path: Path) -> None:
    """The negative control for every row of the outline, against the same fixtures.

    Each reference here names a target the fixtures demonstrably do NOT meet, and
    the fixtures are the ones the satisfied case above passes on — so a reader that
    reported satisfaction unconditionally would fail here, and one that could never
    report it would fail there.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    for kind, reference in _unmet_references().items():
        observation = read_result(
            project_root=repo, reference=reference, runner=_runner(), now=_NOW
        )
        assert _status(observation=observation) != OBSERVATION_SATISFIED, kind


def test_an_observable_unmet_target_of_every_kind_is_unsatisfied(tmp_path: Path) -> None:
    """Assertion 2: an unmet target the reader DID observe is a confident negative.

    One case per row of the scenario outline, over the same fixtures the satisfied
    case passes on — the outline requires both answers from one reading of one
    source. The provenance is asserted on this arm too: an unsatisfied observation
    has to say what WAS observed, or an operator cannot tell a target that moved
    from an instrument that was pointed somewhere else.

    `outstanding` is asserted rather than inferred from the status, because that is
    the question both tracking callers ask of the result.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    for kind, reference in _unmet_references().items():
        observation = read_result(
            project_root=repo, reference=reference, runner=_runner(), now=_NOW
        )
        assert observation is not None, kind
        assert observation.status == _UNSATISFIED, kind
        assert observation.repo == _PROJECT_NAME, kind
        assert kind in observation.target, kind
        assert observation.observed_at == _NOW, kind
        assert observation.evidence != "", kind
        assert observation.source != "", kind
        assert observation.outstanding is True, kind


def test_a_record_that_is_not_evidence_is_unsatisfied_and_not_unobservable(
    tmp_path: Path,
) -> None:
    """The discriminating line between an unmet target and a failed observation.

    All three of these READ their source successfully and found it wanting: a
    comment that says verified but is not a typed record, a verified record naming
    another build, and a remote blob differing from a path that exists locally.
    Reporting any of them as unobservable would hide a real negative behind a
    diagnostic, and the clause's own prohibition runs the other way too —
    unobservable must not become "a confident negative", so the two statuses have
    to be earned separately.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    local = repo / _FILE_PATH
    local.parent.mkdir(parents=True, exist_ok=True)
    _ = local.write_text("a stale local copy of the governed clause\n", encoding="utf-8")
    cases = (
        (
            _fulfilled_references()["verified_proof"],
            _runner(proof_body="Everything here is verified and reproduced: yes.\n"),
        ),
        (
            _fulfilled_references()["verified_proof"],
            _runner(proof_body=_factory_proof_body(head=_OTHER_FACTORY_HEAD)),
        ),
        (
            _fulfilled_references()["file_on_branch"],
            _runner(blob="1111111111111111111111111111111111111111"),
        ),
    )
    for reference, runner in cases:
        observation = read_result(project_root=repo, reference=reference, runner=runner, now=_NOW)
        assert observation is not None
        assert observation.status == _UNSATISFIED


def test_a_comment_saying_verified_cannot_satisfy_a_typed_verified_proof(
    tmp_path: Path,
) -> None:
    """Scenario 146: "a comment saying verified cannot satisfy a typed verified proof".

    The subject's pull request carries a comment whose text says the work is
    verified but which is not a typed Proof of Done record at all. The typed read
    validates the record's own semantics, so the comment cannot stand in for one.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    observation = read_result(
        project_root=repo,
        reference=_fulfilled_references()["verified_proof"],
        runner=_runner(proof_body="Everything here is verified and reproduced: yes.\n"),
        now=_NOW,
    )
    assert _status(observation=observation) != OBSERVATION_SATISFIED


def test_a_host_record_that_is_not_independent_evidence_cannot_satisfy_the_proof(
    tmp_path: Path,
) -> None:
    """The two host readings that reported SATISFIED, driven through the real reader.

    The clause requires the verified-proof read to validate the EXISTING typed
    Proof of Done semantics, and the host leg of the acceptance section already
    rejects both of these: a replay whose publishing identity equals the capture's
    is not evidence "however it was posted", and a record is never edited, so a
    later `host_not_reproduced` supersedes an earlier success rather than sitting
    beside it.

    They are bound HERE as well as at the unit tier because this is the tier the
    scenario binds, and because the component reproduction that found them went
    through `observe_verified_proof` directly — which cannot show that the reader
    an operator actually calls reaches the same verdict.

    Both are UNSATISFIED rather than unobservable: every record was read and the
    reader established that no independent, unretracted replay covers the scope.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    capture = _proof_body(verdict="host_recorded", identity=_CAPTURE_IDENTITY, minute="00")
    cases = (
        (
            "a replay published by the capturing identity",
            (
                capture,
                _proof_body(verdict="host_verified", identity=_CAPTURE_IDENTITY, minute="01"),
            ),
        ),
        (
            "a success a newer failed replay retracted",
            (
                capture,
                _proof_body(verdict="host_verified", identity=_REPLAY_IDENTITY, minute="01"),
                _proof_body(
                    verdict="host_not_reproduced",
                    identity=_REPLAY_IDENTITY,
                    minute="02",
                    reproduced="no",
                ),
            ),
        ),
    )
    for label, bodies in cases:
        observation = read_result(
            project_root=repo,
            reference=_fulfilled_references()["verified_proof"],
            runner=_Runner(answers={_PR_COMMENTS_KEY: _comments(bodies=bodies)}),
            now=_NOW,
        )
        assert _status(observation=observation) == _UNSATISFIED, label
        assert observation.source == SOURCE_PROOF_RECORD, label
    # THE POSITIVE CONTROL, on the same fixture shape: an INDEPENDENT replay of the
    # same capture, against the same build, IS satisfied. Without it both refusals
    # above are equally consistent with a reader that refuses every host record.
    independent = read_result(
        project_root=repo,
        reference=_fulfilled_references()["verified_proof"],
        runner=_Runner(
            answers={
                _PR_COMMENTS_KEY: _comments(
                    bodies=(
                        capture,
                        _proof_body(
                            verdict="host_verified", identity=_REPLAY_IDENTITY, minute="01"
                        ),
                    )
                )
            }
        ),
        now=_NOW,
    )
    assert _status(observation=independent) == OBSERVATION_SATISFIED


def test_an_ordinary_factory_proof_of_its_published_candidate_is_satisfied(
    tmp_path: Path,
) -> None:
    """THE REAL FACTORY RECORD SHAPE, read end to end through the reader an operator calls.

    Measured 2026-10-09 against `overseer-s32tdk`'s own `verified` record on pull
    request 2376: the typed parser reads it, reproduces its first assertion and
    names `Publish-branch head f5a8185687f111807a7e1fe926674fe316bc8fb2`, while
    this reader reported UNSATISFIED for exactly that build and assertion. A
    factory record carries no host `Build identity` section — that section names a
    release, and the capture and verify stages run on the draft pull request before
    the merge any release could contain — so a reader asking for one asks every
    ordinary factory proof for a field it structurally cannot have, and the refusal
    is indistinguishable from a record that genuinely proves nothing.

    TWO INDEPENDENT REPAIRS ARE BOUND HERE, and both are read off the COMPARISON
    LIST rather than off the status, because the fixture answers a valid status for
    any pair it is asked and a status alone therefore cannot say which question was
    put. The declaration must be read through the canonical publish-head parser:
    satisfaction is reachable only by asking `compare/<requested>...<declared
    head>`, the one containing pair the fixture declares for this record. And the
    host leg's SUBJECT-MERGE containment must not be imposed here: this subject
    RECORDS a merge, so a composed reader would also ask whether the candidate
    carries it — a question a pre-merge head cannot answer yes to, since that head
    is what the merge was made from. Exactly one comparison is therefore asserted.

    The sibling case below is the negative control: the same shape declaring a
    DIFFERENT head is refused, so this cannot be a reader that admits any factory
    record carrying a publish-head line.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    runner = _runner()
    observation = read_result(
        project_root=repo,
        reference=_fulfilled_references()["verified_proof"],
        runner=runner,
        now=_NOW,
    )
    assert _status(observation=observation) == OBSERVATION_SATISFIED, observation.detail
    comparisons = tuple(
        token for argv, _cwd in runner.calls for token in argv if _COMPARE_KEY in token
    )
    assert comparisons == (
        f"repos/{{owner}}/{{repo}}/compare/{_BUILD}...{_FACTORY_HEAD}",
    ), comparisons


def test_a_record_naming_another_build_cannot_satisfy_the_requested_build(
    tmp_path: Path,
) -> None:
    """The build leg of the typed proof read, separated from the scope leg.

    The record lists the requested assertion as reproduced and carries a verified
    verdict; only the build identity differs. Without this control a reader that
    ignored the build entirely would pass every other proof case in this file.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    observation = read_result(
        project_root=repo,
        reference=_fulfilled_references()["verified_proof"],
        runner=_runner(proof_body=_factory_proof_body(head=_OTHER_FACTORY_HEAD)),
        now=_NOW,
    )
    assert _status(observation=observation) != OBSERVATION_SATISFIED


def test_a_stale_local_file_cannot_satisfy_the_remote_blob_result(tmp_path: Path) -> None:
    """Scenario 146: "a stale local branch file cannot satisfy the remote blob result".

    The path EXISTS in the working tree and holds bytes, and the remote blob the
    forge reports is a different object. The clause requires the comparison to be
    against "the remote branch's blob identity, not a stale checkout or mere path
    existence", so the local file must not move the answer.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    local = repo / _FILE_PATH
    local.parent.mkdir(parents=True, exist_ok=True)
    _ = local.write_text("a stale local copy of the governed clause\n", encoding="utf-8")
    observation = read_result(
        project_root=repo,
        reference=_fulfilled_references()["file_on_branch"],
        runner=_runner(blob="1111111111111111111111111111111111111111"),
        now=_NOW,
    )
    assert _status(observation=observation) != OBSERVATION_SATISFIED


def test_an_arbitrary_shell_predicate_is_not_a_result_reference(tmp_path: Path) -> None:
    """The clause: "Arbitrary shell predicates MUST NOT be accepted as result references".

    The refused reference also carries a perfectly valid repository identity, so
    the refusal is earned by the predicate rather than by anything else about it.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    observation = read_result(
        project_root=repo,
        reference={"repo": _PROJECT_NAME, "shell": "test -f SPECIFICATION/contracts.md"},
        runner=_runner(),
        now=_NOW,
    )
    assert _status(observation=observation) != OBSERVATION_SATISFIED


def test_a_failed_target_observation_is_never_reported_satisfied(tmp_path: Path) -> None:
    """The clause: an authentication or network failure is never satisfaction.

    Two shapes of failure, against the target the satisfied case passes on: the
    forge refusing the way an unauthenticated `gh` does — a non-zero exit with the
    credential complaint on stderr — and a source that answers nothing at all.
    Neither may become satisfaction or a confident negative. This slice asserts
    only the first half; the `unobservable` status is its own assertion.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    unauthenticated = _Runner(
        answers={
            _PR_STATE_KEY: CommandResult(
                exit_code=4, stdout="", stderr="gh: authentication required\n"
            )
        }
    )
    for runner in (unauthenticated, _Runner(answers={})):
        observation = read_result(
            project_root=repo,
            reference=_fulfilled_references()["pull_request_state"],
            runner=runner,
            now=_NOW,
        )
        assert _status(observation=observation) != OBSERVATION_SATISFIED


def test_a_failed_or_malformed_observation_is_unobservable_and_names_the_failed_source(
    tmp_path: Path,
) -> None:
    """Assertion 3, and Scenario 146's second sub-scenario.

    One case per way an observation can fail, and each asserts the SOURCE the
    clause requires naming after a bounded read — because "unobservable" alone
    sends an operator looking at whichever source they guess. They cover every
    named source plus the two the reader can fail at before any of them is
    reached: a reference that will not parse and a repository that will not
    resolve. Authentication, a payload that is not the shape the read asked for,
    an absent ledger record and a source that answers nothing are all here, and
    none of them may become satisfaction or a confident negative.

    THE MALFORMED-VALUE CASES ARE NOT THE MALFORMED-PAYLOAD CASES, and the
    distinction is why both sets are present. A payload of the wrong SHAPE fails
    the read before any comparison is reachable; a well-formed payload carrying a
    value that is not evidence reaches the comparison, and a reader that compares
    first turns it into a verdict. Those three — a blank `updatedAt`, a state
    outside the forge's vocabulary, and a blob answer of `null` — each failed in a
    direction the clause names, two as confident negatives and one as outright
    satisfaction, so neither a permissive nor a strict default would have caught
    all three.

    `outstanding` is asserted on every case, since the clause requires a bounded
    read failure to leave the obligation outstanding — which is a different
    statement from the status and is the one both tracking callers act on.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    malformed_state = _Runner(
        answers={_PR_STATE_KEY: CommandResult(exit_code=0, stdout="<html>", stderr="")}
    )
    unauthenticated = _Runner(
        answers={
            _PR_STATE_KEY: CommandResult(
                exit_code=4, stdout="", stderr="gh: authentication required\n"
            )
        }
    )
    unreadable_comments = _Runner(
        answers={_PR_COMMENTS_KEY: CommandResult(exit_code=4, stdout="", stderr="gh: no access\n")}
    )
    blank_blob = _Runner(answers={_BLOB_KEY: CommandResult(exit_code=0, stdout="\n", stderr="")})
    # The three MALFORMED-VALUE readings, each of which the forge answers
    # SUCCESSFULLY and in a well-formed payload of exactly the requested shape.
    # They are here rather than only at the unit tier because they are the ones
    # that crossed the clause's line in BOTH directions: the blank timestamp read
    # as SATISFACTION, while the uninterpretable state and the `null` blob read as
    # CONFIDENT NEGATIVES. The payload-shape cases above cannot stand in for any of
    # them — there the shape is wrong, here it is right and the VALUE is not
    # evidence.
    blank_updated_at = _Runner(
        answers={
            _PR_STATE_KEY: CommandResult(
                exit_code=0, stdout='{"state": "OPEN", "updatedAt": ""}', stderr=""
            )
        }
    )
    uninterpretable_state = _Runner(
        answers={
            _PR_STATE_KEY: CommandResult(
                exit_code=0,
                stdout='{"state": "INVALID", "updatedAt": "2026-10-08T09:00:00Z"}',
                stderr="",
            )
        }
    )
    null_blob = _Runner(answers={_BLOB_KEY: CommandResult(exit_code=0, stdout="null\n", stderr="")})
    cases = (
        ("result reference", {"repo": _PROJECT_NAME, "shell": "test -f a.md"}, _runner()),
        (
            "repository resolution",
            {
                "repo": "a-repository-nobody-configured",
                "item_status": {"item_id": _ITEM_ID, "status": "ready"},
            },
            _runner(),
        ),
        (
            "ledger",
            {
                "repo": _PROJECT_NAME,
                "item_status": {"item_id": "bd-ib-never-filed", "status": "ready"},
            },
            _runner(),
        ),
        (
            "ledger",
            {
                "repo": _PROJECT_NAME,
                "item_comment": {"item_id": "bd-ib-never-filed", "marker": _MARKER},
            },
            _runner(),
        ),
        ("forge", _fulfilled_references()["pull_request_state"], unauthenticated),
        ("forge", _fulfilled_references()["pull_request_state"], malformed_state),
        ("forge", _fulfilled_references()["pull_request_state"], blank_updated_at),
        ("forge", _fulfilled_references()["pull_request_state"], uninterpretable_state),
        ("proof record", _fulfilled_references()["verified_proof"], unreadable_comments),
        ("git object", _fulfilled_references()["file_on_branch"], blank_blob),
        ("git object", _fulfilled_references()["file_on_branch"], null_blob),
    )
    for source, reference, runner in cases:
        observation = read_result(project_root=repo, reference=reference, runner=runner, now=_NOW)
        assert _status(observation=observation) == _UNOBSERVABLE, source
        assert observation.source == source, source
        assert observation.observed_at == _NOW, source
        assert observation.detail != "", source
        assert observation.outstanding is True, source


@dataclass(kw_only=True)
class _HttpTransport:
    """A `CommandRunner` that issues the adapter's OWN endpoint over real HTTP.

    This is the one case in the module where a recording stand-in cannot answer
    the question. Every other case asserts the argv the adapter BUILT, and an
    argv assertion cannot see what a transport then does with it: the defect this
    guards is that `?ref=proof#variant` is a perfectly well-formed endpoint string
    whose `#` an HTTP client reads as a FRAGMENT DELIMITER, so the server is asked
    for `ref=proof` and never learns that `variant` was wanted. The request has to
    actually be issued for that to be observable.

    `urlopen` is used rather than the `gh` binary deliberately. The fragment is
    dropped by URL parsing — RFC 3986 says a fragment is not transmitted — so the
    stdlib client reproduces the defect byte for byte while keeping this tier
    hermetic and free of a `gh` installation. The argv is asserted to be the
    production shape before it is used, so this transport cannot quietly accept an
    endpoint the real adapter would never emit.
    """

    base: str
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, env, stdin
        self.calls.append(tuple(argv))
        assert argv[:2] == ["gh", "api"], argv
        assert argv[3:] == ["--jq", ".sha"], argv
        request = Request(url=f"{self.base}/{argv[2]}")  # noqa: S310 — loopback fixture.
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            payload: object = json.loads(response.read().decode())
        assert isinstance(payload, dict)
        return CommandResult(exit_code=0, stdout=f"{payload['sha']}\n", stderr="")


def _remote_fixture(
    *, exact: tuple[str, str], received: list[tuple[str, str]]
) -> ThreadingHTTPServer:
    """A loopback forge that answers `_BLOB_EXACT` for ONE (path, ref) pair.

    EVERY OTHER PAIR — including every corruption of the requested one — answers
    `_BLOB_SHADOW`. That asymmetry is what makes the regression discriminating in
    both directions rather than merely failing: a reference asking for the SHADOW
    blob is satisfied only by a request that reached the wrong target, and one
    asking for the EXACT blob is satisfied only by a request that reached the
    right one. A fixture answering the same blob everywhere would pass whatever
    the transport sent.
    """

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — the stdlib fixes this method name.
            split = urlsplit(self.path)
            path = unquote(split.path.split("/contents/", 1)[-1])
            ref = parse_qs(split.query).get("ref", [""])[0]
            received.append((path, ref))
            blob = _BLOB_EXACT if (path, ref) == exact else _BLOB_SHADOW
            body = json.dumps({"sha": blob}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            _ = self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    return ThreadingHTTPServer(("127.0.0.1", 0), _Handler)


@pytest.mark.parametrize(
    ("branch", "path"),
    [
        (_VARIANT_BRANCH, _FILE_PATH),
        (_BRANCH, _FRAGMENT_PATH),
        (_BRANCH, _SPACED_PATH),
    ],
)
def test_a_remote_blob_read_asks_for_the_exact_branch_and_path_requested(
    tmp_path: Path, branch: str, path: str
) -> None:
    """Scenario 146's remote-blob requirement, read through a real HTTP request.

    The clause requires a file result to compare "the remote branch's blob
    identity". That is a statement about WHICH branch and WHICH path, and the
    adapter interpolated both raw into an API URL — so a target whose branch or
    path contains a `#` silently became a request for a DIFFERENT, shorter target,
    and the answer about that other target was reported as the answer about this
    one. `git check-ref-format --branch proof#variant` succeeds, so the branch is
    not exotic; it is simply a name no raw interpolation survives.

    Each row is a target a raw interpolation corrupts differently: a `#` in the
    BRANCH truncates the query value, a `#` in the PATH truncates the path and
    takes the whole query with it, and a SPACE in the path produces a URL no
    client can send intact. All three are asserted three ways, because each alone
    admits a wrong reading — the SHADOW case alone cannot tell a corrected request
    from a broken fixture, the EXACT case alone cannot tell a correct request from
    a fixture answering everything, and the received-pair assertion alone says
    nothing about which observation the reader published.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    received: list[tuple[str, str]] = []
    server = _remote_fixture(exact=(path, branch), received=received)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        shadow = read_result(
            project_root=repo,
            reference=_reference(
                kind="file_on_branch",
                target={"branch": branch, "path": path, "blob": _BLOB_SHADOW},
            ),
            runner=_HttpTransport(base=base),
            now=_NOW,
        )
        exact = read_result(
            project_root=repo,
            reference=_reference(
                kind="file_on_branch",
                target={"branch": branch, "path": path, "blob": _BLOB_EXACT},
            ),
            runner=_HttpTransport(base=base),
            now=_NOW,
        )
    finally:
        server.shutdown()
        server.server_close()
    assert received == [(path, branch), (path, branch)], received
    assert _status(observation=shadow) == _UNSATISFIED
    assert _status(observation=exact) == OBSERVATION_SATISFIED
    assert exact.evidence == f"git blob {_BLOB_EXACT} at {branch}:{path}"


def test_a_query_to_the_wrong_repository_cannot_discharge_the_requested_target(
    tmp_path: Path,
) -> None:
    """Scenario 146: "a query to the wrong repository cannot discharge the target".

    The item the reference names IS present, at exactly the status requested, in
    the tenant the reader is standing in — so a reader that ignored the repository
    identity and read its own would report satisfaction. The requested repository
    does not resolve, which the clause puts in the unobservable set, so the
    obligation stays outstanding instead.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    observation = read_result(
        project_root=repo,
        reference={
            "repo": "a-repository-nobody-configured",
            "item_status": {"item_id": _ITEM_ID, "status": "ready"},
        },
        runner=_runner(),
        now=_NOW,
    )
    assert _status(observation=observation) == _UNOBSERVABLE
    assert observation.repo == "a-repository-nobody-configured"
    assert _ITEM_ID in observation.target


def test_an_unobservable_reading_carries_no_evidence_it_did_not_find(
    tmp_path: Path,
) -> None:
    """A read that failed has nothing to cite, and must not manufacture a citation.

    The clause separates the failed SOURCE from the source EVIDENCE identity for
    exactly this reason: an unobservable reading names what it could not read and
    leaves the evidence empty, where a satisfied or unsatisfied reading of the same
    target carries the artifact it rested on. An evidence string here would read as
    a record somebody could look up.
    """
    repo = _seeded_project(tmp_path=tmp_path)
    observation = read_result(
        project_root=repo,
        reference={
            "repo": _PROJECT_NAME,
            "item_status": {"item_id": "bd-ib-never-filed", "status": "ready"},
        },
        runner=_runner(),
        now=_NOW,
    )
    assert _status(observation=observation) == _UNOBSERVABLE
    assert observation.evidence == ""


def test_every_cross_tenant_command_executes_from_the_named_repository(
    tmp_path: Path,
) -> None:
    """The clause: "cross-tenant commands MUST execute from that target repository".

    The reader is given a reference naming a CONFIGURED SIBLING rather than the
    project itself, and every argv the runner saw must have been issued from that
    sibling's clone. A reader that resolved the repository for its configuration
    and then ran `gh` in the invoking project would answer about the wrong forge
    repository while reporting the requested one.
    """
    repo = _project(tmp_path=tmp_path)
    sibling = tmp_path / "sibling-repo"
    sibling.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"cross_repo_targets": {"sibling-repo": {'
        '"github_url": "https://github.com/thewoolleyman/sibling-repo",'
        f' "local_clone": "{sibling}"'
        "}},"
        ' "livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    runner = _runner()
    observation = read_result(
        project_root=repo,
        reference={
            "repo": "sibling-repo",
            "pull_request_state": {"number": _PR_NUMBER, "state": "MERGED"},
        },
        runner=runner,
        now=_NOW,
    )
    assert _status(observation=observation) == OBSERVATION_SATISFIED
    assert runner.calls != []
    for _argv, cwd in runner.calls:
        assert cwd == sibling
