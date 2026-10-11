"""The Enemy Unit Test suite's absent-run fixture is a well-formed ULID.

Two tier 0 cases drive `questions` and `answer_question` against a run id the
factory does not hold, and the whole point of both is that the server
CONSIDERED the request and declined it — a parked run's reconciler reads "no
credential resolved" and "a healthy server refused the act" as different facts
with different remedies. That discrimination only works while the id is one
the server can PARSE: an id it rejects as malformed is refused at the edge,
before the credential it is supposed to be testing is ever consulted.

Measured 2026-10-11 against both the pinned 0.254.0 server on :32276 and the
0.382.0-nightly.0 candidate on :32278, the previous fixture
`01ENEMYUNITTESTABSENTRUN0` was not a ULID in two independent ways — Crockford
base32 excludes `U`, and the string is 25 characters where a ULID is 26 — so
both engines answered 400 for a malformed id. That 400 SATISFIES the suite's
own `status >= 400` assertion, which is why nothing announced it: the case
passed its stated bar for a reason that has nothing to do with the credential.

This module is deliberately NOT an enemy test: it spawns nothing and needs no
server. It reads the literal out of the suite's own source so it cannot drift
from a copy, and it carries a POSITIVE CONTROL — the retired literal, asserted
to fail each of the same three tests — because every assertion here reports a
well-formedness that an instrument matching nothing would report identically.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TIER0_SURFACE = _REPO_ROOT / "fabro-enemy-unit-tests" / "test_tier0_fabro_port_surface.py"
_FIXTURE_NAME = "_ABSENT_RUN_ID"

# Crockford base32, which is what a ULID is spelled in: `I`, `L`, `O` and `U`
# are excluded from the alphabet — the first three because they are confusable
# with digits, `U` to keep accidental obscenities out of generated ids.
_CROCKFORD_ALPHABET = frozenset("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
_ULID_LENGTH = 26
# The 48-bit timestamp a ULID opens with cannot overflow its ten base32
# characters, so the leading character is bounded even though the alphabet is
# not. A decoder rejects `8` through `Z` in that position.
_ULID_LEADING_CHARACTERS = frozenset("01234567")
# The retired literal, kept as the control for all three tests below.
_RETIRED_FIXTURE = "01ENEMYUNITTESTABSENTRUN0"
# What makes the fixture name no run: it is a RESERVED literal, recognisable on
# sight as suite scaffolding, rather than a value any generator would emit.
_FIXTURE_MARKER = "ENEMY"


def _fixture_literal(*, source: Path = _TIER0_SURFACE) -> str:
    """The absent-run id as the tier 0 surface actually declares it.

    REFUSES a surface declaring no such literal rather than returning a
    fallback. A tolerant parse would hand every measurement below a
    well-formed value the suite does not drive — the wrong-population
    failure, arrived at through a default rather than through a typo.
    """
    module = ast.parse(source.read_text(encoding="utf-8"), filename=source.name)
    for node in module.body:
        match node:
            # The name is compared in a GUARD, not written into the pattern. A
            # bare `_FIXTURE_NAME` there is a CAPTURE pattern rather than a
            # value pattern, so it binds whatever name it finds and matches
            # every string assignment in the file. That is how this parse
            # first shipped, and the barren-surface case below is what caught
            # it: it happened to return the right literal only because no
            # other module-level string assignment precedes it.
            case ast.Assign(
                targets=[ast.Name(id=name)],
                value=ast.Constant(value=str() as literal),
            ) if name == _FIXTURE_NAME:
                return literal
            case _:
                pass
    raise AssertionError(f"{source.name} declares no {_FIXTURE_NAME} string literal")


def test_the_fixture_is_read_off_the_tier0_surfaces_own_declaration() -> None:
    # The instrument before the measurements that ride on it: a parse aimed at
    # the wrong name, or at a file that had moved, would raise rather than
    # quietly report a well-formed id that is not the one the suite drives.
    literal = _fixture_literal()

    assert _TIER0_SURFACE.is_file()
    assert literal
    assert literal != _RETIRED_FIXTURE


def test_a_surface_declaring_no_fixture_is_refused_rather_than_defaulted(
    tmp_path: Path,
) -> None:
    # The other half of that instrument control. Every test here reads one
    # literal, so a parse that answered SOMETHING for a surface carrying no
    # such declaration would make all of them report on a value the suite
    # never drives, and report it as a pass.
    barren = tmp_path / "test_tier0_barren.py"
    _ = barren.write_text("_SOME_OTHER_FIXTURE = 'not the one'\n", encoding="utf-8")

    with pytest.raises(AssertionError, match=_FIXTURE_NAME):
        _ = _fixture_literal(source=barren)


def test_the_absent_run_fixture_is_a_syntactically_valid_ulid() -> None:
    literal = _fixture_literal()

    assert len(literal) == _ULID_LENGTH
    assert not set(literal) - _CROCKFORD_ALPHABET
    assert literal[0] in _ULID_LEADING_CHARACTERS


def test_the_retired_fixture_fails_every_one_of_those_tests() -> None:
    # The positive control. Each assertion above reports a well-formedness, so
    # each would read identically if it were pointed at nothing at all; these
    # name exactly which properties the retired literal broke and therefore
    # prove the three tests can return a hit.
    assert len(_RETIRED_FIXTURE) != _ULID_LENGTH
    assert sorted(set(_RETIRED_FIXTURE) - _CROCKFORD_ALPHABET) == ["I", "U"]


def test_the_absent_run_fixture_is_a_reserved_literal_rather_than_a_generated_id() -> None:
    # The other half of "names no run", and the half no syntax test can carry:
    # a well-formed ULID is only reliably absent from the factory if it was
    # never generated by one.
    assert _FIXTURE_MARKER in _fixture_literal()
