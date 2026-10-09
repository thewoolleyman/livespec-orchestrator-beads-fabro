"""Tests for the typed verified-proof adapter.

The four things the clause requires validating — record semantics, verdict, build
and scope — each get their own control, because a reader that skipped any one of
them would still pass every other case in this file. The fourth, scope, is the
one a text match would appear to satisfy, so its control publishes a record that
says "verified" in prose and nothing a typed reader can grade.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    BeadsRecord,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    COMMIT_LABEL,
    RELEASE_TAG_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer import (
    ProofPointer,
    description_with_pointer,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNOBSERVABLE,
    OBSERVATION_UNSATISFIED,
    SOURCE_LEDGER,
    SOURCE_PROOF_RECORD,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_proof import (
    VERIFIED_PROOF_VERDICTS,
    observe_verified_proof,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import ResultRepository
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import VerifiedProofTarget

_SUBJECT_ID = "bd-ib-proof"
_PR_NUMBER = 146
_BUILD = "v0.170.0"
_ASSERTION = "The reader validates the typed record rather than matching text."
_RECORD_URL = f"https://example.test/owner/repo/pull/{_PR_NUMBER}#issuecomment-1"
_NOW = "2026-10-08T12:00:00Z"
# The containment comparison is told from the comments read by its own endpoint, so
# a case can answer each independently.
_COMPARE_KEY = "/compare/"
# The merge the subject records in its audit metadata. The host-leg rule admits a
# record "naming a build identity containing the merged change", so this is the
# other thing a record's build must contain besides the requested build.
_MERGE_SHA = "c" * 40
# The capture's identity and an INDEPENDENT replayer's. The host-leg rule admits a
# replay only from a party other than the one that recorded the capture, so every
# positive control here needs two distinct identities and the self-replay control
# needs one identity used twice.
_CAPTURE_IDENTITY = "session 1e14094a-0000-4000-8000-000000000001"
_REPLAY_IDENTITY = "session b1e14094-0000-4000-8000-000000000002"


@dataclass(kw_only=True)
class _Runner:
    """A `CommandRunner` answering the comments read and the containment compare apart.

    TWO answers rather than one, because validating a host replay's build is a
    SECOND forge read. A single-answer runner handed the comments payload to the
    comparison too, whose `.status` then parsed as an unknown value — so every host
    case would report unreadable containment and the positive controls could not be
    told from the refusals.
    """

    comments: CommandResult
    compare: CommandResult
    statuses: dict[str, str] = field(default_factory=dict)
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
        if any(_COMPARE_KEY in token for token in argv):
            for ref, status in self.statuses.items():
                if ref in argv[2]:
                    return CommandResult(exit_code=0, stdout=f"{status}\n", stderr="")
            return self.compare
        return self.comments

    @property
    def comparisons(self) -> tuple[str, ...]:
        """The endpoint of every containment comparison asked, in order.

        Exposed so a case can assert WHICH refs were compared. A canned answer
        makes a comparison aimed at the wrong refs indistinguishable from one
        aimed correctly, because the fixture replies the same either way.
        """
        return tuple(
            argv[2] for argv, _cwd in self.calls if any(_COMPARE_KEY in token for token in argv)
        )


class _DescriptionlessClient:
    """A tenant whose record omits `description`, the way a sparse record can."""

    def show_issue(self, *, issue_id: str) -> BeadsRecord:
        return {"id": issue_id}


@dataclass(kw_only=True)
class _AuditShapeClient:
    """A tenant whose metadata records no merge, in the shapes sparseness produces.

    `bd` records are `omitempty`-SPARSE, so `metadata` can be absent outright and a
    present `metadata` can carry no `audit`. Neither is a malformed record: the
    subject simply records no merge, which is the same answer as a subject whose
    work has not closed. Seeding an ABSENT metadata through `IssueDraft` is not
    possible — its `metadata` is typed as a mapping — so this read-only stub
    supplies the shape the public write verb cannot.
    """

    metadata: object

    def show_issue(self, *, issue_id: str) -> BeadsRecord:
        return cast(
            "BeadsRecord",
            {"id": issue_id, "description": _pointed_description(), "metadata": self.metadata},
        )


def _repo(*, tmp_path: Path, prefix: str | None = "bd-ib") -> ResultRepository:
    clone = tmp_path / "repo"
    clone.mkdir()
    connection: dict[str, object] = {} if prefix is None else {"prefix": prefix}
    _ = (clone / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"connection": connection}}),
        encoding="utf-8",
    )
    return ResultRepository(name="repo", clone=clone)


def _seed_subject(
    *, repository: ResultRepository, description: str, merge_sha: str | None = None
) -> None:
    """Seed the subject, optionally recording the merge its proof must contain.

    `merge_sha` goes into the audit metadata the store maps an item's `audit`
    from, written through the client's own public create verb. It is OPTIONAL
    because the host-leg rule admits a record "naming a build identity containing
    the merged change" — which presupposes a merged change. A subject whose work
    has not closed carries no recorded merge, so that requirement is vacuous for
    it rather than unmet; the case below asserts exactly that, because making it
    fail closed would leave every not-yet-closed subject permanently
    unobservable.
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
    client = make_beads_client(config=store_config(repo=repository.clone))
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_SUBJECT_ID,
            issue_type="feature",
            title=_SUBJECT_ID,
            description=description,
            assignee=None,
            created_at="2026-10-08T00:00:00Z",
            metadata=metadata,
        )
    )


