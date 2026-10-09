"""The subject-record read behind the verified-proof adapter's merge requirement.

`test_plan_result_proof.py` covers the adapter's grading. This module covers the
one question that sits before it: what the subject's own ledger record yields
about the merge its proof must contain, when that record is sparse.

WHY THIS IS A SEPARATE MODULE. Its sibling's cases arrived as one Red whose test
bytes are fixed across the Red->Green pair, and these shapes were found by a
coverage measurement after that Red was authored. The repository protocol admits
additional test files alongside the implementation at the Green amend, which is
the honest route: the alternative is rewriting a protected Red, and a rewritten
Red cannot be re-run against the commit that first made it pass.

WHY THE SHAPES ARE NOT MALFORMED RECORDS. `bd` records are `omitempty`-sparse and
their metadata is a free-form JSON column, so an audit object that carries no
`merge_sha` — or carries a blank one — is an ordinary record for a subject whose
work has not closed. It means exactly what absent metadata means: no merge is
recorded, so the host-leg requirement that a build "contain the merged change"
has nothing to contain and is vacuous. Reading any of these as a fault would make
the verified-proof result unobservable for a whole class of normal records.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    RELEASE_TAG_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer import (
    ProofPointer,
    description_with_pointer,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_proof import observe_verified_proof
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import ResultRepository
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import VerifiedProofTarget

_SUBJECT_ID = "bd-ib-proof"
_PR_NUMBER = 146
_BUILD = "v0.170.0"
_ASSERTION = "The reader validates the typed record rather than matching text."
_RECORD_URL = f"https://example.test/owner/repo/pull/{_PR_NUMBER}#issuecomment-1"
_NOW = "2026-10-08T12:00:00Z"
_COMPARE_KEY = "/compare/"
_CAPTURE_IDENTITY = "session 1e14094a-0000-4000-8000-000000000001"
_REPLAY_IDENTITY = "session b1e14094-0000-4000-8000-000000000002"


@dataclass(kw_only=True)
class _Runner:
    """Answers the comments read and the build comparison apart, recording both."""

    bodies: tuple[str, ...]
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
        del cwd, timeout_seconds, env, stdin
        self.calls.append(tuple(argv))
        if any(_COMPARE_KEY in token for token in argv):
            return CommandResult(exit_code=0, stdout="identical\n", stderr="")
        payload = {
            "comments": [
                {"body": one, "url": f"{_RECORD_URL}{index}"}
                for index, one in enumerate(self.bodies, start=1)
            ]
        }
        return CommandResult(exit_code=0, stdout=json.dumps(payload), stderr="")

    @property
    def comparisons(self) -> tuple[str, ...]:
        """Every comparison endpoint asked, so a case can assert which refs it named."""
        return tuple(argv[2] for argv in self.calls if any(_COMPARE_KEY in token for token in argv))


@dataclass(kw_only=True)
class _SubjectClient:
    """A read-only tenant returning one record with the audit metadata supplied.

    A stub rather than the in-memory client, because `IssueDraft.metadata` is typed
    as a mapping and these cases need the shapes a free-form JSON column can hold
    that the public write verb cannot express.
    """

    audit: object

    def show_issue(self, *, issue_id: str) -> BeadsRecord:
        return cast(
            "BeadsRecord",
            {
                "id": issue_id,
                "description": _description(),
                "metadata": {"audit": self.audit},
            },
        )


def _description() -> str:
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


def _body(*, verdict: str, identity: str, minute: str) -> str:
    return (
        f"Proof of Done — {verdict} — {identity} — 2026-10-08T08:{minute}:00Z\n"
        "\n"
        f"- {RELEASE_TAG_LABEL}: {_BUILD}\n"
        "\n"
        f"## Assertion 1 — {_ASSERTION}\n"
        "Reproduced: yes.\n"
    )


def _repo(*, tmp_path: Path) -> ResultRepository:
    clone = tmp_path / "repo"
    clone.mkdir()
    _ = (clone / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}),
        encoding="utf-8",
    )
    return ResultRepository(name="repo", clone=clone)


@pytest.mark.parametrize(
    "audit",
    [
        pytest.param({}, id="audit-object-carrying-no-merge"),
        pytest.param({"merge_sha": ""}, id="audit-carrying-a-blank-merge"),
        pytest.param({"merge_sha": "   "}, id="audit-carrying-a-whitespace-merge"),
        pytest.param({"merge_sha": 7}, id="audit-carrying-a-non-string-merge"),
    ],
)
def test_an_audit_object_recording_no_merge_leaves_the_requirement_vacuous(
    tmp_path: Path, audit: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Four audit objects that exist and record no merge, none of them a fault.

    Each means what absent metadata means — this subject records no merge — so the
    merge-containment requirement is vacuous and the requested build's own
    containment decides the reading. The assertion is SATISFIED rather than merely
    "not unobservable", because the failure this guards against is the reader
    treating a sparse audit as an unreadable measurement and parking the
    obligation for ever.

    The comparison list is asserted to name no second base, which is what
    distinguishes "the requirement was vacuous" from "the requirement was asked
    and happened to pass".
    """
    repository = _repo(tmp_path=tmp_path)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._plan_result_proof.result_store_config",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._plan_result_proof.make_beads_client",
        lambda **_kwargs: _SubjectClient(audit=audit),
    )
    runner = _Runner(
        bodies=(
            _body(verdict="host_recorded", identity=_CAPTURE_IDENTITY, minute="00"),
            _body(verdict="host_verified", identity=_REPLAY_IDENTITY, minute="01"),
        )
    )
    observation = observe_verified_proof(
        repository=repository,
        target=VerifiedProofTarget(subject_id=_SUBJECT_ID, build=_BUILD, assertions=(_ASSERTION,)),
        runner=runner,
        now=_NOW,
    )
    assert observation.status == OBSERVATION_SATISFIED
    assert runner.comparisons == (f"repos/{{owner}}/{{repo}}/compare/{_BUILD}...{_BUILD}",)
