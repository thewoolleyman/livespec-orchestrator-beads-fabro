"""Mechanical control: nothing opens the journal path for append but the layer.

The journal invoker attribution contract in `SPECIFICATION/contracts.md`
requires EVERY journal write to route through the append layer
(`_dispatcher_journal_file.JournalFile`, re-exported from `_dispatcher_io`),
because the stamped-once `invoker` / `invoker_source` guarantee governs only
what that layer actually writes. A writer that opens the journal path itself
produces a record with no attribution and no timestamp, and — this is the part
that makes a mechanical control worth having — the resulting journal looks
entirely normal. Two shipped writers did exactly that until this contract
landed, and nothing surfaced it.

So the control is structural rather than behavioural: it parses every
first-party module and refuses any append-mode `open` whose target expression
names the journal. It cannot be satisfied by a test double or a passing dispatch
— only by there being no such call site.

Scope note, because an absence claim is only as good as the population it
searched: the scan covers every `.py` under the plugin's own package tree
(`_vendor/` excluded, since vendored code is read-only and writes no journal of
ours), and it is keyed on the RECEIVER EXPRESSION rather than the mode alone —
appending to a spans file or a sink is legitimate and is not a journal write.
The positive control below proves the scan can return a hit at all, so a green
run means "no journal-append bypass exists", never "the scan found nothing
because it could not look".
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_ROOT = _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro"
# The one module that IS the append layer, and therefore the one module allowed
# to open the journal path for append. It moved out of `_dispatcher_io` into its
# own leaf when the overflow-selection record became a writer that also resolves
# a dispatch factory — the aggregate's import closure reaches the factory-ledger
# resolution, so such a writer could not import it. Re-pointing rather than
# widening keeps the exclusion exactly one module wide: `_dispatcher_io` is now
# SCANNED, which is strictly stricter than before.
_APPEND_LAYER = _PACKAGE_ROOT / "commands" / "_dispatcher_journal_file.py"
_JOURNAL_TOKEN = "journal"
_APPEND_MODES = ("a", "ab", "a+", "at")


def _append_open_targets(*, source: str) -> list[str]:
    """Unparsed receiver expression of every append-mode `open` call in `source`.

    Covers BOTH spellings: the `Path.open("a")` method form and the builtin
    `open(path, "a")` form. Missing either would leave a bypass route the
    control cannot see, which is the failure mode this whole module exists to
    close.
    """
    targets: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        target = _append_target(call=node)
        if target is not None:
            targets.append(target)
    return targets


def _append_target(*, call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "open":
        return ast.unparse(func.value) if _is_append_mode(args=call.args, index=0) else None
    if (
        isinstance(func, ast.Name)
        and func.id == "open"
        and _is_append_mode(args=call.args, index=1)
    ):
        return ast.unparse(call.args[0])
    return None


def _is_append_mode(*, args: list[ast.expr], index: int) -> bool:
    if len(args) <= index:
        return False
    mode = args[index]
    return isinstance(mode, ast.Constant) and mode.value in _APPEND_MODES


def _journal_append_bypasses() -> list[str]:
    bypasses: list[str] = []
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        if path == _APPEND_LAYER:
            continue
        source = path.read_text(encoding="utf-8")
        bypasses.extend(
            f"{path.relative_to(_REPO_ROOT).as_posix()}: {target}"
            for target in _append_open_targets(source=source)
            if _JOURNAL_TOKEN in target.lower()
        )
    return bypasses


def test_no_module_outside_the_append_layer_opens_the_journal_for_append() -> None:
    assert _journal_append_bypasses() == []


def test_the_append_layer_itself_is_the_one_journal_append_site() -> None:
    """The chokepoint exists where the control claims it does."""
    targets = _append_open_targets(source=_APPEND_LAYER.read_text(encoding="utf-8"))
    assert targets == ["self.path"]


def test_the_scan_reports_a_bypass_when_one_is_present() -> None:
    """Positive control: the instrument CAN return a hit.

    Without this, a green suite is equally consistent with "no bypass exists"
    and with "the matcher can never match" — the two readings a mechanical
    absence claim must be able to tell apart.
    """
    method_form = "journal.path.open('a', encoding='utf-8')"
    builtin_form = "open(journal_path, 'a')"
    assert _append_open_targets(source=method_form) == ["journal.path"]
    assert _append_open_targets(source=builtin_form) == ["journal_path"]


def test_the_scan_ignores_reads_and_non_journal_appends() -> None:
    """A spans/sink append and a journal READ are both legitimate, not bypasses."""
    assert _append_open_targets(source="spans_path.open('a', encoding='utf-8')") == ["spans_path"]
    assert _append_open_targets(source="journal.path.open('r', encoding='utf-8')") == []
    assert _append_open_targets(source="journal.path.open()") == []