def _pointed_description() -> str:
    return description_with_pointer(
        description="## Definition of Done\n\n- Something.\n",
        pointer=ProofPointer(
            pull_request=_PR_NUMBER,
            record_url=_RECORD_URL,
            run_id="01M4PROOF",
            timestamp="2026-10-08T08:00:00Z",
            verdict="verified",
        ),
    )


def _record_body(
    *,
    verdict: str = "verified",
    label: str = RELEASE_TAG_LABEL,
    build: str = _BUILD,
    reproduced: str = "yes",
    identity: str = "run 01M4PROOF",
    minute: str = "00",
) -> str:
    return (
        f"Proof of Done — {verdict} — {identity} — 2026-10-08T08:{minute}:00Z\n"
        "\n"
        f"- {label}: {build}\n"
        "\n"
        f"## Assertion 1 — {_ASSERTION}\n"
        f"Reproduced: {reproduced}.\n"
    )


def _runner(
    *,
    bodies: tuple[str, ...] = (),
    exit_code: int = 0,
    stdout: str | None = None,
    containment: str = "identical",
    containment_exit: int = 0,
    statuses: dict[str, str] | None = None,
) -> _Runner:
    """A runner over `bodies`, each comment carrying its own url.

    The urls are numbered from ONE so a single-record case still renders
    `_RECORD_URL`, and so a multi-record case can say WHICH record an observation
    cited — the whole supersession question is which of two records was read.

    `containment` is the `.status` the forge comparison answers for any refs: it is
    `identical` and `ahead` when the record's build carries the requested one,
    `behind` when it does not, and `containment_exit` non-zero makes the comparison
    UNREADABLE, which is a different reading from either.

    `statuses` answers PER REF NAMED ANYWHERE IN THE COMPARISON instead, for the
    cases that assert which refs were compared rather than what the comparison
    said. A canned answer cannot discriminate there — it replies the same whatever
    the adapter asked. Matching anywhere in the endpoint rather than on the head
    alone is what lets a case key the comparison whose BASE it cares about: the
    requested-build relation puts the record's build in the head, while the
    merge-containment relation puts the merge in the base.
    """
    payload = (
        stdout
        if stdout is not None
        else json.dumps(
            {
                "comments": [
                    {
                        "body": one,
                        "url": f"https://example.test/owner/repo/pull/{_PR_NUMBER}#issuecomment-{index}",
                    }
                    for index, one in enumerate(bodies, start=1)
                ]
            }
        )
    )
    return _Runner(
        comments=CommandResult(exit_code=exit_code, stdout=payload, stderr=""),
        compare=CommandResult(exit_code=containment_exit, stdout=f"{containment}\n", stderr=""),
        statuses={} if statuses is None else statuses,
    )


def _target(
    *, assertions: tuple[str, ...] = (_ASSERTION,), build: str = _BUILD
) -> VerifiedProofTarget:
    return VerifiedProofTarget(subject_id=_SUBJECT_ID, build=build, assertions=assertions)


