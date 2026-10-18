"""The MiniJinja literal escaper is a cohesive module, not a guest of the overlay.

WHY THIS SPLIT, AND WHY NOW (bd-ib-tlmq3m). `_dispatcher_overlay` renders a run
config; `escape_minijinja_literal` neutralizes template syntax in untrusted prose.
Those are two concerns, and that module's own docstring said so -- it opened
"Run-config overlay rendering (plus MiniJinja literal escaping)" and then explained
that the escaper was merely "hosted" there. The overlay renders NONE of its own
output through the escaper: all three callers (`_dispatcher_goal`,
`_dispatcher_preserve_reference_body`, and `_dispatcher_plan`'s re-export) import it
and nothing inside the overlay does, so the seam is as clean as a seam gets.

The occasion is the sandbox worktree-pack prepare step this work-item adds, which
the overlay has to render and had no room for: `_dispatcher_overlay` measured 247
LLOC against the 250 hard ceiling, and the wiring is five lines. Per AGENTS.md
section "Refactoring for size", the honest answer to a file at its ceiling is to
decompose it by COHESION rather than to shave its line count -- so the guest
concern moves out, and the overlay keeps the one it is named for.

NO RE-EXPORT SHIM. The same section bans one, so every caller imports from the new
home and `_dispatcher_overlay` no longer carries the name at all. The absence
assertions below are what make that checkable: a shim left behind would satisfy
every positive assertion here while leaving the overlay exactly as large as it was,
which is the one outcome this split must not have.

THE IMPORTLIB PATTERN is the repository's established form for an extract-to-a-new-
module slice (AGENTS.md section "Red-Green-Replay"): the module is imported INSIDE
the test body and the first assertion is a genuine `is_file()` check on the path the
module must occupy, so the Red fails on an assertion rather than dying at collection
with a `ModuleNotFoundError` that proves only unimportability.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_overlay

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = f"{_PACKAGE}._dispatcher_minijinja_escape"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_minijinja_escape.py"
)
_ESCAPER = "escape_minijinja_literal"
# The three OPENING delimiters MiniJinja's lexer enters template mode at, each
# paired with the text the escaper must render it as. A closing delimiter and every
# other character are inert outside a tag, which is why only openers appear here.
_OPENERS = (
    ("{{ goal }}", '{{ "{{" }} goal }}'),
    ("{% if x %}", '{{ "{%" }} if x %}'),
    ("{# note #}", '{{ "{#" }} note #}'),
)


def test_the_escaper_has_its_own_module_and_that_module_is_its_whole_surface() -> None:
    """The new home exists, exports exactly the escaper, and still escapes.

    The behaviour assertions are carried HERE rather than left to the callers'
    tests because a move is only a move if the moved code still does its job: an
    extraction that dropped the `{%` or `{#` arm would leave a template-injection
    surface open while every import in the tree resolved perfectly.
    """
    assert _MODULE_PATH.is_file(), f"the escaper has no cohesive home at {_MODULE_PATH}"

    module = importlib.import_module(_MODULE)

    assert set(module.__all__) == {_ESCAPER}
    for text, expected in _OPENERS:
        assert module.escape_minijinja_literal(text=text) == expected


def test_the_overlay_no_longer_carries_the_escaper_at_all() -> None:
    """The guest concern LEFT; it was not copied, and no shim stands in for it.

    `hasattr` is the load-bearing half: dropping the name from `__all__` while
    keeping the definition or an import of it would buy the overlay no room, and
    room is the whole reason this split happened.
    """
    assert _ESCAPER not in _dispatcher_overlay.__all__
    assert not hasattr(_dispatcher_overlay, _ESCAPER)
