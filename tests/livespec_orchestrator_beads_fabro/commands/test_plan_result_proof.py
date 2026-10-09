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


@dataclass(kw_only=True)
class _Runner:
    result: CommandResult
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
        return self.result


class _DescriptionlessClient:
    """A tenant whose record omits `description`, the way a sparse record can."""

    def show_issue(self, *, issue_id: str) -> BeadsRecord:
        return {"id": issue_id}


def _repo(*, tmp_path: Path, prefix: str | None = "bd-ib") -> ResultRepository:
    clone = tmp_path / "repo"
    clone.mkdir()
    connection: dict[str, object] = {} if prefix is None else {"prefix": prefix}
    _ = (clone / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"connection": connection}}),
        encoding="utf-8",
    )
    return ResultRepository(name="repo", clone=clone)


def _seed_subject(*, repository: ResultRepository, description: str) -> None:
    client = make_beads_client(config=store_config(repo=repository.clone))
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_SUBJECT_ID,
            issue_type="feature",
            title=_SUBJECT_ID,
            description=description,
            assignee=None,
            created_at="2026-10-08T00:00:00Z",
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
) -> str:
    return (
        f"Proof of Done — {verdict} — run 01M4PROOF — 2026-10-08T08:00:00Z\n"
        "\n"
        f"- {label}: {build}\n"
        "\n"
        f"## Assertion 1 — {_ASSERTION}\n"
        f"Reproduced: {reproduced}.\n"
    )


def _runner(
    *, bodies: tuple[str, ...] = (), exit_code: int = 0, stdout: str | None = None
) -> _Runner:
    payload = (
        stdout
        if stdout is not None
        else json.dumps({"comments": [{"body": one, "url": _RECORD_URL} for one in bodies]})
    )
    return _Runner(result=CommandResult(exit_code=exit_code, stdout=payload, stderr=""))


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
        assert f"names build {_BUILD}" in observation.detail, verdict


def test_a_record_naming_another_build_or_no_build_is_not_evidence(tmp_path: Path) -> None:
    """A record whose build section is absent names no ref to compare against."""
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
            repository=repository, target=_target(), runner=_runner(bodies=bodies), now=_NOW
        )
        assert observation is not None
        assert observation.status == OBSERVATION_UNSATISFIED
        assert f"names build {_BUILD}" in observation.detail


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
    assert "does not list 1 of the 2 requested assertion(s)" in unevidenced.detail
    refused = observe_verified_proof(
        repository=repository,
        target=_target(),
        runner=_runner(bodies=(_record_body(reproduced="no"),)),
        now=_NOW,
    )
    assert refused is not None
    assert refused.status == OBSERVATION_UNSATISFIED
    assert "does not list 1 of the 1 requested assertion(s)" in refused.detail


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
