"""The release-repository resolution ladder, across every arm the clause names.

Covers `_plan_release_reader`. The ladder is driven through a stub forge that
answers per endpoint, so each case is one record body resolved against one forge
state — which is what makes the arms the v148 plan-record clause separates
reachable at all: a bare name the forge reports, a bare name it does not, an
explicit name it does not, an unreadable tag read, and an unreadable governed
identity.

TWO ARMS ARE OPPOSITE CONSEQUENCES OF ONE FORGE ANSWER, and they are the pair that
gives each other meaning. A `404` for a BARE word routes to the governed
repository; a `404` for an EXPLICIT `<owner>/<repository>` rejects and must not be
judged against the governed repository. A ladder that collapsed them would satisfy
either case alone — so the explicit case asserts that the governed repository's
tags were NEVER READ, which is a claim about a read that did not happen and is the
only thing that separates "rejected" from "rejected and then quietly fell back".

NO READ MAY CONSULT A LOCAL CLONE. Every case asserts the whole command set the
ladder issued, and the governed checkout is the only working directory any of them
runs in — so a host holding no clone of the release repository reaches the same
verdict. A ladder that shelled out to `git` in a sibling path would fail that
assertion rather than merely answer differently on a host that happens to have one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
)
from livespec_orchestrator_beads_fabro.commands._plan_release_forge import (
    governed_repository_argv,
    repository_probe_argv,
    repository_tags_argv,
)
from livespec_orchestrator_beads_fabro.commands._plan_release_reader import (
    forge_release_reader,
)
from livespec_orchestrator_beads_fabro.commands._plan_release_repository import (
    ReleaseTags,
    UnreadableRelease,
)

_ROOT = Path("/governed/livespec")
_GOVERNED = "thewoolleyman/livespec"
_SIBLING = "thewoolleyman/livespec-dev-tooling"
_GOVERNED_TAGS = frozenset({"v0.1.0"})
_SIBLING_TAGS = frozenset({"v1.95.12", "v1.96.1"})
_ASSERTION = "The released build runs in a real operator session."


@dataclass(kw_only=True)
class _Forge:
    """A stub forge that answers per endpoint, as `gh` does."""

    identity: str = _GOVERNED
    identity_exit: int = 0
    existing: frozenset[str] = frozenset({_GOVERNED, _SIBLING})
    tags: dict[str, frozenset[str]] = field(default_factory=dict)
    unreadable_tags: frozenset[str] = frozenset()
    unprobeable: frozenset[str] = frozenset()
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
            return CommandResult(
                exit_code=self.identity_exit,
                stdout=self.identity,
                stderr="no git remotes found",
            )
        endpoint = next(one for one in argv if one.startswith("repos/"))
        if "--include" in argv:
            return self._probe(repository=endpoint.removeprefix("repos/"))
        return self._tags(repository=endpoint.removeprefix("repos/").removesuffix("/tags"))

    def _probe(self, *, repository: str) -> CommandResult:
        if repository in self.unprobeable:
            return CommandResult(exit_code=1, stdout="", stderr="dial tcp: no such host")
        present = repository in self.existing
        return CommandResult(
            exit_code=0 if present else 1,
            stdout=f"HTTP/2.0 {'200 OK' if present else '404 Not Found'}\r\n",
            stderr="" if present else "gh: HTTP 404",
        )

    def _tags(self, *, repository: str) -> CommandResult:
        if repository in self.unreadable_tags:
            return CommandResult(exit_code=1, stdout="", stderr="gh: Bad credentials (HTTP 401)")
        return CommandResult(
            exit_code=0,
            stdout="\n".join(sorted(self.tags.get(repository, frozenset()))),
            stderr="",
        )


def _forge(**overrides: object) -> _Forge:
    defaults: dict[str, object] = {"tags": {_GOVERNED: _GOVERNED_TAGS, _SIBLING: _SIBLING_TAGS}}
    return _Forge(**{**defaults, **overrides})  # pyright: ignore[reportArgumentType]


def _body(*, installed_build: str | None, release: str | None = "v1.96.1") -> str:
    return render_proof_record(
        title=PLAN_PROOF_RECORD_TITLE,
        verdict=VERDICT_CAPTURED,
        identity="session capturing",
        timestamp="2026-10-16T00:00:00Z",
        build=BuildIdentity(release_tag=release, installed_build=installed_build, commit="c0ffee1"),
        assertions=(
            RecordAssertion(
                text=_ASSERTION,
                proof_mode=PROOF_MODE_HOST_CAPTURED,
                governing_scenario=None,
                steps=("Install the released build.",),
                proof="$ delivered --version\n1.96.1",
                reproduced=None,
            ),
        ),
    )


def _reading(*, forge: _Forge, installed_build: str | None) -> object:
    reader = forge_release_reader(project_root=_ROOT, runner=forge)
    return reader.reading(body=_body(installed_build=installed_build))


def test_a_bare_name_the_forge_reports_is_judged_against_that_repositorys_tags() -> None:
    # The live case: a livespec plan whose honest records name
    # `livespec-dev-tooling` releases, resolved under the governed owner.
    forge = _forge()

    reading = _reading(forge=forge, installed_build="livespec-dev-tooling v1.96.1")

    assert reading == ReleaseTags(repository=_SIBLING, tags=_SIBLING_TAGS)
    # Three reads and no more: the governed identity, the existence probe, the
    # sibling's tags. The governed repository's own tags are NOT read, because
    # the sibling is what this record is judged against.
    assert forge.calls == [
        tuple(governed_repository_argv()),
        tuple(repository_probe_argv(repository=_SIBLING)),
        tuple(repository_tags_argv(repository=_SIBLING)),
    ]
    # Every read runs from the governed checkout. No clone of the release
    # repository is consulted, needed, or even named as a path.
    assert set(forge.cwds) == {_ROOT}


def test_a_bare_name_the_forge_reports_is_no_repository_falls_back_to_the_governed_one() -> None:
    forge = _forge()

    reading = _reading(forge=forge, installed_build="v1.96.1 (built from source)")

    assert reading == ReleaseTags(repository=_GOVERNED, tags=_GOVERNED_TAGS)
    # The probe DID run and answered 404: that answer is what elected the
    # governed repository, rather than the word's shape.
    assert tuple(repository_probe_argv(repository="thewoolleyman/v1.96.1")) in forge.calls


def test_a_record_naming_no_installed_build_identifier_is_judged_against_the_governed_one() -> None:
    forge = _forge()

    reading = _reading(forge=forge, installed_build=None)

    assert reading == ReleaseTags(repository=_GOVERNED, tags=_GOVERNED_TAGS)
    # No probe at all: there is no name to ask the forge about, so the governed
    # repository is reached without a round trip that could only fail.
    assert forge.calls == [
        tuple(governed_repository_argv()),
        tuple(repository_tags_argv(repository=_GOVERNED)),
    ]


def test_an_explicit_repository_the_forge_denies_is_rejected_and_never_falls_back() -> None:
    forge = _forge(existing=frozenset({_GOVERNED}))

    reading = _reading(forge=forge, installed_build="thewoolleyman/livespec-dev-tooling v1.96.1")

    assert isinstance(reading, UnreadableRelease)
    assert reading.repository == _SIBLING
    assert _SIBLING in reading.failure
    # THE LOAD-BEARING HALF: the governed repository's tags were never read, so
    # the record was not judged against it in the sibling's place.
    assert tuple(repository_tags_argv(repository=_GOVERNED)) not in forge.calls


def test_an_explicit_repository_the_forge_reports_is_judged_against_its_own_tags() -> None:
    # The control for the case above: a ladder that rejected every explicit name
    # would satisfy it on its own.
    reading = _reading(forge=_forge(), installed_build="thewoolleyman/livespec-dev-tooling v1.96.1")

    assert reading == ReleaseTags(repository=_SIBLING, tags=_SIBLING_TAGS)


def test_a_tag_read_the_forge_refuses_is_unreadable_and_never_an_empty_tag_set() -> None:
    forge = _forge(unreadable_tags=frozenset({_SIBLING}))

    reading = _reading(forge=forge, installed_build="livespec-dev-tooling v1.96.1")

    assert isinstance(reading, UnreadableRelease)
    assert reading.repository == _SIBLING
    assert "Bad credentials" in reading.failure


def test_a_probe_the_forge_cannot_answer_is_unreadable_and_never_a_fallback() -> None:
    forge = _forge(unprobeable=frozenset({_SIBLING}))

    reading = _reading(forge=forge, installed_build="livespec-dev-tooling v1.96.1")

    assert isinstance(reading, UnreadableRelease)
    assert reading.repository == _SIBLING
    assert "no such host" in reading.failure
    # An unobservable probe must not be read as "no such repository", which is
    # the arm that routes to the governed repository.
    assert tuple(repository_tags_argv(repository=_GOVERNED)) not in forge.calls


def test_a_governed_identity_the_forge_cannot_answer_rejects_before_any_other_read() -> None:
    forge = _forge(identity_exit=1)

    reading = _reading(forge=forge, installed_build="livespec-dev-tooling v1.96.1")

    assert isinstance(reading, UnreadableRelease)
    # With no identity to name, the checkout the gate tried to read it from is
    # what the refusal names.
    assert reading.repository == _ROOT.name
    assert "no git remotes found" in reading.failure
    # Nothing else was asked: the forge that hosts the governed repository is
    # unknown, so no other read could be aimed anywhere.
    assert forge.calls == [tuple(governed_repository_argv())]


def test_an_identity_outside_the_forges_grammar_rejects_rather_than_reading_nothing() -> None:
    forge = _forge(identity="")

    reading = _reading(forge=forge, installed_build=None)

    assert isinstance(reading, UnreadableRelease)
    assert reading.repository == _ROOT.name


def test_every_record_naming_one_build_identifier_costs_one_resolution() -> None:
    forge = _forge()
    reader = forge_release_reader(project_root=_ROOT, runner=forge)
    body = _body(installed_build="livespec-dev-tooling v1.96.1")

    first = reader.reading(body=body)
    second = reader.reading(body=_body(installed_build="livespec-dev-tooling v1.95.12"))

    assert first == second
    # A timeline carries one record per capture and replay, each naming the same
    # build identifier, so the resolution is taken once and the forge is asked
    # three times rather than three times per record.
    assert len(forge.calls) == 3


def test_two_records_naming_different_repositories_are_resolved_separately() -> None:
    # The control for the memo: a cache keyed on nothing would answer the first
    # record's repository for the second.
    forge = _forge()
    reader = forge_release_reader(project_root=_ROOT, runner=forge)

    sibling = reader.reading(body=_body(installed_build="livespec-dev-tooling v1.96.1"))
    governed = reader.reading(body=_body(installed_build=None))

    assert sibling == ReleaseTags(repository=_SIBLING, tags=_SIBLING_TAGS)
    assert governed == ReleaseTags(repository=_GOVERNED, tags=_GOVERNED_TAGS)