def test_the_verified_verdict_set_is_the_two_reproduction_verdicts() -> None:
    """`captured` says a proof was produced, not that anyone reproduced it."""
    assert VERIFIED_PROOF_VERDICTS == ("verified", "host_verified")


def test_a_verified_record_naming_the_build_and_scope_is_satisfied(tmp_path: Path) -> None:
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    observation = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_runner(bodies=(_record_body(),)),
        now=_NOW,
    )
    assert observation is not None
    assert observation.status == OBSERVATION_SATISFIED
    assert observation.source == SOURCE_PROOF_RECORD
    assert observation.evidence == f"proof record {_RECORD_URL} verdict verified build {_BUILD}"


def test_a_host_verified_record_naming_a_commit_build_is_satisfied(tmp_path: Path) -> None:
    """The second verified-class verdict, and the no-release arm of the build read.

    Where no release applies the record names the default-branch commit, and the
    containment ref is that commit — so a reader that only ever compared release
    tags would refuse every host replay of unreleased work.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    body = _record_body(verdict="host_verified", label=COMMIT_LABEL, build="ac7ebb0f")
    observation = observe_verified_proof(
        repository=repository,
        target=_target(build="ac7ebb0f"),
        runner=_runner(bodies=(body,)),
        now=_NOW,
    )
    assert observation is not None
    assert observation.status == OBSERVATION_SATISFIED


def _capture_and_replay(
    *, replay_verdict: str = "host_verified", replay_identity: str = _REPLAY_IDENTITY, **kwargs: str
) -> tuple[str, ...]:
    """A `host_recorded` capture followed by one replay of it, in forge order."""
    return (
        _record_body(verdict="host_recorded", identity=_CAPTURE_IDENTITY, minute="00"),
        _record_body(verdict=replay_verdict, identity=replay_identity, minute="01", **kwargs),
    )


def test_an_independent_replay_of_a_containing_build_is_satisfied(tmp_path: Path) -> None:
    """THE POSITIVE CONTROL for every host refusal below, and it is load-bearing.

    Four refusals follow this case, and each of them is only evidence of a working
    rule if a genuine host proof still SATISFIES. Without this case the whole group
    is equally consistent with a reader that refuses every host record — which is
    the failure mode a fail-closed change arrives at most easily.

    "Truly independent" is the operative word: the capture and the replay carry
    DIFFERENT identities, and the build the replay names is compared against the
    requested one through the forge rather than string-matched.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    runner = _runner(bodies=_capture_and_replay(), containment="ahead")
    observation = observe_verified_proof(
        repository=repository, target=_target(), runner=runner, now=_NOW
    )
    assert observation.status == OBSERVATION_SATISFIED
    assert observation.source == SOURCE_PROOF_RECORD
    # `ahead` rather than `identical`, so the control also proves CONTAINMENT is what
    # is asked. A reader comparing the build labels as strings would refuse this.
    assert any(_COMPARE_KEY in token for call in runner.calls for token in call[0])


def test_the_containment_comparison_names_the_requested_build_as_its_base(
    tmp_path: Path,
) -> None:
    """WHICH refs the comparison names, not merely that a comparison was made.

    `compare/<base>...<head>` asks whether HEAD carries BASE, so the requested
    build has to be the base and the record's build the head. Get that pair wrong
    — swap them, or aim either at some other value — and the relation inverts
    while every status the forge can answer stays a perfectly valid status.

    THE SIBLING CASES ABOVE CANNOT SEE THAT. They assert the status the comparison
    returned, from a fixture that returns it for any refs at all, so a reader
    aiming the comparison at the wrong pair collects the same canned answer and
    reports the same verdict. Measured on this tree: rebuilding the containment
    reader with the subject id as its base left all 33 unit cases passing.

    So this case answers per-REF instead. The record names a LATER release than
    the one requested, `v0.9.9` is the only ref with an answer, and every other
    comparison falls through to `behind` — so satisfaction is reachable only by
    asking exactly `compare/<requested>...<record build>`. The endpoint is then
    asserted literally, which pins the order a status alone cannot.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    runner = _runner(
        bodies=_capture_and_replay(build="v0.9.9"),
        containment="behind",
        statuses={"v0.9.9": "ahead"},
    )
    observation = observe_verified_proof(
        repository=repository, target=_target(), runner=runner, now=_NOW
    )
    assert observation.status == OBSERVATION_SATISFIED
    assert runner.comparisons == (f"repos/{{owner}}/{{repo}}/compare/{_BUILD}...v0.9.9",)


def test_a_replay_by_the_capturing_identity_is_not_satisfied(tmp_path: Path) -> None:
    """The host-leg rule: a record whose replaying identity equals its capturing one.

    The clause rejects it "however it was posted", so this is enforced on the READ
    rather than left to the posting primitive that also refuses it — a record
    reaches a pull request by routes that primitive does not own.

    Reported as UNSATISFIED rather than unobservable: the records were read and the
    reader established that no independent replay exists, which is an observed
    unmet target rather than a failure to observe.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    observation = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_runner(
            bodies=_capture_and_replay(replay_identity=_CAPTURE_IDENTITY), containment="identical"
        ),
        now=_NOW,
    )
    assert observation.status == OBSERVATION_UNSATISFIED
    assert observation.source == SOURCE_PROOF_RECORD


