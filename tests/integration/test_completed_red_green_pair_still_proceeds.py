"""A stage that ends normally with a completed Red-Green pair still proceeds.

Binds the THIRD Definition-of-Done assertion of work-item `bd-ib-qhv7qs`: the
ordinary route is unchanged — a `fix` or `review_fix` stage that ends normally
with a completed Red and Green pair at the branch head still checkpoints and
goes on to the janitor exactly as it did before the failure edge and the
open-Red reason existed.

WHY A PRESERVATION ASSERTION GETS ITS OWN MODULE. It is the only one of the
three with nothing to implement, which is precisely what makes it the one most
easily lost: both repairs this item lands are additions to the paths a NORMAL
stage also travels, and each has an obvious over-reaching form that satisfies
the other two assertions while breaking this one. A failure edge added by
CONSUMING the unconditional fallthrough routes the timeout correctly and makes
the graph one `fabro validate` rejects outright. An open-Red clause keyed on the
presence of Red trailers alone — rather than on the ABSENCE of the Green —
names an open Red on every completed pair, and since a completed pair is what
every healthy stage leaves, that misreading is the common case rather than the
edge case.

THE THREE FACTS ARE ASSERTED AS A COMPOSITION, and that is the point rather
than a redundancy. Each is independently a control in a sibling module — the
fallthrough in `test_fix_stage_failure_routes_to_needs_human`, the completed-pair
silence in `test_open_red_needs_human_reason`, the checkpoint declaration in
`tests/test_factory_checkpoint_declaration` — because each is the discriminator
that makes that module's own positive case evidence. What none of them asserts
is the ORDINARY JOURNEY: that a stage which ends normally still has a route
onward, still leaves a tree the engine can checkpoint, and still says nothing
about an open Red. A build can hold any two of those and break the third.

The checkpoint half is read as the DECLARATION the engine resolves rather than
as an executed commit: this tier spawns no engine, and `skip_git_hooks` plus a
budget generously above the stock thirty seconds are exactly what "still
checkpoints" reduced to after `bd-ib-jb53pu` — a checkpoint commit that no
repository gate can refuse, which is the condition the 27 measured hp run
deaths of 2026-10-09..12 violated.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_WORKFLOW_DIR = Path(".claude-plugin/.fabro/workflows/implement-work-item")
_WORKFLOW_DOT = _WORKFLOW_DIR / "workflow.fabro"
_WORKFLOW_TOML = _WORKFLOW_DIR / "workflow.toml"
_ORDINARY_ROUTES = (("fix", "janitor"), ("review_fix", "janitor"))
_GENERIC_REASON = "loop cannot auto-resolve this work-item"
_OPEN_RED_CLAUSE = "open Red commit"
_GREEN_TRAILER_KEY = "TDD-Green-Verified-At:"
# The stock engine budget a hook-free commit has already been measured to
# cross (ledger bd-ib-6ka), so the declared one has to sit well above it.
_STOCK_CHECKPOINT_SECONDS = 30
_EDGE_RE = re.compile(r"^(?P<source>\w+)\s*->\s*(?P<target>\w+)\s*(?:\[(?P<attrs>.*)\])?$")


def _code_lines() -> list[str]:
    text = _WORKFLOW_DOT.read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if not line.strip().startswith("//")]


def _terminal_script() -> str:
    """The needs-human terminal's own script, unescaped from the committed attribute."""
    text = _WORKFLOW_DOT.read_text(encoding="utf-8")
    node = re.search(r"^\s*needs_human\s*\[(?P<body>.*?)^\s*\]", text, re.DOTALL | re.MULTILINE)
    assert node is not None
    script = re.search(r'script="(?P<script>(?:[^"\\]|\\.)*)"', node.group("body"))
    assert script is not None
    return re.sub(r"\\(?P<escaped>.)", r"\g<escaped>", script.group("script"))


def _checkpoint() -> dict[str, Any]:
    """The shipped `[run.checkpoint]` table, parsed as the engine parses it."""
    import tomli

    document: dict[str, Any] = tomli.loads(_WORKFLOW_TOML.read_text(encoding="utf-8"))
    checkpoint: dict[str, Any] = document["run"]["checkpoint"]
    return checkpoint


def test_a_normally_ended_stage_still_has_an_unconditional_route_onward() -> None:
    """The ordinary route survives the failure edge, and still targets the janitor."""
    for source, ordinary in _ORDINARY_ROUTES:
        onward = [
            match.group("target")
            for line in _code_lines()
            if (match := _EDGE_RE.match(line)) is not None
            and match.group("source") == source
            and "condition=" not in (match.group("attrs") or "")
        ]
        assert onward == [ordinary], source


def test_the_terminal_reads_the_absence_of_the_green_and_not_the_red_alone() -> None:
    """Keyed on the Green's absence, so a completed pair can never read as an open Red."""
    script = _terminal_script()

    assert _GREEN_TRAILER_KEY in script
    assert f"! printf '%s\\n' \"$head_message\" | grep -qF '{_GREEN_TRAILER_KEY}'" in script
    assert _GENERIC_REASON in script
    assert _OPEN_RED_CLAUSE in script


def test_the_engine_checkpoint_still_runs_and_no_repository_gate_can_refuse_it() -> None:
    """`skip_git_hooks` holds and the budget stays well above the stock thirty seconds."""
    checkpoint = _checkpoint()

    assert checkpoint["skip_git_hooks"] is True
    declared = checkpoint["commit_timeout"]
    assert isinstance(declared, str)
    assert declared.endswith("m")
    assert int(declared.removesuffix("m")) * 60 > _STOCK_CHECKPOINT_SECONDS
