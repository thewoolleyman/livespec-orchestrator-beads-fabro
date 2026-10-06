"""The committed-run-config TOML reader, and the silent-absence defect it retired.

WHAT THIS BINDS. One declaration of `[run.checkpoint] commit_timeout` can be
spelled many ways in TOML, and the credential requirement multiplies that value
by three when it sums the per-attempt checkpoint ceiling. So a reader that fails
to RECOGNIZE a spelling does not merely miss a feature: it reports the key as
ABSENT, the caller applies the engine's stock thirty-second default, and the
credential floor comes out well below what the configuration asks for. Nothing
in the result says so, because the smaller figure is a perfectly well-formed
number.

WHY THE EQUIVALENCE CASE IS PARAMETRIZED OVER SPELLINGS RATHER THAN ASSERTED
ONCE. Two successive hand-rolled regex readers were wrong here, each fixing the
spellings its author had thought of and each still silently defaulting the rest:
the first accepted only `key = "value"` with nothing after the closing quote,
and the second added indentation, literal strings and trailing comments while
still reporting `[run . checkpoint]`, `["run"."checkpoint"]`, a quoted key, an
inline table and a root-level dotted key as absent. The list below is therefore
the measured defect set, not a style survey, and the case asserts every entry
resolves the SAME value -- which is the property a pattern-matching reader
cannot have and a parser has by construction.

THE THREE NON-VALUES ARE ASSERTED APART, because collapsing them is the defect.
`None` means genuinely undeclared and a documented default is correct;
`TomlStringUnreadable` means declared-but-not-a-string; `TomlDocumentUnparseable`
means the file is not TOML at all. The last two must never read as the first.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_toml_read import (
    TomlDocumentUnparseable,
    TomlStringUnreadable,
    toml_section_string,
    toml_section_string_declaration,
)

_SECTION = "run.checkpoint"
_KEY = "commit_timeout"
_VALUE = "10m"

# Every entry declares `run.checkpoint.commit_timeout = "10m"`. The id names the
# spelling so a failure says which one regressed rather than only that one did.
_EQUIVALENT_SPELLINGS = [
    pytest.param('[run.checkpoint]\ncommit_timeout = "10m"\n', id="canonical"),
    pytest.param('[run.checkpoint]\n    commit_timeout = "10m"\n', id="indented-assignment"),
    pytest.param("[run.checkpoint]\ncommit_timeout = '10m'\n", id="literal-string"),
    pytest.param('[run.checkpoint]\ncommit_timeout = "10m"  # budget\n', id="trailing-comment"),
    pytest.param('[run . checkpoint]\ncommit_timeout = "10m"\n', id="spaced-header"),
    pytest.param('["run"."checkpoint"]\ncommit_timeout = "10m"\n', id="quoted-header-segments"),
    pytest.param('[run.checkpoint]\n"commit_timeout" = "10m"\n', id="quoted-key"),
    pytest.param('[run]\ncheckpoint = { commit_timeout = "10m" }\n', id="inline-table"),
    pytest.param('run.checkpoint.commit_timeout = "10m"\n', id="root-dotted-key"),
    pytest.param('[run.checkpoint]\r\ncommit_timeout = "10m"\r\n', id="crlf"),
    pytest.param('[run.checkpoint]\ncommit_timeout = """10m"""\n', id="multiline-basic-string"),
]


@pytest.mark.parametrize("text", _EQUIVALENT_SPELLINGS)
def test_every_equivalent_spelling_of_one_declaration_reads_the_same_value(text: str) -> None:
    """One declaration, many spellings, one value — the regression control.

    Each entry defeated at least one of the two regex readers that preceded the
    parser, and each defeat presented as ABSENT rather than as an error.
    """
    assert toml_section_string_declaration(text=text, section=_SECTION, key=_KEY) == _VALUE


def test_an_undeclared_key_is_absent_so_a_caller_may_apply_its_documented_default() -> None:
    """ABSENT is a real answer and must stay distinguishable from the others.

    A run config declaring a checkpoint table but no `commit_timeout` is
    complete and ordinary, and the engine's own stock budget is the right
    reading. This is the one case where defaulting is correct, which is why the
    other two must not be able to reach it.
    """
    text = "[run.checkpoint]\nskip_git_hooks = false\n"

    assert toml_section_string_declaration(text=text, section=_SECTION, key=_KEY) is None


def test_an_undeclared_section_is_absent_rather_than_a_fault() -> None:
    """A config declaring no checkpoint table at all is equally ordinary."""
    text = '[workflow]\ngraph = "workflow.fabro"\n'

    assert toml_section_string_declaration(text=text, section=_SECTION, key=_KEY) is None


def test_a_section_name_that_resolves_to_a_non_table_is_absent_rather_than_a_crash() -> None:
    """A path walking INTO a scalar is absent, not an exception.

    `[run] checkpoint = 600` makes `run.checkpoint` a number, so the walk to its
    `commit_timeout` has nowhere to go. The honest answer is that the key is not
    declared; raising here would turn a malformed-but-parseable config into a
    traceback from inside a credential derivation.
    """
    text = "[run]\ncheckpoint = 600\n"

    assert toml_section_string_declaration(text=text, section=_SECTION, key=_KEY) is None


@pytest.mark.parametrize(
    ("text", "expected_raw"),
    [
        pytest.param("[run.checkpoint]\ncommit_timeout = 600\n", "600", id="integer"),
        pytest.param('[run.checkpoint]\ncommit_timeout = ["10m"]\n', "['10m']", id="array"),
        pytest.param("[run.checkpoint]\ncommit_timeout = true\n", "True", id="boolean"),
    ],
)
def test_a_declared_non_string_is_unreadable_and_quotes_what_it_found(
    text: str, expected_raw: str
) -> None:
    """Declared-but-not-a-string refuses, and names the value it could not use.

    The raw rendering is asserted because a refusal naming only the key leaves
    an operator comparing their file against expectations nobody wrote down.
    """
    declaration = toml_section_string_declaration(text=text, section=_SECTION, key=_KEY)

    assert isinstance(declaration, TomlStringUnreadable), declaration
    assert declaration.raw == expected_raw


def test_a_document_that_is_not_toml_reports_that_rather_than_an_absence() -> None:
    """An unparseable document says nothing about what it declares.

    Distinct from absence because the two support opposite conclusions: an
    absent key licenses a default, while a file the engine itself would reject
    licenses nothing at all.
    """
    declaration = toml_section_string_declaration(
        text='[run.checkpoint\ncommit_timeout = "10m"\n', section=_SECTION, key=_KEY
    )

    assert isinstance(declaration, TomlDocumentUnparseable), declaration
    assert declaration.detail != ""


@pytest.mark.parametrize("text", _EQUIVALENT_SPELLINGS)
def test_the_collapsing_reader_returns_the_same_value_for_every_spelling(text: str) -> None:
    """The `str | None` reader its existing callers use, over the same spellings.

    A graph path and an environment id route an absent and an unusable
    declaration identically, so that reader collapses them — but it must still
    RECOGNIZE every spelling, which is the half of the defect that affected it
    too.
    """
    assert toml_section_string(text=text, section=_SECTION, key=_KEY) == _VALUE


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("[run.checkpoint]\nskip_git_hooks = false\n", id="absent-key"),
        pytest.param("[run.checkpoint]\ncommit_timeout = 600\n", id="declared-non-string"),
        pytest.param('[run.checkpoint\ncommit_timeout = "10m"\n', id="unparseable-document"),
    ],
)
def test_the_collapsing_reader_reports_none_for_every_non_value(text: str) -> None:
    """All three non-values collapse to None for the callers that want that."""
    assert toml_section_string(text=text, section=_SECTION, key=_KEY) is None