def test_a_newer_failed_replay_supersedes_an_older_success(tmp_path: Path) -> None:
    """A record is never edited, so a correction is a NEW record and the newest wins.

    The dangerous shape, and the one measured against the candidate: an older
    `host_verified` success with a newer `host_not_reproduced` on the same build and
    assertion reported SATISFIED, citing the superseded success. That closes an
    obligation on proof its own publisher has since retracted.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    bodies = (
        _record_body(verdict="host_recorded", identity=_CAPTURE_IDENTITY, minute="00"),
        _record_body(verdict="host_verified", identity=_REPLAY_IDENTITY, minute="01"),
        _record_body(
            verdict="host_not_reproduced",
            identity=_REPLAY_IDENTITY,
            minute="02",
            reproduced="no",
        ),
    )
    observation = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_runner(bodies=bodies, containment="identical"),
        now=_NOW,
    )
    assert observation.status == OBSERVATION_UNSATISFIED
    # The superseded success must not be cited as the evidence of anything.
    assert "issuecomment-2" not in observation.evidence


def test_a_replay_naming_a_non_containing_build_is_not_satisfied(tmp_path: Path) -> None:
    """A replay of a build that does not carry the requested one proves nothing here.

    `behind` is an OBSERVED answer — the forge compared and said no — so this is an
    unmet target, which is what separates it from the unreadable case below.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    observation = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_runner(bodies=_capture_and_replay(), containment="behind"),
        now=_NOW,
    )
    assert observation.status == OBSERVATION_UNSATISFIED


def test_an_unreadable_containment_comparison_is_unobservable(tmp_path: Path) -> None:
    """An unmade measurement is NOT an unmet proof, and the two must not collapse.

    This is the pair the finding asks to be kept apart. The record may well be
    perfectly good evidence; the reader could not establish whether its build
    carries the requested one, so the obligation is OUTSTANDING rather than refuted.
    Reporting `unsatisfied` here would publish a confident negative the reader never
    earned, and would make blinding the comparison the cheapest route to a verdict.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    observation = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_runner(bodies=_capture_and_replay(), containment_exit=1),
        now=_NOW,
    )
    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert observation.source == SOURCE_PROOF_RECORD
    assert observation.evidence == ""


def test_a_factory_record_from_another_dispatch_is_not_evidence(tmp_path: Path) -> None:
    """The FACTORY leg's attribution half, which the host leg's independence mirrors.

    `_dispatcher_proof_evidence` states the rule outright — "a record from another
    dispatch describes another tree" — and makes an unidentifiable dispatch fatal
    to attribution rather than a reason to fall back on the newest verified record
    whoever published it. This read admitted ANY `verified` record on the pull
    request, so a record belonging to a different dispatch satisfied the result.

    The subject's own proof pointer names the run that evidenced its merge, which
    is the attribution anchor this reader has. The positive control is the SAME
    record published by that run, so the refusal cannot be a reader that rejects
    every factory record.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    unrelated = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_runner(bodies=(_record_body(identity="run 01M4OTHERRUN"),)),
        now=_NOW,
    )
    assert unrelated.status == OBSERVATION_UNSATISFIED
    attributed = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_runner(bodies=(_record_body(identity="run 01M4PROOF"),)),
        now=_NOW,
    )
    assert attributed.status == OBSERVATION_SATISFIED


