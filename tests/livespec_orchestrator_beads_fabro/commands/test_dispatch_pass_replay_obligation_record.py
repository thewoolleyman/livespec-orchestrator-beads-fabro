"""What the v127 deletion site may and may not CLAIM about the replay obligation.

Binds the surviving design record at the one place work-item `bd-ib-qm6r1`
deleted a call site inside `_dispatcher_reconcile_runs`, against
`SPECIFICATION/contracts.md` — cited at FILE level, because a heading-level
citation rots the moment the heading is reworded. That revision lists TWO
separate obligations in one paragraph: that "the per-node selection record ...
and the `provider-limit-release` record are the authoritative fallback history",
and, separately, that "Reconciliation MUST replay selection-to-execution
observation idempotently using factory, run, node attempt, and selection
identity".

THE SECOND OBLIGATION IS NOT DISCHARGED AT THAT SITE, and the comment left in
place of the deletion claimed it was — naming `reconcile_one_run` as the
function that performs it. That function disposes ORPHAN runs and names no
selection, fallback or release at all; `dispose_provider_limit_release` is
reached only from `_dispatcher_terminal_routing`, on the DISPATCH terminal path,
which reconciliation never enters.

WHY A COMMENT IS WORTH A TEST HERE. This comment is the only surviving design
record at the exact site of a contract-relevant deletion, so it is what the next
reader auditing v127 conformance finds. A false "already discharged" there is
the confident-wrong-answer-that-forecloses-the-action class: nothing downstream
re-tests a conclusion that the obligation is met, and the live risk is that the
follow-on half of v127 (`bd-ib-augqc2`) is closed as already-covered on the
strength of it.

THE CONTROL IS THE MEASUREMENT THAT MAKES THE CLAIM FALSE, and it is what gives
the two prose assertions their meaning: a module that happened to carry neither
word would satisfy them while saying nothing about where the leg actually runs.
It reads the importers through `ast` rather than as text, because the one module
that mentions `dispose_provider_limit_release` WITHOUT importing it mentions it
in a comment — and a text scan counting that comment reports a second caller
that does not exist.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_DELETION_SITE = _COMMANDS / "_dispatcher_reconcile_runs.py"
_ORPHAN_DISPOSAL = _COMMANDS / "_dispatcher_reconcile_one_run.py"

# The clause's own words for the obligation, which is how the block carrying the
# design record is located rather than by line number — a line number in a test
# is wrong the first time anything above it is edited.
_OBLIGATION_PHRASE = "selection-to-execution"
_RELEASE_SYMBOL = "dispose_provider_limit_release"
_ONLY_CALLER = "_dispatcher_terminal_routing"
_FOLLOW_ON_ITEM = "bd-ib-augqc2"


def _comment_block_naming(*, source: str, needle: str) -> str:
    """The one contiguous `#`-comment block containing `needle`.

    Contiguous rather than whole-file, because the claim under test is about the
    record AT the deletion site: a whole-file read would be satisfied by a build
    that moved the false attribution into some other comment in the same module.
    """
    blocks: list[list[str]] = []
    open_block: list[str] | None = None
    for line in source.splitlines():
        if line.strip().startswith("#"):
            if open_block is None:
                open_block = []
                blocks.append(open_block)
            open_block.append(line.strip())
            continue
        open_block = None
    carrying = ["\n".join(block) for block in blocks if needle in "\n".join(block)]
    assert len(carrying) == 1, f"expected exactly one comment block naming {needle!r}"
    return carrying[0]


def test_the_deletion_site_does_not_attribute_the_replay_obligation_to_the_orphan_disposal() -> (
    None
):
    """`reconcile_one_run` disposes orphans; it performs no release leg."""
    block = _comment_block_naming(
        source=_DELETION_SITE.read_text(encoding="utf-8"), needle=_OBLIGATION_PHRASE
    )

    assert "reconcile_one_run" not in block


def test_the_deletion_site_names_the_item_that_re_sources_the_replay_obligation() -> None:
    """A reader told only that the old replay is gone is stranded, not routed."""
    block = _comment_block_naming(
        source=_DELETION_SITE.read_text(encoding="utf-8"), needle=_OBLIGATION_PHRASE
    )

    assert _FOLLOW_ON_ITEM in block


def test_the_orphan_disposal_names_no_selection_fallback_or_release() -> None:
    """The control: the measurement the false attribution contradicted."""
    source = _ORPHAN_DISPOSAL.read_text(encoding="utf-8").casefold()

    assert [
        word
        for word in ("selection", "fallback", "provider_limit", "provider-limit", "release")
        if word in source
    ] == []


def test_the_release_leg_is_imported_only_by_the_dispatch_terminal_path() -> None:
    """The control's other half: reconciliation never reaches that symbol."""
    importers = sorted(
        path.stem
        for path in sorted(_COMMANDS.glob("*.py"))
        if _RELEASE_SYMBOL
        in {
            alias.name
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
    )

    assert importers == [_ONLY_CALLER]
