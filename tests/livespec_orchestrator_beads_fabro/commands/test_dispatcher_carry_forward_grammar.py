"""The direct-read grammar, exercised as the SHIPPED BYTES the sandbox runs.

Every case below loads `grammar_program_fragment()` into a module and calls it.
Nothing here re-implements a production: a Python transcription of the grammar
would be a second account of it, and the two would diverge in the direction
that is invisible -- both would look correct and only the one the sandbox runs
would decide anything.

THE CASES ARE THE CLAUSE'S OWN EXAMPLES. `SPECIFICATION/scenarios.md` Scenario
178 enumerates the shapes that must be refused -- an operation, a recursive
read, a glob, a non-canonical path, a parent segment, a hidden substitution, a
missing operand, an option-shaped pattern, a dash operand -- and each has a case
here. The accepting cases are the clause's seven productions, because a grammar
tested only on refusals would pass while admitting nothing at all.
"""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_carry_forward_grammar import (
    READ_IDENTITY_LABEL,
    WORKING_DIRECTORY_LINE,
    WORKING_DIRECTORY_PREFIX,
    grammar_program_fragment,
)

_MODULE_NAME = "livespec_carry_forward_grammar_fragment_under_test"


@pytest.fixture(scope="module")
def grammar(tmp_path_factory: pytest.TempPathFactory) -> ModuleType:
    """The fragment, materialized and imported exactly as the sandbox would run it."""
    path = tmp_path_factory.mktemp("grammar") / "fragment.py"
    path.write_text(grammar_program_fragment(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def test_the_fragment_carries_the_record_line_spellings_it_was_given(
    grammar: ModuleType,
) -> None:
    """The substitution happened, so the fragment parses the lines the prompts write."""
    assert grammar.WORKING_DIRECTORY_LINE == WORKING_DIRECTORY_LINE
    assert grammar.WORKING_DIRECTORY_PREFIX == WORKING_DIRECTORY_PREFIX
    assert grammar.READ_IDENTITY_LABEL == READ_IDENTITY_LABEL


# What each production READS, named rather than carried as a bare boolean: the
# distinction decides whether a step owes a read identity, and `True`/`False` in
# a case table says nothing about which way round that is.
_WORKING_TREE = "working tree"
_OBJECT_STORE = "object store"


@pytest.mark.parametrize(
    ("command", "operands", "reads"),
    [
        ("cat AGENTS.md", ["AGENTS.md"], _WORKING_TREE),
        ("cat AGENTS.md README.md", ["AGENTS.md", "README.md"], _WORKING_TREE),
        ("head -n 20 AGENTS.md", ["AGENTS.md"], _WORKING_TREE),
        ("tail AGENTS.md", ["AGENTS.md"], _WORKING_TREE),
        ("wc -c AGENTS.md", ["AGENTS.md"], _WORKING_TREE),
        ("wc AGENTS.md", ["AGENTS.md"], _WORKING_TREE),
        ('grep -n "ledger comment" AGENTS.md', ["AGENTS.md"], _WORKING_TREE),
        ("grep -A 3 -B 2 -e pattern AGENTS.md", ["AGENTS.md"], _WORKING_TREE),
        ("sed -n '1,5p' AGENTS.md", ["AGENTS.md"], _WORKING_TREE),
        ("sed -n '3p;9p' AGENTS.md", ["AGENTS.md"], _WORKING_TREE),
        ("diff -u a.md b.md", ["a.md", "b.md"], _WORKING_TREE),
        ("git show HEAD:AGENTS.md", ["AGENTS.md"], _OBJECT_STORE),
    ],
)
def test_each_production_is_admitted_with_its_path_operands(
    grammar: ModuleType, command: str, operands: list[str], reads: str
) -> None:
    """The seven productions the clause enumerates, and what each one reads."""
    verdict = grammar.classify_command(command)
    assert verdict["inside"] is True
    assert verdict["reason"] is None
    assert verdict["operands"] == operands
    assert verdict["working_tree"] is (reads == _WORKING_TREE)


@pytest.mark.parametrize(
    "command",
    [
        # Scenario 178's own refusal cases, in the order it states them.
        "uv run livespec-orchestrator-beads-fabro-list-plans --json",
        'grep -rn "Scenario 178" SPECIFICATION/',
        "cat plan/*/research/001.md",
        'grep -n "$(cat plan/topic/pattern.txt)" AGENTS.md',
        "cat",
        "grep -F '-fplan/topic/pattern.txt' AGENTS.md",
        "cat -",
        # And the shapes a hidden read could otherwise arrive through.
        "cat AGENTS.md | wc -l",
        "cat AGENTS.md; cat README.md",
        "cat < AGENTS.md",
        "cat AGENTS.md > copy.md",
        "cat ~/AGENTS.md",
        "cat 'unbalanced",
        "head -n many AGENTS.md",
        "wc -z AGENTS.md",
        "sed -n '1,$p' AGENTS.md",
        "sed AGENTS.md",
        "diff a.md b.md c.md",
        "git log HEAD:AGENTS.md",
        "git show HEAD:",
        "grep -A pattern AGENTS.md",
        "grep -e",
        "   ",
    ],
)
def test_every_shape_outside_the_grammar_is_refused_with_a_reason(
    grammar: ModuleType, command: str
) -> None:
    """A refused command names why, and reads nothing the decision could rely on."""
    verdict = grammar.classify_command(command)
    assert verdict["inside"] is False
    assert isinstance(verdict["reason"], str)
    assert verdict["reason"]
    assert verdict["operands"] == []


def test_a_double_quoted_substitution_is_refused_on_its_own_terms(
    grammar: ModuleType,
) -> None:
    """The double-quoted arm names the character, which is what the record reports."""
    verdict = grammar.classify_command('grep -n "a`b`c" AGENTS.md')
    assert verdict["inside"] is False
    assert "`" in verdict["reason"]


def test_a_single_quoted_metacharacter_is_literal_and_does_not_refuse(
    grammar: ModuleType,
) -> None:
    """Single quotes make a metacharacter a pattern, which the clause admits."""
    verdict = grammar.classify_command("grep -F 'a|b' AGENTS.md")
    assert verdict["inside"] is True
    assert verdict["operands"] == ["AGENTS.md"]


def test_a_quote_inside_the_other_quote_does_not_open_a_region(
    grammar: ModuleType,
) -> None:
    """A `'` inside double quotes is text, so the single-quote state never flips."""
    assert grammar.forbidden_character('grep -F "it\'s" AGENTS.md') is None
    assert grammar.forbidden_character("grep -F 'say \"hi\"' AGENTS.md") is None


@pytest.mark.parametrize(
    ("operand", "canonical"),
    [
        ("AGENTS.md", "AGENTS.md"),
        ("./plan//topic/research/001.md", "plan/topic/research/001.md"),
        ("plan/./topic/note.md", "plan/topic/note.md"),
    ],
)
def test_a_non_canonical_operand_canonicalizes_to_the_path_it_reads(
    grammar: ModuleType, operand: str, canonical: str
) -> None:
    """Canonicalization is what makes an incoming change to that file comparable."""
    assert grammar.canonical_path(operand) == canonical


@pytest.mark.parametrize(
    "operand",
    ["/etc/passwd", "", "docs/../AGENTS.md", "..", ".", "./"],
)
def test_a_rejected_operand_canonicalizes_to_nothing(grammar: ModuleType, operand: str) -> None:
    """Absolute, empty and parent-bearing operands are rejected, never guessed at."""
    assert grammar.canonical_path(operand) is None