def test_an_unreadable_containment_is_unobservable_on_the_factory_leg_too(
    tmp_path: Path,
) -> None:
    """The unreadable/unmet distinction must hold on BOTH legs, not just the host one.

    The host leg answers `unobservable` when a replay's containment could not be
    read. The factory leg skipped such a record silently, and with no host record
    to carry a refusal the reading fell through to `unsatisfied` — a confident
    negative about a build nobody compared, which is the clause's forbidden
    direction and the exact asymmetry a one-leg fix leaves behind.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    observation = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_runner(bodies=(_record_body(),), containment_exit=1),
        now=_NOW,
    )
    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert observation.source == SOURCE_PROOF_RECORD
    assert observation.evidence == ""


def test_a_build_excluding_the_subjects_recorded_merge_is_not_evidence(
    tmp_path: Path,
) -> None:
    """The host-leg rule names a build "containing the merged change", not any build.

    Validating only that the record's build covers the REQUESTED build leaves a
    replay taken against a release predating the subject's merge as satisfaction —
    proof of a build that does not carry the work. So when the subject records a
    merge, the record's build must contain THAT too, and the comparison names it.

    The positive control is the same record against a build that does contain the
    merge, so this cannot be a reader that refuses every record once a merge is
    recorded.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description(), merge_sha=_MERGE_SHA)
    excluding = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_runner(bodies=_capture_and_replay(), statuses={_MERGE_SHA: "behind"}),
        now=_NOW,
    )
    assert excluding.status == OBSERVATION_UNSATISFIED
    containing = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_runner(bodies=_capture_and_replay()),
        now=_NOW,
    )
    assert containing.status == OBSERVATION_SATISFIED
    # The comparison must NAME the merge, which is what a status alone cannot show.
    runner = _runner(bodies=_capture_and_replay())
    _ = observe_verified_proof(repository=repository, target=_target(), runner=runner, now=_NOW)
    assert any(f"compare/{_MERGE_SHA}..." in one for one in runner.comparisons), runner.comparisons


def test_a_subject_recording_no_merge_has_no_merge_to_contain(tmp_path: Path) -> None:
    """The vacuous arm, and it is load-bearing rather than a convenience.

    "A build identity containing the merged change" presupposes a merged change. A
    subject whose work has not closed records none, and treating that absence as a
    failed containment would make the verified-proof result PERMANENTLY
    unobservable for every such subject — the instrument-blinded-by-its-own-guard
    failure, arriving from the fail-closed direction.

    So the requirement applies when a merge IS recorded and is vacuous when it is
    not; the requested build's own containment still applies either way, which the
    sibling cases above assert.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    runner = _runner(bodies=_capture_and_replay())
    observation = observe_verified_proof(
        repository=repository, target=_target(), runner=runner, now=_NOW
    )
    assert observation.status == OBSERVATION_SATISFIED
    assert all(f"compare/{_MERGE_SHA}..." not in one for one in runner.comparisons)


def test_an_unreadable_comparison_is_unobservable_once_a_merge_is_recorded_too(
    tmp_path: Path,
) -> None:
    """The composed reader's unreadable arm, which needs BOTH relations in play.

    The sibling unreadable cases record no merge, so only the requested-build
    relation is asked and the composition never runs. With a merge recorded the
    reader asks two questions, and EITHER being unreadable has to make the answer
    unreadable rather than `False` — a composition that returned `False` when one
    relation could not be read would convict a record on a measurement nobody
    took, which is the whole thing the unobservable status exists to prevent.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description(), merge_sha=_MERGE_SHA)
    observation = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_runner(bodies=_capture_and_replay(), containment_exit=1),
        now=_NOW,
    )
    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert observation.source == SOURCE_PROOF_RECORD


