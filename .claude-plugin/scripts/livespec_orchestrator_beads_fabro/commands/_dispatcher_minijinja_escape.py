"""The shared MiniJinja literal escaper every untrusted-prose renderer routes through.

Fabro renders the run goal through MiniJinja, so any prose that reaches a graph
attribute has to be neutralized first. Three callers do that -- the goal brief
(`_dispatcher_goal`), the preserve-by-reference body
(`_dispatcher_preserve_reference_body`), and `_dispatcher_plan`'s re-export of the
name for its own consumers -- and none of them is about rendering a run config.

WHY IT IS NOT IN `_dispatcher_overlay`, which hosted it until bd-ib-tlmq3m. That
module renders a run config and renders NONE of its own output through this
function: the escaper was a guest, as that module's own docstring said in as many
words. The occasion for moving it was the sandbox worktree-pack prepare step, which
the overlay had to render with three LLOC of headroom under its hard ceiling --
and AGENTS.md section "Refactoring for size" makes decomposition by COHESION the
honest answer to a file at its ceiling, never a line-count shave. There is
deliberately no re-export shim in the overlay: the same section bans one, and a
shim would have bought the overlay none of the room the split was for.
"""

from __future__ import annotations

import re

__all__: list[str] = [
    "escape_minijinja_literal",
]

# MiniJinja's three OPENING delimiters: expression `{{`, statement `{%`,
# comment `{#` (fabro v0.254.0 renders the run goal through MiniJinja —
# fabro issue #124 — storing it in the graph's `goal` attribute and
# interpolating it into the prompts as `{{ goal }}`). The lexer only
# enters template mode at one of these openers; closing delimiters and
# every other character are inert outside a tag. Neutralizing every
# opener therefore guarantees arbitrary goal prose cannot alter graph
# semantics regardless of content (work-item livespec-impl-beads-ajv).
_MINIJINJA_OPEN_DELIMITER_RE = re.compile(r"\{\{|\{%|\{#")


def escape_minijinja_literal(*, text: str) -> str:
    """Neutralize MiniJinja syntax in `text` so it renders back verbatim.

    Fabro v0.254.0 renders the run goal through MiniJinja (fabro issue
    #124): the goal lands in the graph's `goal` attribute and is
    interpolated into the prompts as `{{ goal }}`. Untrusted item prose
    containing a literal MiniJinja construct — a `{{ ... }}` expression
    (e.g. justfile recipe syntax), a `{% ... %}` statement, or a
    `{# ... #}` comment — would otherwise re-enter template mode and
    raise `template_undefined_variable` (or worse: this is also a mild
    template-INJECTION surface, since the prose could introduce arbitrary
    template constructs). Three v5k-leg dispatches failed pre-flight this
    way (livespec-wwfu, livespec-runtime-ani, livespec-driver-claude-3bk;
    work-item livespec-impl-beads-ajv).

    MiniJinja's lexer only enters template mode at one of the three
    OPENING delimiters (`{{`, `{%`, `{#`); the closing delimiters and
    every other character (backslashes, quotes, newlines) are inert
    outside a tag. So replacing each opener with the MiniJinja expression
    that emits those two literal characters — `{{` -> `{{ "{{" }}`,
    `{%` -> `{{ "{%" }}`, `{#` -> `{{ "{#" }}` — makes the lexer never
    enter a tag from the original prose, and the inserted expressions
    render back to the exact original characters after one render. This
    transform is self-cancelling by construction: it is correct only when
    the consumer renders exactly once, because that render restores the
    original opener text. This is preferred over a `{% raw %}...{% endraw
    %}` wrapper, which is NOT content-agnostic: a goal containing the
    literal text `{% endraw %}` would close the raw block early and
    re-expose the tail. The single `re.sub` pass does not re-scan its own
    replacement text, so the inserted `{{ ... }}` expressions are never
    themselves neutralized during this transform.
    """
    return _MINIJINJA_OPEN_DELIMITER_RE.sub(
        # The replacement always OPENS with the expression delimiter `{{`
        # (only `{{ ... }}` emits a value) and quotes the matched opener as
        # a string literal: `{{` -> `{{ "{{" }}`, `{%` -> `{{ "{%" }}`,
        # `{#` -> `{{ "{#" }}`. Using the matched opener as the prefix would
        # be wrong — `{%`/`{#` are themselves live openers, not literals.
        lambda match: '{{ "' + match.group(0) + '" }}',
        text,
    )
