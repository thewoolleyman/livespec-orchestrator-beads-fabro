"""Which repository a plan record's release rule names, read off real record bytes.

Covers `_plan_release_repository`. The parse is pure, so every case is one
rendered record graded against the four forms the v148 plan-record clause
distinguishes: an `<owner>/<repository>` word, a bare `<repository>` word, a word
of neither form, and a record naming no installed build identifier at all.

EVERY CASE IS RENDERED THROUGH THE PRODUCTION RENDERER rather than hand-written.
The parse's whole job is to read a word out of a record a publishing primitive
wrote, so a hand-assembled body would prove only that the parse handles whatever
bytes this module chose — the same reason `test_plan_proof_leg` renders its
timelines.

THE BARE AND NEITHER-FORM CASES ARE THE PAIR THAT GIVES EACH OTHER MEANING. Both
resolve downstream against the governed repository on some path, so a parse that
collapsed them would satisfy the fallback behaviour while losing the forge
question the bare form owes: a bare word is a repository NAME to be asked about,
and a word of neither form is not a name at all.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HOST_CAPTURED,
)
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
from livespec_orchestrator_beads_fabro.commands._plan_release_repository import (
    BareRepository,
    ExplicitRepository,
    ReleaseTags,
    UnreadableRelease,
    release_repository_in,
)

_ASSERTION = "The released build runs in a real operator session."


def _body(*, installed_build: str | None) -> str:
    """One plan record body, rendered exactly as the posting primitive writes it."""
    return render_proof_record(
        title=PLAN_PROOF_RECORD_TITLE,
        verdict=VERDICT_CAPTURED,
        identity="session capturing",
        timestamp="2026-10-16T00:00:00Z",
        build=BuildIdentity(
            release_tag="v1.95.12",
            installed_build=installed_build,
            commit="c0ffee1",
        ),
        assertions=(
            RecordAssertion(
                text=_ASSERTION,
                proof_mode=PROOF_MODE_HOST_CAPTURED,
                governing_scenario=None,
                steps=("Install the released build.",),
                proof="$ delivered --version\n1.95.12",
                reproduced=None,
            ),
        ),
    )


def test_a_bare_first_word_names_a_repository_of_the_governed_owner() -> None:
    # The live case this rule exists for: the livespec plan whose honest records
    # name `livespec-dev-tooling` releases while the governed repository is
    # `livespec`.
    named = release_repository_in(body=_body(installed_build="livespec-dev-tooling v1.95.12"))

    assert named == BareRepository(repository="livespec-dev-tooling")


def test_an_owner_and_repository_first_word_names_both_parts() -> None:
    named = release_repository_in(
        body=_body(installed_build="thewoolleyman/livespec-dev-tooling v1.95.12")
    )

    assert named == ExplicitRepository(owner="thewoolleyman", repository="livespec-dev-tooling")
    assert isinstance(named, ExplicitRepository)
    # The rendered name is what every forge read and every refusal cites, so it
    # is the parse's own output rather than something each caller re-joins.
    assert named.name == "thewoolleyman/livespec-dev-tooling"


@pytest.mark.parametrize(
    "installed_build",
    [
        "fabro-sh/fabro/releases v0.254.0",
        "/livespec-dev-tooling v1.95.12",
        "thewoolleyman/ v1.95.12",
    ],
    ids=["two-separators", "empty-owner", "empty-repository"],
)
def test_a_first_word_of_neither_form_names_no_repository(installed_build: str) -> None:
    # Each of these is a word the clause's two forms exclude, so the release
    # repository is the governed one — and the resolution must not be able to ask
    # the forge about a name nobody wrote.
    assert release_repository_in(body=_body(installed_build=installed_build)) is None


def test_a_record_naming_no_installed_build_identifier_names_no_repository() -> None:
    assert release_repository_in(body=_body(installed_build=None)) is None


def test_a_body_carrying_no_build_identity_section_at_all_names_no_repository() -> None:
    assert release_repository_in(body="Plan Proof of Done — captured\n\nno section here") is None


def test_the_two_readings_carry_the_repository_each_one_is_about() -> None:
    # The reading is a two-member union rather than an optional tag set so that
    # "no release applies" and "the gate could not read" cannot be spelled the
    # same way. Each member names the repository, because every refusal the
    # clause requires has to name the repository the gate judged.
    assert ReleaseTags(repository="o/r", tags=frozenset({"v1.0.0"})).repository == "o/r"
    assert UnreadableRelease(repository="o/r", failure="exited 1").failure == "exited 1"
