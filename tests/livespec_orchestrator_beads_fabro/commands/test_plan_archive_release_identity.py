"""The archive gate's release rule, judged against each record's own repository.

Binds the plan-record clause of `SPECIFICATION/contracts.md` (v148) and Scenario
135: "The release rule is judged against the RELEASE REPOSITORY of each record ...
Every repository's release tags — the governed repository's included — MUST be
read by an authenticated read of its remote on the forge that hosts the governed
repository, and MUST NOT be read from any local clone or worktree."

WHY THIS IS DRIVEN THROUGH `archive_thread` AND NOT THE PURE LEG. The pure
decision is exercised by `test_plan_proof_leg`, which hands it a reader directly,
and the ladder by `test_plan_release_reader`. What neither can show is that the
GATE reads each record's own release repository: a build that kept judging every
record against the governed repository would satisfy every case over there and
look identical from the leg's side.

THE FIXTURE IS NOT A GIT REPOSITORY AND HOLDS NO CLONE OF THE RELEASE REPOSITORY,
which is the point rather than an economy. The retired rule read `git tag --list`
in the governed checkout, so it could only ever answer about a repository this host
had cloned — and it answered "no tags", i.e. "no release applies", for every
repository it could not reach. Here the only thing that can answer is the forge, so
a verdict earned in this fixture is a verdict earned with no local clone at all.
Every case asserts the whole command set the archive issued: all `gh`, all run from
the governed checkout.

EVERY CASE CARRIES THE ARCHIVE THAT SUCCEEDS. A gate that rejected every record
would satisfy every refusal here on its own, and would make the ratified remedy —
republish naming the release exercised — unreachable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HOST_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    BuildIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    RecordAssertion,
    render_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
)
from livespec_orchestrator_beads_fabro.commands._plan_release_forge import (
    governed_repository_argv,
    repository_tags_argv,
)
from livespec_orchestrator_beads_fabro.commands.plan import (
    PlanArchiveRefusedError,
    archive_thread,
    create_thread,
    record_completeness_review_evidence,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_SLUG = "release-identity-thread"
_ASSERTION = "The released build runs in a real operator session."
# The archiving session's own environment, supplied explicitly so each archive
# grades against a known identity rather than against whatever session happens
# to be running pytest.
_ARCHIVING_SESSION_ENV = {"CLAUDE_CODE_SESSION_ID": "archiving-session"}
# The reviewing session's own environment. The evidence record's reviewer
# identity is COMPUTED from it — there is no field a caller can name one in —
# so a reviewer distinct from the archiver is expressed as a distinct session.
_REVIEWING_SESSION_ENV = {"CLAUDE_CODE_SESSION_ID": "reviewing-session"}

_GOVERNED = "thewoolleyman/livespec"
_SIBLING = "thewoolleyman/livespec-dev-tooling"
# The live case this rule exists for: the livespec plan k3s-on-gmktec-for-vps-usage
# shipped as livespec-dev-tooling releases, and the governed repository carries
# neither tag.
_SIBLING_TAG = "v1.96.1"
_GOVERNED_TAG = "v0.167.0"
_BUILD = f"livespec-dev-tooling {_SIBLING_TAG}"


@dataclass(kw_only=True)
class _Forge:
    """A stub forge that answers per endpoint, as `gh` does."""

    existing: frozenset[str] = frozenset({_GOVERNED, _SIBLING})
    tags: dict[str, frozenset[str]] = field(default_factory=dict)
    unreadable_tags: frozenset[str] = frozenset()
    calls: list[tuple[str, ...]] = field(default_factory=list)
    cwds: list[Path] = field(default_factory=list)

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
        self.calls.append(tuple(argv))
        self.cwds.append(cwd)
        if argv == governed_repository_argv():
            return CommandResult(exit_code=0, stdout=_GOVERNED, stderr="")
        endpoint = next(one for one in argv if one.startswith("repos/"))
        if "--include" in argv:
            present = endpoint.removeprefix("repos/") in self.existing
            return CommandResult(
                exit_code=0 if present else 1,
                stdout=f"HTTP/2.0 {'200 OK' if present else '404 Not Found'}\r\n",
                stderr="" if present else "gh: HTTP 404",
            )
        repository = endpoint.removeprefix("repos/").removesuffix("/tags")
        if repository in self.unreadable_tags:
            return CommandResult(exit_code=1, stdout="", stderr="gh: Bad credentials (HTTP 401)")
        return CommandResult(
            exit_code=0,
            stdout="\n".join(sorted(self.tags.get(repository, frozenset()))),
            stderr="",
        )


def _forge(**overrides: object) -> _Forge:
    defaults: dict[str, object] = {
        "tags": {_GOVERNED: frozenset({_GOVERNED_TAG}), _SIBLING: frozenset({_SIBLING_TAG})}
    }
    return _Forge(**{**defaults, **overrides})  # pyright: ignore[reportArgumentType]


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


def _record(
    *, epic_id: str, verdict: str, identity: str, release: str | None, installed: str | None
) -> None:
    _fake().add_comment(
        issue_id=epic_id,
        body=render_proof_record(
            title=PLAN_PROOF_RECORD_TITLE,
            verdict=verdict,
            identity=f"session {identity}",
            timestamp="2026-10-16T01:00:00Z",
            build=BuildIdentity(release_tag=release, installed_build=installed, commit="c0ffee1"),
            assertions=(
                RecordAssertion(
                    text=_ASSERTION,
                    proof_mode=PROOF_MODE_HOST_CAPTURED,
                    governing_scenario=None,
                    steps=("Install the released build.", "Run it in a real session."),
                    proof="$ delivered --version\n1.96.1",
                    reproduced=None if verdict == VERDICT_CAPTURED else True,
                ),
            ),
        ),
    )


def _plan_ready_to_archive(*, repo: Path) -> str:
    """A plan whose child and completeness legs pass, so only proof is left."""
    repo.mkdir(parents=True, exist_ok=True)
    created = create_thread(
        project_root=repo,
        config=_config(),
        slug=_SLUG,
        title="Release identity thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-10-16T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the released build has been run in a real session.",
            assertions=(_ASSERTION,),
        ),
    )
    record_completeness_review_evidence(
        config=_config(),
        epic_id=created["epic_id"],
        evidence_id="review-evidence-1",
        env=_REVIEWING_SESSION_ENV,
        reviewed_child_ids=(),
        separate_reviewer=True,
        attests_complete_requirement_coverage=True,
        body="Every requirement carrier under the plan is covered.",
        now="2026-10-16T00:30:00Z",
    )
    return created["epic_id"]


def _seeded(*, repo: Path, release: str | None, installed: str | None) -> str:
    epic_id = _plan_ready_to_archive(repo=repo)
    for verdict, identity in ((VERDICT_CAPTURED, "capturing"), (VERDICT_VERIFIED, "replaying")):
        _record(
            epic_id=epic_id,
            verdict=verdict,
            identity=identity,
            release=release,
            installed=installed,
        )
    return epic_id


def _archive(*, repo: Path, epic_id: str, forge: _Forge) -> dict[str, str]:
    return archive_thread(
        env=_ARCHIVING_SESSION_ENV,
        runner=forge,
        project_root=repo,
        config=_config(),
        slug=_SLUG,
        epic_id=epic_id,
        completeness_review_comment_id="review-evidence-1",
    )


def _no_local_clone_was_read(*, forge: _Forge, repo: Path) -> bool:
    """Whether every read the archive took was a forge read from the governed checkout."""
    return all(call[0] == "gh" for call in forge.calls) and set(forge.cwds) == {repo}


def test_a_record_naming_a_sibling_release_the_forge_carries_is_evidence(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    repo = tmp_path / "governed"
    forge = _forge()
    epic_id = _seeded(repo=repo, release=_SIBLING_TAG, installed=_BUILD)

    result = _archive(repo=repo, epic_id=epic_id, forge=forge)

    assert result["archive_path"] == f"plan/archive/{_SLUG}"
    assert _fake().show_issue(issue_id=epic_id)["status"] == "closed"
    # The sibling's tags were read, and the governed repository's were not: the
    # record is judged against the repository its build identity names.
    assert tuple(repository_tags_argv(repository=_SIBLING)) in forge.calls
    assert tuple(repository_tags_argv(repository=_GOVERNED)) not in forge.calls
    # No clone of `livespec-dev-tooling` exists anywhere under this fixture, and
    # none was consulted.
    assert not (tmp_path / "livespec-dev-tooling").exists()
    assert _no_local_clone_was_read(forge=forge, repo=repo)


def test_a_record_naming_a_tag_its_release_repository_lacks_is_refused_naming_both(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    repo = tmp_path / "governed"
    forge = _forge()
    epic_id = _seeded(repo=repo, release="v9.9.9", installed=_BUILD)

    with pytest.raises(PlanArchiveRefusedError) as refused:
        _ = _archive(repo=repo, epic_id=epic_id, forge=forge)

    message = str(refused.value)
    assert _ASSERTION in message
    # Both halves the clause requires: the missing release identity, and the
    # release repository the gate judged. Naming only the tag would leave an
    # operator unable to tell which repository was asked.
    assert "v9.9.9" in message
    assert _SIBLING in message
    assert (repo / "plan" / _SLUG).is_dir()
    assert _fake().show_issue(issue_id=epic_id)["status"] != "closed"
    assert _no_local_clone_was_read(forge=forge, repo=repo)


def test_a_release_repository_the_forge_will_not_answer_for_is_refused_not_waved_through(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    repo = tmp_path / "governed"
    forge = _forge(unreadable_tags=frozenset({_SIBLING}))
    epic_id = _seeded(repo=repo, release=_SIBLING_TAG, installed=_BUILD)

    with pytest.raises(PlanArchiveRefusedError) as refused:
        _ = _archive(repo=repo, epic_id=epic_id, forge=forge)

    message = str(refused.value)
    # The reversed default: an unreadable repository is NOT a repository carrying
    # no release tag. The refusal names the repository it tried to read and the
    # failure, which is what tells a credential problem from a wrong tag.
    assert _SIBLING in message
    assert "Bad credentials" in message
    assert _fake().show_issue(issue_id=epic_id)["status"] != "closed"


def test_an_explicit_repository_the_forge_denies_is_refused_without_judging_the_governed_one(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    repo = tmp_path / "governed"
    forge = _forge()
    epic_id = _seeded(
        repo=repo, release=_GOVERNED_TAG, installed=f"thewoolleyman/absent-repo {_GOVERNED_TAG}"
    )

    with pytest.raises(PlanArchiveRefusedError) as refused:
        _ = _archive(repo=repo, epic_id=epic_id, forge=forge)

    assert "thewoolleyman/absent-repo" in str(refused.value)
    # THE LOAD-BEARING HALF: the record names a tag the GOVERNED repository does
    # carry, so a gate that fell back would have ADMITTED it. The governed
    # repository's tags were never read, so it was not judged in its place.
    assert tuple(repository_tags_argv(repository=_GOVERNED)) not in forge.calls
    assert _fake().show_issue(issue_id=epic_id)["status"] != "closed"


def test_a_record_naming_no_installed_build_is_judged_against_the_governed_repository(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    repo = tmp_path / "governed"
    forge = _forge()
    epic_id = _seeded(repo=repo, release=None, installed=None)

    with pytest.raises(PlanArchiveRefusedError) as refused:
        _ = _archive(repo=repo, epic_id=epic_id, forge=forge)

    message = str(refused.value)
    # The governed repository carries a release tag, read from ITS forge remote
    # rather than from this checkout — which is not a git repository at all.
    assert _GOVERNED in message
    assert tuple(repository_tags_argv(repository=_GOVERNED)) in forge.calls
    assert not (repo / ".git").exists()
    assert _no_local_clone_was_read(forge=forge, repo=repo)


def test_a_bare_word_the_forge_calls_no_repository_falls_back_to_the_governed_one(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    repo = tmp_path / "governed"
    forge = _forge()
    # A version string is a bare `<repository>` by the clause's grammar, so the
    # forge is ASKED about it; it answers 404, and the governed repository stands.
    epic_id = _seeded(repo=repo, release=_GOVERNED_TAG, installed=f"{_GOVERNED_TAG} (local)")

    result = _archive(repo=repo, epic_id=epic_id, forge=forge)

    assert result["archive_path"] == f"plan/archive/{_SLUG}"
    assert tuple(repository_tags_argv(repository=_GOVERNED)) in forge.calls


def test_a_governed_repository_the_forge_reports_no_tag_for_waives_the_release_rule(
    tmp_path: Path,
) -> None:
    # The control the clause attaches the whole rule to: where the release
    # repository carries no release tag, no release applies and a record stating
    # `release: none` is evidence.
    reset_fake_singleton()
    repo = tmp_path / "governed"
    forge = _forge(tags={})
    epic_id = _seeded(repo=repo, release=None, installed=None)

    result = _archive(repo=repo, epic_id=epic_id, forge=forge)

    assert result["archive_path"] == f"plan/archive/{_SLUG}"
    assert _fake().show_issue(issue_id=epic_id)["status"] == "closed"
