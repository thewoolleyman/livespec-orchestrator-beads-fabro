"""`SPECIFICATION/scenarios.md` Scenario 238 — a generated register is regenerated.

WHAT THIS BINDS. The declared-record-file clause of `SPECIFICATION/contracts.md`
makes a GENERATED record file's correct content "its generator's output over the
tree it sits in, so a conflict in it is never resolved by merging its text, on
any route", requires a refreshing stage to "run the file's generator over that
tree and write its output as the resolution", requires a refresh-repair brief
whose conflicted paths include one to "carry one line `regenerate: <path> via
<generator argv>` per such file", and requires the same line beside a failed gate
target naming one. The behaviour itself is produced by the graph's own command
scripts against a RELEASED payload, which Scenario 54 puts beyond any sandbox
capability — so the work-item captures all three on an operator host. What is
left for this tier is the committed TEXT: whether the two refreshing nodes reach
the resolution at all, whether the head check precedes the gate it must precede,
and whether the `fix` prompt tells a turn to RUN the generator rather than merge
the register.

WHY THE MEASUREMENT MATTERS. Observed 2026-10-22 on `livespec-dev-tooling-ltkxq2`
(chase-master re-run 01M5GWSFZPN6, hp, build b63a9548019c): `pr_refresh` →
`refresh_repair` → `fix` → `needs_human` in ten minutes. The pull request and the
default branch had both edited `tests/heading-coverage-debt.json`, which
`just generate-heading-coverage-debt-register` generates from
`tests/heading-coverage.json`. The `fix` stage resolved the conflict BY HAND and
lost the two rows master had added for newly ratified scenarios;
`check-heading-coverage-debt-register` then failed, and the stage ended
`needs_human` blaming an "inherited master failure" on a master that was green.
Three chase-master re-runs hit the same class that day.

A GRAPH-AND-PROMPT TEST because both halves are discharged out of committed
prose: the resolution is a shell route inside a node `script`, and the repair
instruction is read by the `fix` AGENT. Nothing host-side observes either, and
the resulting loss surfaces as a red register check on the repaired head, which
reads as somebody else's failure.

THE SUBJECTS ARE DERIVED, NOT SPELLED. The nodes are located by name in the
committed graph and the prompt by the `fix` node's own `prompt=` attribute, so a
node re-pointed at another prompt file does not leave these cases passing about a
file nothing dispatches. Every spelling the shell must agree with the Dispatcher
on — the program's filename, the sandbox plugins root, the gate target and the
brief label — is read from the module that OWNS it rather than typed a second
time here, because a literal here would keep passing after the owner changed and
the disagreement it hid lands in a sandbox.

POLARITY IS PINNED POSITIVELY. Each case asserts the sentence or the token that
GRANTS the behaviour, and the one prohibition the prompt carries is asserted as
the prohibition's own words. A probe for the absence of a phrase passes against a
prompt that says nothing at all.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_regeneration import (
    GENERATED_RECORD_FILE_GATE_TARGET,
    RECORD_FILE_BRIEF_FILENAME,
    RECORD_FILE_PROGRAM_FILENAME,
    RECORD_FILE_TARGETS_FILENAME,
    REGENERATE_BRIEF_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DIR = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_PROMPTS_DIR = _WORKFLOW_DIR / "prompts"
_GRAPH = _WORKFLOW_DIR / "workflow.fabro"

# A graph node block is `<name> [` on its own line through a closing `]` on its
# own line. Edge declarations carry their attributes inline on ONE line, so this
# shape cannot match an edge. Same reader as the sibling prompt modules.
_NODE_BLOCK = re.compile(
    r"^[ \t]*(?P<name>\w+)[ \t]*\[$(?P<body>.*?)^[ \t]*\]$",
    re.DOTALL | re.MULTILINE,
)
_SCRIPT_ATTR = re.compile(r'^\s*script="(?P<script>.*)"$', re.MULTILINE)
_PROMPT_ATTR = re.compile(r'prompt="@prompts/(?P<file>[\w.-]+\.md)"')

_FIX_NODE = "fix"
_REFRESHING_NODES = ("publish_draft", "pr_refresh")

# The per-repository DECLARATION the gate is invoked through. The head check must
# precede it, and asserting the ORDER against this token rather than against a
# recipe name is what keeps the case repository-agnostic.
_DECLARED_GATE = "livespec_declared_gate"
_CHECK_HEAD = "--check-head"
_RESOLVE = "--resolve"
_BRIEF = "--brief"

# The `fix` prompt's two halves: the instruction that the named file is resolved
# by RUNNING its generator, and the prohibition that closes the hand merge.
_REGENERATE_INSTRUCTION = (
    "**A `regenerate:` line in the brief is an instruction, not a hint.**",
    "running exactly that argv from the repository root and committing whatever it",
    "Resolve",
    "every OTHER conflicted path first",
)
_HAND_MERGE_PROHIBITION = (
    "NEVER edit such a file's text, and never merge its conflicted",
    'hunks — not even "carefully", and not even when the merge looks obvious.',
    "correct content is its generator's output over the integrated tree, so a hand",
    "merge keeps whichever rows you chose and silently drops the rest",
)


def _node_scripts() -> dict[str, str]:
    """Every graph node's `script` attribute, decoded to the shell it runs.

    Decoded rather than matched raw, because every quote and newline inside the
    attribute is escaped and a raw needle would have to carry the escaping — an
    instrument that stops matching the moment an unrelated edit changes how a
    neighbouring character is escaped.
    """
    graph = _GRAPH.read_text(encoding="utf-8")
    found: dict[str, str] = {}
    for block in _NODE_BLOCK.finditer(graph):
        attr = _SCRIPT_ATTR.search(block.group("body"))
        if attr is None:
            continue
        found[block.group("name")] = (
            attr.group("script")
            .replace("\\\\", "\x00")
            .replace('\\"', '"')
            .replace("\\n", "\n")
            .replace("\x00", "\\")
        )
    return found


_NODE_SCRIPTS = _node_scripts()


def _fix_prompt_text() -> str:
    graph = _GRAPH.read_text(encoding="utf-8")
    named = [
        attr.group("file")
        for block in _NODE_BLOCK.finditer(graph)
        if block.group("name") == _FIX_NODE
        for attr in [_PROMPT_ATTR.search(block.group("body"))]
        if attr is not None
    ]
    assert len(named) == 1, named
    return (_PROMPTS_DIR / named[0]).read_text(encoding="utf-8")


def test_the_derivation_found_both_refreshing_nodes_and_the_fix_prompt() -> None:
    """The control. Every case below reads a script this derivation produced.

    Without it a reader that matched no node at all would make each absence
    assertion below vacuous and each presence assertion fail for the wrong
    reason — and the two are not distinguishable from a needle's own verdict.
    """
    for node in _REFRESHING_NODES:
        assert node in _NODE_SCRIPTS, sorted(_NODE_SCRIPTS)
        assert "git rebase" in _NODE_SCRIPTS[node]
        assert _DECLARED_GATE in _NODE_SCRIPTS[node]
    assert "refresh-repair brief" in _fix_prompt_text()


@pytest.mark.parametrize("node", _REFRESHING_NODES)
def test_a_refreshing_stage_resolves_the_program_the_dispatcher_materializes(
    node: str,
) -> None:
    """Both stages reach the ONE resolution, through the ONE plugins root.

    The filename and the root are read from their owning modules rather than
    typed here, because a node resolving a different root than the prepare pass
    finds no program at all — and that failure reads as a Dispatcher that never
    materialized one, which points at the wrong half of the seam.
    """
    script = _NODE_SCRIPTS[node]
    assert RECORD_FILE_PROGRAM_FILENAME in script
    assert sandbox_plugins_root_expansion() in script
    assert RECORD_FILE_BRIEF_FILENAME in script


@pytest.mark.parametrize("node", _REFRESHING_NODES)
def test_a_conflict_brief_asks_for_the_regenerate_lines_before_routing_to_repair(
    node: str,
) -> None:
    """The brief the `fix` turn reads carries the generator for every named file.

    Scenario 238's second behaviour. A brief naming the conflicted register
    without its generator leaves the turn to merge the register's text, which is
    the loss this scenario exists to stop — and the turn's hand merge then looks
    like an ordinary conflict resolution in every record of it.
    """
    script = _NODE_SCRIPTS[node]
    asked = script.index(_BRIEF)
    routed = script.index("conflicted-paths")
    assert asked < routed, script[asked : routed + 40]
    assert 'repair_extra="${6:-}"' in script
    assert 'if test -n "$repair_extra"; then' in script


def test_a_conflicted_generated_record_file_is_regenerated_rather_than_repaired() -> None:
    """Scenario 238's first behaviour: the rebase itself reaches the resolution.

    `pr_refresh` rebases through a wrapper that hands each conflicted set to the
    resolution and continues the rebase when it succeeds, so a conflict confined
    to declared generated record files completes the refresh and counts NO
    refresh-repair round. A stage that asked only on the repair route would
    always spend a round, which the clause forbids outright.
    """
    script = _NODE_SCRIPTS["pr_refresh"]
    assert "livespec_regenerating_rebase" in script
    assert f"livespec_record_file {_RESOLVE}" in script
    assert "git rebase --continue" in script
    # The repair counter is the observable: the resolution route must not pass
    # through the helper that increments it.
    resolved = script.index(f"livespec_record_file {_RESOLVE}")
    assert "livespec-refresh-repair-count" not in script[:resolved]


def test_the_head_check_runs_before_the_repository_declared_gate() -> None:
    """Scenario 238's third behaviour, and its ORDER is the whole assertion.

    A hand-merged register fails the repository's own register check, so a head
    check placed AFTER the declared gate would never be reached: the gate would
    have failed first, with the repository's target rather than
    `generated-record-file:<path>`, and the finding would read as the
    repository's own breakage on a head the refresh produced.
    """
    script = _NODE_SCRIPTS["pr_refresh"]
    checked = script.index(_CHECK_HEAD)
    gated = script.index(f"gate_out=$({_DECLARED_GATE}")
    assert checked < gated, script[checked : gated + 60]
    assert RECORD_FILE_TARGETS_FILENAME in script
    assert "failed-gate-targets" in script[checked:]


def test_the_gate_target_and_brief_label_are_the_ratified_spellings() -> None:
    """One spelling each, owned by one module, read by the program and the prompt.

    The `fix` turn matches the brief label and the gate target out of prose, so a
    second spelling anywhere makes the instruction unreachable for exactly the
    files it was written for — while every record of the turn still reads as a
    brief that named no generated file.
    """
    assert GENERATED_RECORD_FILE_GATE_TARGET == "generated-record-file"
    assert REGENERATE_BRIEF_LABEL == "regenerate"
    prompt = _fix_prompt_text()
    assert f"`{REGENERATE_BRIEF_LABEL}: <path> via <generator argv>`" in prompt
    assert f"`{GENERATED_RECORD_FILE_GATE_TARGET}:<path>`" in prompt


@pytest.mark.parametrize("needle", _REGENERATE_INSTRUCTION)
def test_the_fix_prompt_directs_the_turn_to_run_the_generator(needle: str) -> None:
    """The instruction is stated AT the refresh-repair steps the turn executes.

    Each needle sits within one physical line of the hard-wrapped prose, because
    a needle straddling a line break fails while the prompt says exactly the
    thing — a probe that can only fail silently.
    """
    assert needle in _fix_prompt_text()


@pytest.mark.parametrize("needle", _HAND_MERGE_PROHIBITION)
def test_the_fix_prompt_forbids_merging_a_generated_record_files_text(
    needle: str,
) -> None:
    """The prohibition carries its own reason, because the hand merge looks correct.

    The measured turn resolved the conflict competently by every ordinary
    standard and still lost two rows: the register derives from a registry the
    merge had already resolved, so nothing in the conflicted hunks shows what is
    missing. A prohibition stated without that reason is one a turn under
    pressure reads as advice.
    """
    assert needle in _fix_prompt_text()
