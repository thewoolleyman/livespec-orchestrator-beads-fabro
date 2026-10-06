"""Reading one declared string out of a committed TOML run config.

WHY A REAL PARSER, AND WHY IT IS VENDORED. `tomllib` is standard library only
from Python 3.11, and this bundle's supported runtime starts at 3.10
(`pyproject.toml` `requires-python >= 3.10.16`, and the distributed
`scripts/bin/_bootstrap.py`, which states 3.10+). An unconditional
`import tomllib` would therefore read as working -- the factory's own
interpreter has it -- while breaking every supported 3.10 adopter at import
time. `SPECIFICATION/constraints.md` forbids PyPI RUNTIME dependencies and
requires vendored ones to live in `.claude-plugin/scripts/_vendor/`; it does
not forbid vendoring, and `typing_extensions` is already vendored for exactly
this 3.10-backport reason. So `tomli` -- which IS the upstream of stdlib
`tomllib`, pure Python with no dependencies -- is vendored beside it, and the
vendored parse and a 3.11+ stdlib parse agree by construction.

WHY NOT A REGEX, STATED AS A MEASUREMENT RATHER THAN A PREFERENCE. Two
successive hand-rolled readers were wrong here, each in the same direction and
each silently. The original matched only `key = "value"` with nothing after the
closing quote. Its replacement widened that to cover indentation, literal
strings and trailing comments -- and was still wrong, because TOML spells ONE
declaration many ways and a pattern only recognizes the spellings its author
thought of. Every form below is the same declaration of
`run.checkpoint.commit_timeout`, and the regex readers returned "absent" for
all but the first:

    [run.checkpoint]                        commit_timeout = "10m"
    [run.checkpoint]                            commit_timeout = "10m"   (indented)
    [run.checkpoint]                        commit_timeout = '10m'
    [run.checkpoint]                        commit_timeout = "10m"  # budget
    [run . checkpoint]                      commit_timeout = "10m"
    ["run"."checkpoint"]                    commit_timeout = "10m"
    [run.checkpoint]                        "commit_timeout" = "10m"
    [run]                                   checkpoint = { commit_timeout = "10m" }
    (root)                                  run.checkpoint.commit_timeout = "10m"

WHY THAT MATTERED MORE THAN A MISSING FEATURE. "Absent" is not a harmless
answer here. An absent `[run.checkpoint] commit_timeout` is an ordinary,
complete run config and correctly takes the engine's own stock thirty-second
budget; a DECLARED one that reads as absent takes that stock budget INSTEAD OF
the configured value. The checkpoint enters the allowance multiplied by three
(the engine spends the budget independently on `git add`, `git diff --cached`
and `git commit`), and that product is billed PER ATTEMPT, so the error scales
with the graph. A repository that raised `commit_timeout` to survive its own
hooks -- precisely the repository that needed the larger allowance -- therefore
got the smaller floor, and nothing said so, because the smaller figure is just
as well-formed a number.

Measured on this repository's own shipped run config and graph: the configured
ten minutes resolves a required lifetime of 588030 seconds, while the same
config read as though the declaration were absent resolves 324690 -- a 263340
second understatement, about 3.05 days. The per-attempt gap is
3 * (600 - 30) = 1710 seconds; the rest is that figure across the attempts the
shipped graph bounds. (The independent review that caught this measured 7395
against 5685, which is the same 1710-second gap billed once.)

THE TWO READERS, and why new code should use the tri-state one.
`toml_section_string` keeps the `str | None` shape its existing callers read
(a graph path and an environment id, where absent and unusable route the same
way). `toml_section_string_declaration` distinguishes ABSENT from
`TomlStringUnreadable`, so a caller that must not silently default can refuse
instead. A DOCUMENT that does not parse at all is `TomlDocumentUnparseable`,
which is also not an absence: a run config the engine itself would reject must
not quietly contribute default figures to a credential floor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import tomli

__all__: list[str] = [
    "TomlDocumentUnparseable",
    "TomlStringUnreadable",
    "toml_section_string",
    "toml_section_string_declaration",
]


@dataclass(frozen=True, kw_only=True)
class TomlDocumentUnparseable:
    """The whole document is not valid TOML.

    Distinct from a missing key because the two support opposite conclusions: a
    missing key means the configuration declares nothing and a documented
    default applies, while an unparseable document means nothing about it is
    known -- including whether it declares the key.
    """

    detail: str


@dataclass(frozen=True, kw_only=True)
class TomlStringUnreadable:
    """The key IS declared, and its value is not a string.

    Carries a rendering of what was found so a refusal can QUOTE it. A
    diagnostic naming only the key leaves an operator comparing their file
    against expectations nobody wrote down.
    """

    raw: str


def _table_at(*, document: dict[str, Any], section: str) -> dict[str, Any] | None:
    """Walk a dotted section path through parsed tables, or None if absent.

    The path is walked against the PARSED document, so every way TOML can spell
    the same table -- a dotted header, a spaced one, quoted segments, an inline
    table, a root-level dotted key -- has already been normalized into nested
    dicts by the parser and arrives here identically. That normalization is the
    whole reason this reads a parse tree instead of lines of text.
    """
    table: dict[str, Any] = document
    for segment in section.split("."):
        candidate = table.get(segment)
        if not isinstance(candidate, dict):
            return None
        table = candidate
    return table


def toml_section_string_declaration(
    *, text: str, section: str, key: str
) -> str | None | TomlStringUnreadable | TomlDocumentUnparseable:
    """One table's string value, or ABSENT, or one of the two unusable verdicts.

    The reader new code should use. `None` means the key is genuinely not
    declared anywhere the section path reaches -- a caller may then apply a
    documented default. `TomlStringUnreadable` means the key IS declared and
    holds something other than a string, and `TomlDocumentUnparseable` means the
    file is not TOML at all; neither is ever safe to treat as a default, because
    both mean the configuration says something the caller would be ignoring.
    """
    try:
        document = tomli.loads(text)
    except tomli.TOMLDecodeError as error:
        return TomlDocumentUnparseable(detail=str(error))
    table = _table_at(document=document, section=section)
    if table is None or key not in table:
        return None
    value = table[key]
    if isinstance(value, str):
        return value
    return TomlStringUnreadable(raw=repr(value))


def toml_section_string(*, text: str, section: str, key: str) -> str | None:
    """One table's string value, with every unusable verdict collapsed to None.

    The shape this module's pre-existing callers read, kept so a graph path and
    an environment id resolve exactly as before: both route an absent and an
    unusable declaration the same way, so the distinction buys them nothing. New
    callers that must not silently default should use
    `toml_section_string_declaration` instead.
    """
    declaration = toml_section_string_declaration(text=text, section=section, key=key)
    return declaration if isinstance(declaration, str) else None
