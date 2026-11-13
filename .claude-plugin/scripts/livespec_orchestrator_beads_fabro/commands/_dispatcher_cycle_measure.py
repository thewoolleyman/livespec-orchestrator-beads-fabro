"""The canonical product logical-line measurement for one completed cycle.

Plan slice S6 (`bd-ib-z2y4ca`) feeds per-cycle progress signals into the
existing non-convergence bounce. `SPECIFICATION/contracts.md` fixes what the
size measurement MEANS, and this module is the one place that computes it:

  "Changed product logical lines MUST mean added plus removed logical lines
  between the pair's test-only Red state and Green state, not net file growth.
  The measurement MUST use the repository's canonical logical-line counting and
  product-path classification, excluding tests, documentation, comments, blank
  lines and formatting-only changes."

WHY THE COUNTING IS RESTATED HERE RATHER THAN IMPORTED. The canonical counter
is `livespec_dev_tooling.checks.file_lloc._count_lloc`, which is module-private
to a check, and the shipped plugin package must not depend on the dev-tooling
package at all — the same constraint `_dispatcher_tdd_commits` records for the
three TDD trailer keys. So the SEMANTICS are restated (standard-library
`tokenize` for code lines, `ast` for docstring lines, both excluded exactly as
the check excludes them) and the paired test pins them against real sources.

WHY `None` RATHER THAN A COUNT WHEN A SOURCE DOES NOT TOKENIZE. The clause
requires "unsupported counting" to be "exposed as unobserved with a reason for
the affected measurement, never substituted with zero". A source this counter
cannot read is exactly that case: a zero would read as a cycle that changed no
product code, which is a measurement, and the honest answer is that no
measurement was taken.

HOW FORMATTING-ONLY CHANGES ARE EXCLUDED, AND THE RESIDUAL. The two sources'
CODE TOKEN SEQUENCES are compared first: a `ruff format` reflow moves tokens
between physical lines without changing the sequence, so an identical sequence
is reported as zero changed lines however much the physical text moved. That
gate is what makes "formatting-only" a measured exclusion rather than an
aspiration. The residual is a change that BOTH reflows and edits code in one
file: its reflowed lines contribute to the count beside the genuine edit. That
over-counts rather than under-counts, which is the safe direction for a ceiling
whose breach must be strict.

WHY THE LINE DIFFERENCE IS A MULTISET DIFFERENCE. Added plus removed is counted
over the multiset of normalized logical lines, so a pure REORDERING of
unchanged statements contributes nothing — a diff-based count would report the
moved block twice while nothing about the product changed. A line appearing
twice in one state and once in the other contributes the one occurrence that
differs, which is why the counts are multisets rather than sets.

This module is PURE: no IO, no environment reads, and it never raises. The git
reads that supply the two source texts live in `_dispatcher_cycle_probe`.
"""

from __future__ import annotations

import ast
import tokenize
from collections import Counter
from io import BytesIO
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    FLEET_SOURCE_TREE_DECLARATION_SECTION,
    FLEET_SOURCE_TREE_KEY,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_toml_read import (
    TomlDocumentUnparseable,
    toml_document,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "PRODUCT_LLOC_MEASUREMENT_METHOD",
    "changed_product_logical_lines",
    "is_product_path",
    "product_source_prefixes",
]

# The method identity the cycle record carries so an operator can replay the
# number. It names the counting rule, the normalization and the exclusion gate,
# because a record saying only "logical lines" leaves a replay guessing which of
# several defensible counts produced it.
PRODUCT_LLOC_MEASUREMENT_METHOD = (
    "product-logical-lines/tokenized-multiset-difference/formatting-excluded/v1"
)

# The token types the canonical counter drops before counting a line as code.
# Restated from `livespec_dev_tooling.checks.file_lloc` for the dependency
# reason in the module docstring; the paired test pins the equivalence.
_NON_CODE_TOKEN_TYPES = frozenset(
    {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
    }
)

# Everything `tokenize` and `ast` raise for a source they cannot read.
# `IndentationError` is a `SyntaxError` subclass and `TokenError` is neither, so
# both ends are named rather than assumed.
_UNREADABLE_SOURCE_ERRORS = (SyntaxError, ValueError, tokenize.TokenError)

_PYTHON_SUFFIX = ".py"
_TESTS_PREFIX = "tests/"
_VENDOR_SEGMENT = "_vendor/"
# A comma immediately before one of these closers is syntactically inert, which
# is what `_without_inert_commas` reads it as.
_COMMA = ","
_CLOSERS = ([")"], ["]"], ["}"])