@pytest.mark.parametrize(
    "metadata",
    [
        pytest.param(None, id="metadata-absent"),
        pytest.param({}, id="metadata-carrying-no-audit"),
    ],
)
def test_audit_metadata_that_records_no_merge_leaves_the_requirement_vacuous(
    tmp_path: Path, metadata: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two sparse shapes, neither of which is a malformed record.

    A `bd` record is `omitempty`-sparse, so a metadata column that is absent
    altogether and one carrying no `audit` are both shapes the store genuinely
    produces. Each means the same thing — this subject records no merge — so each
    leaves the merge requirement vacuous rather than refusing the read. Treating
    either as malformed would make the result unobservable for a whole class of
    perfectly ordinary records, which is the sparseness trap this repository has
    already paid for once.

    THE SHAPES THAT ARE PRESENT AND OF THE WRONG TYPE ARE NOT HERE, and that is the
    point of the pair: sparseness OMITS a field, so a present value of another type
    is unreadable evidence rather than an absence.
    `test_plan_result_proof_subject.py` owns those cases and asserts them
    `unobservable`.
    """
    repository = _repo(tmp_path=tmp_path)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._plan_result_proof.result_store_config",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._plan_result_proof.make_beads_client",
        lambda **_kwargs: _AuditShapeClient(metadata=metadata),
    )
    runner = _runner(bodies=_capture_and_replay())
    observation = observe_verified_proof(
        repository=repository, target=_target(), runner=runner, now=_NOW
    )
    assert observation.status == OBSERVATION_SATISFIED
    assert all(f"compare/{_MERGE_SHA}..." not in one for one in runner.comparisons)


def test_a_comment_saying_verified_is_not_a_typed_record(tmp_path: Path) -> None:
    """The clause: the read validates record semantics rather than matching text.

    The comment is on the pull request and WAS read, so this is an unmet target
    rather than a failed observation — and the evidence says how many records the
    read found, which for a comment that is not a record at all is zero.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    observation = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_runner(bodies=("Everything is verified. Reproduced: yes.\n",)),
        now=_NOW,
    )
    assert observation is not None
    assert observation.status == OBSERVATION_UNSATISFIED
    assert observation.source == SOURCE_PROOF_RECORD
    assert observation.evidence == f"0 Proof of Done record(s) on pull request #{_PR_NUMBER}"


def test_a_non_verified_verdict_is_not_evidence(tmp_path: Path) -> None:
    """`captured` and `not_reproduced` are records, and neither is a verified proof."""
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    for verdict in ("captured", "not_reproduced"):
        observation = observe_verified_proof(
            repository=repository,
            target=_target(),
            runner=_runner(bodies=(_record_body(verdict=verdict),)),
            now=_NOW,
        )
        assert observation is not None, verdict
        assert observation.status == OBSERVATION_UNSATISFIED, verdict
        assert f"against build {_BUILD}" in observation.detail, verdict


def test_a_record_naming_another_build_or_no_build_is_not_evidence(tmp_path: Path) -> None:
    """A record whose build section is absent names no ref to compare against.

    The other-build leg answers `behind`, which is the forge OBSERVING that the
    record's build does not carry the requested one. That is what keeps it an unmet
    target rather than an unreadable comparison — the distinction the unobservable
    case above rests on.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    buildless = (
        "Proof of Done — verified — run 01M4PROOF — 2026-10-08T08:00:00Z\n"
        "\n"
        f"## Assertion 1 — {_ASSERTION}\n"
        "Reproduced: yes.\n"
    )
    for bodies in ((_record_body(build="v0.1.0"),), (buildless,)):
        observation = observe_verified_proof(
            repository=repository,
            target=_target(),
            runner=_runner(bodies=bodies, containment="behind"),
            now=_NOW,
        )
        assert observation is not None
        assert observation.status == OBSERVATION_UNSATISFIED
        assert f"against build {_BUILD}" in observation.detail


def test_a_newer_record_for_another_build_does_not_shadow_the_requested_one(
    tmp_path: Path,
) -> None:
    """The build filter runs BEFORE the newest-wins choice, not after it.

    Filtering afterwards would let a later replay of a different build hide an
    earlier record that genuinely covers the requested build, and the refusal
    would read as if no proof existed.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    observation = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_runner(bodies=(_record_body(), _record_body(build="v0.9.9"))),
        now=_NOW,
    )
    assert observation is not None
    assert observation.status == OBSERVATION_SATISFIED


