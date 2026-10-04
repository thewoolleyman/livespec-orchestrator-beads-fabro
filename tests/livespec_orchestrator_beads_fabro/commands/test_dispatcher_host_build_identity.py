"""Tests for the BUILD IDENTITY a host-leg Proof of Done record names.

The host-leg clause of `SPECIFICATION/contracts.md` (v115) requires a host record
to "additionally name the BUILD IDENTITY exercised: the release tag and the
installed build identifier, or, where no release applies, the default-branch
commit exercised", and the host-captured leg of its post-merge acceptance section
makes that identity the subject of a containment check. One module therefore owns
both directions — the posting primitive RENDERS it and the acceptance pass PARSES
it back — and these tests bind the ROUND TRIP rather than each half alone, because
a renderer and a reader that disagreed about the label spelling would each pass a
test of its own while the pass reported every published record as naming no build.

The hand-written bodies below are deliberately the ones a rendered body cannot
produce: a record that names no build identity at all, a release bullet carrying
the reserved literal in another case, and a label whose value is blank.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    BUILD_IDENTITY_HEADING,
    COMMIT_LABEL,
    INSTALLED_BUILD_LABEL,
    NO_RELEASE,
    RELEASE_TAG_LABEL,
    BuildIdentity,
    build_identity_in,
)

_RELEASE_TAG = "v0.166.0"
_INSTALLED_BUILD = "livespec-orchestrator-beads-fabro 0.166.0 (d709f27ac3c1)"
_COMMIT = "7b92d1a0f1e2d3c4b5a6978877665544332211aa"


def test_release_build_identity_round_trips_through_the_rendered_section() -> None:
    """A released build renders both halves and parses back to the same value.

    `containment_ref` is asserted separately from the three fields because it is
    the only thing the acceptance pass asks this value for, and a reader that
    recovered all three fields while answering the wrong ref would check
    containment against the commit the capture happened to mention rather than
    against the release the clause names.
    """
    identity = BuildIdentity(
        release_tag=_RELEASE_TAG, installed_build=_INSTALLED_BUILD, commit=_COMMIT
    )
    rendered = identity.render()
    assert build_identity_in(body=rendered) == identity
    assert identity.containment_ref == _RELEASE_TAG
    assert BUILD_IDENTITY_HEADING in rendered
    assert _INSTALLED_BUILD in rendered


def test_an_unreleased_build_identity_names_the_commit_and_checks_against_it() -> None:
    """`release: none` round trips, and the commit becomes the containment ref."""
    identity = BuildIdentity(release_tag=None, installed_build=None, commit=_COMMIT)
    rendered = identity.render()
    assert NO_RELEASE in rendered
    assert build_identity_in(body=rendered) == identity
    assert identity.containment_ref == _COMMIT


def test_a_body_naming_no_build_identity_reads_as_none() -> None:
    """`None` is the "this record names no build" answer the evidence rule needs.

    Deliberately distinct from a `BuildIdentity` whose every field is `None`: the
    pass reports a record naming no build as not evidence, and a value object
    would make that refusal indistinguishable from one whose labels were present
    but empty.
    """
    assert build_identity_in(body="Proof of Done — host_verified — session s — t\n") is None


def test_a_release_bullet_reading_none_in_another_case_is_not_a_release_tag() -> None:
    """The literal the clause reserves is read as "no release applies"."""
    body = f"- {RELEASE_TAG_LABEL}: None\n- {COMMIT_LABEL}: {_COMMIT}\n"
    identity = build_identity_in(body=body)
    assert identity is not None
    assert identity.release_tag is None
    assert identity.containment_ref == _COMMIT


def test_a_record_naming_neither_a_release_nor_a_commit_has_no_containment_ref() -> None:
    """An identity with nothing to check against answers `None`, never a guess.

    This is the fail-closed half: the pass treats a record it cannot aim the
    containment check at as not evidence, so the ref must be absent rather than
    defaulted to the installed build identifier — which the clause says is
    "recorded, not verified" and is not a git ref at all.
    """
    body = f"- {RELEASE_TAG_LABEL}: none\n- {INSTALLED_BUILD_LABEL}: {_INSTALLED_BUILD}\n"
    identity = build_identity_in(body=body)
    assert identity is not None
    assert identity.containment_ref is None
    assert identity.installed_build == _INSTALLED_BUILD


def test_an_empty_label_value_is_absent_rather_than_an_empty_string() -> None:
    """A bullet with a label and no value asserts nothing, so it reads as absent."""
    body = f"- {RELEASE_TAG_LABEL}:\n- {COMMIT_LABEL}:   \n"
    assert build_identity_in(body=body) is None


def test_a_label_inside_another_bullets_prose_does_not_become_the_value() -> None:
    """Only a bullet whose OWN label matches is read, never a mention in prose.

    The record body is prose around the proof, and the steps routinely talk about
    the commit and the tag they exercised. A reader matching the label anywhere
    would take a step's narrative as the build identity, which is the fail-OPEN
    direction: the containment check would then be aimed at whatever ref the
    narrative happened to name.
    """
    body = (
        f"1. Confirm the {COMMIT_LABEL}: {_COMMIT} is installed.\n"
        f"- {RELEASE_TAG_LABEL}: {_RELEASE_TAG}\n"
    )
    identity = build_identity_in(body=body)
    assert identity is not None
    assert identity.commit is None
    assert identity.containment_ref == _RELEASE_TAG