def product_source_prefixes(*, pyproject_text: str) -> tuple[str, ...]:
    """The repository's declared first-party SOURCE trees, as path prefixes.

    Read from the same declaration the repository's own gates classify a path
    against — the `[[tool.livespec_dev_tooling.mirror_pairings]]` array whose
    `source_tree` entries the shared source-prefix derivation uses. Reading the
    declaration rather than hardcoding the trees is what keeps this measurement
    pointed at the same population the ceiling check and the Red-Green hook
    classify, in this repository and in any other the Dispatcher governs.

    An unparseable or silent declaration yields the EMPTY tuple, which makes
    every path non-product and therefore makes the whole size measurement
    unobservable rather than zero. That is the fail-closed direction: a guess at
    the trees would report a confident measurement over a population nobody
    declared.
    """
    document = toml_document(text=pyproject_text)
    if isinstance(document, TomlDocumentUnparseable):
        return ()
    pairings = _walk(table=document, path=FLEET_SOURCE_TREE_DECLARATION_SECTION)
    if not isinstance(pairings, list):
        return ()
    found: list[str] = []
    for raw in cast("list[object]", pairings):
        entry = _table(value=raw)
        if entry is None:
            continue
        tree = entry.get(FLEET_SOURCE_TREE_KEY)
        if isinstance(tree, str) and tree != "":
            found.append(tree)
    return tuple(found)


def _walk(*, table: dict[str, object], path: tuple[str, ...]) -> object | None:
    """The value a dotted path reaches, or None when any segment is not a table."""
    current: object = table
    for segment in path:
        narrowed = _table(value=current)
        if narrowed is None:
            return None
        current = narrowed.get(segment)
    return current


def _table(*, value: object) -> dict[str, object] | None:
    """One parsed value as a string-keyed table, or None when it is not one."""
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def is_product_path(*, path: str, prefixes: tuple[str, ...]) -> bool:
    """Whether one repository-relative path is PRODUCT code for this measurement.

    `.py` under one of the declared source trees, and neither a test nor
    vendored. Documentation, configuration and data carry no logical lines this
    counter can read, so the suffix test excludes them before the tree test
    rather than relying on no `.md` living under a source tree.

    The test-tree exclusion is a `tests/` prefix rather than the declared
    `test_tree` values, for the reason the repository's own commit-time gate
    uses the same prefix: a test path is identified by where it lives, and a
    source tree that nested its tests would otherwise classify them as product.
    """
    if not path.endswith(_PYTHON_SUFFIX):
        return False
    if path.startswith(_TESTS_PREFIX) or _VENDOR_SEGMENT in path:
        return False
    return path.startswith(prefixes) if prefixes else False


def changed_product_logical_lines(*, before: str, after: str) -> int | None:
    """Added plus removed logical lines between two states of one product file.

    `before` is the pair's test-only Red state of the file and `after` its Green
    state, so the figure is the product code the cycle actually wrote — net file
    growth is never consulted. `None` when either state cannot be counted.
    """
    before_read = _read_source(source=before)
    after_read = _read_source(source=after)
    if before_read is None or after_read is None:
        return None
    before_tokens, before_lines = before_read
    after_tokens, after_lines = after_read
    if before_tokens == after_tokens:
        return 0
    before_counts = Counter(before_lines)
    after_counts = Counter(after_lines)
    removed = sum((before_counts - after_counts).values())
    added = sum((after_counts - before_counts).values())
    return added + removed


def _read_source(*, source: str) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """The source's code tokens and its normalized code lines, or None.

    Both derivations come from ONE walk, because a second walk could not be
    shown to have seen the same tokens — and the formatting-only gate compares
    the token sequence against the very lines it decides about.
    """
    read = attempt(action=lambda: _walk_source(source=source), exceptions=_UNREADABLE_SOURCE_ERRORS)
    return None if isinstance(read, AttemptFailure) else read


def _walk_source(*, source: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The one walk `_read_source` guards — raises for a source it cannot read."""
    docstring_lines = _docstring_lines(source=source)
    tokens: list[str] = []
    grouped: dict[int, list[str]] = {}
    for token in tokenize.tokenize(BytesIO(source.encode("utf-8")).readline):
        if token.type in _NON_CODE_TOKEN_TYPES:
            continue
        line = token.start[0]
        if line in docstring_lines:
            continue
        tokens.append(token.string)
        grouped.setdefault(line, []).append(token.string)
    return _without_inert_commas(tokens=tokens), tuple(
        " ".join(grouped[line]) for line in sorted(grouped)
    )


def _without_inert_commas(*, tokens: list[str]) -> tuple[str, ...]:
    """The token sequence with every trailing comma before a closer dropped.

    A comma immediately preceding `)`, `]` or `}` is syntactically inert, and it
    is exactly what the formatter's magic trailing comma ADDS when it reflows a
    single-line call across several lines. Without this normalization the
    formatting-only gate above would miss the most common real reflow — measured
    on `render(first, second)` becoming a four-line call, which differs from its
    source by that one comma and nothing else.
    """
    return tuple(
        text
        for index, text in enumerate(tokens)
        if not (text == _COMMA and tokens[index + 1 :][:1] in _CLOSERS)
    )


def _docstring_lines(*, source: str) -> frozenset[int]:
    """The line numbers covered by module, class and function docstrings.

    Excluded from the count for the reason the canonical counter excludes them:
    a docstring is documentation, and the clause excludes documentation. It is
    what makes a prose-only amend measure zero rather than measuring the prose.
    """
    covered: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = node.body
        if not body:
            continue
        first = body[0]
        if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
            continue
        if not isinstance(first.value.value, str) or first.end_lineno is None:
            continue
        covered.update(range(first.lineno, first.end_lineno + 1))
    return frozenset(covered)