def test_an_assertion_the_record_does_not_reproduce_is_not_in_scope(tmp_path: Path) -> None:
    """Unevidenced and not-reproduced are both outside the requested scope.

    The record lists one assertion; the first case asks about a second one it
    never mentions, and the second asks about the one it explicitly refused.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    unevidenced = observe_verified_proof(
        repository=repository,
        target=_target(assertions=(_ASSERTION, "An assertion nobody published.")),
        runner=_runner(bodies=(_record_body(),)),
        now=_NOW,
    )
    assert unevidenced is not None
    assert unevidenced.status == OBSERVATION_UNSATISFIED
    assert "is evidence for 1 of the 2 requested assertion(s)" in unevidenced.detail
    refused = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_runner(bodies=(_record_body(reproduced="no"),)),
        now=_NOW,
    )
    assert refused is not None
    assert refused.status == OBSERVATION_UNSATISFIED
    assert "is evidence for 1 of the 1 requested assertion(s)" in refused.detail


def test_a_subject_naming_no_pull_request_is_unobservable_per_failing_source(
    tmp_path: Path,
) -> None:
    """Four ways the subject itself fails to name a pull request, each with a source.

    The pointer is the only thing that says WHICH pull request's records belong to
    this subject, so each of these leaves the typed read with nothing to aim at.
    The SOURCES differ, and that is the reason the refusal is a value rather than a
    bare absence: an unresolvable connection, an unreadable record and a sparse
    record are LEDGER failures whose remedy is in the named repository, while a
    subject carrying no proof pointer is a PROOF RECORD that was never published.
    Collapsing them would point every retry at whichever one the reader guessed.
    """
    pointerless = _repo(tmp_path=tmp_path)
    _seed_subject(repository=pointerless, description="## Definition of Done\n\n- Something.\n")
    no_pointer = observe_verified_proof(
        repository=pointerless, target=_target(), runner=_runner(bodies=()), now=_NOW
    )
    assert no_pointer.status == OBSERVATION_UNOBSERVABLE
    assert no_pointer.source == SOURCE_PROOF_RECORD
    assert "carries no Proof of Done pointer" in no_pointer.detail
    absent_subject = observe_verified_proof(
        repository=pointerless,
        target=VerifiedProofTarget(
            subject_id="bd-ib-never-filed", build=_BUILD, assertions=(_ASSERTION,)
        ),
        runner=_runner(bodies=()),
        now=_NOW,
    )
    assert absent_subject.status == OBSERVATION_UNOBSERVABLE
    assert absent_subject.source == SOURCE_LEDGER
    assert "BeadsMappingError" in absent_subject.detail


def test_an_unreadable_target_configuration_is_unobservable(tmp_path: Path) -> None:
    repository = _repo(tmp_path=tmp_path, prefix=None)
    observation = observe_verified_proof(
        repository=repository, target=_target(), runner=_runner(bodies=()), now=_NOW
    )
    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert observation.source == SOURCE_LEDGER
    assert "did not resolve a tenant connection" in observation.detail


def test_a_record_carrying_no_description_is_unobservable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sparse record names no pointer, which is not the same as naming none."""
    repository = _repo(tmp_path=tmp_path)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._plan_result_proof.make_beads_client",
        lambda **_kwargs: _DescriptionlessClient(),
    )
    observation = observe_verified_proof(
        repository=repository, target=_target(), runner=_runner(bodies=()), now=_NOW
    )
    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert observation.source == SOURCE_LEDGER
    assert "carries no description" in observation.detail


def test_an_unreadable_pull_request_is_unobservable(tmp_path: Path) -> None:
    """A failed comments read is evidence of nothing, not of an absent record.

    The contrast with the unsatisfied arm above is the whole point: there, zero
    records were READ and that is a negative; here the read failed, so whether a
    verified proof was published is unknown.
    """
    repository = _repo(tmp_path=tmp_path)
    _seed_subject(repository=repository, description=_pointed_description())
    observation = observe_verified_proof(
        repository=repository, target=_target(), runner=_runner(exit_code=4), now=_NOW
    )
    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert observation.source == SOURCE_PROOF_RECORD
    assert observation.evidence == ""
