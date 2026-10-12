"""The title and body the scripted `pr` stage applies, rendered HOST-side as data.

WHY THIS MODULE EXISTS. `SPECIFICATION/contracts.md` section
"Definition-of-Done and Proof-of-Done stages" -> "Scripted publication and
proof-head integrity" requires `pr` to "apply the Dispatcher-rendered title and
body", and the named-workflow-variants clause fixes the transport: "Title and
body are transported as run-scoped environment data (`LIVESPEC_PR_TITLE` and a
sandbox-readable `LIVESPEC_PR_BODY_FILE`), not new `inputs.*` tokens".

Before this module nothing produced either value. The retired ACP `pr` prompt
composed them inside the agent turn, and when publication became a command stage
the shaping was dropped rather than retained: the stage fell back to the publish
BRANCH NAME as its title and left `publish_draft`'s placeholder body ("Draft
opened by the publish_draft stage so the Proof of Done record can be captured on
it") in place permanently. Both fallbacks were silent -- no sentinel, no stderr
line, exit 0 -- so the regression was invisible on every run record.

WHY THE TITLE RIDES THE ENV TABLE AND THE BODY RIDES A FILE. A title is one
short line and an environment variable carries it exactly. A body is many lines
of ledger prose, and the stage hands it to `gh pr edit --body-file`, which wants
a path -- so the body is MATERIALIZED into the sandbox by a prepare step and the
stage reads the file.

WHY THE BODY PATH IS NOT PROJECTED AS AN ENV VALUE, which is the one choice here
most likely to read as an oversight. The file lands below the sandbox plugins
root, and that root is NOT KNOWN HOST-SIDE -- it is the sandbox's own `$HOME`
unless the image overrides it -- while the pinned engine does not expand
`${...}` inside an `[environments.*.env]` value, so a projected path would reach
the node as the literal dollar-brace string. `_dispatcher_sandbox_plugins`
records that measurement, and the three helpers already materialized below that
root (the plugin-cache gate, the publication-head reader, the exact-head push
program) all resolve it the same way: by shell expansion at the point of use. So
`LIVESPEC_PR_BODY_FILE` remains the channel the clause names and the stage's
override, and its DEFAULT is the expansion of where this module's step writes.

WHY NOTHING HERE IS MINIJINJA-ESCAPED. Item prose reaching the run GOAL is
escaped (`escape_minijinja_literal`), because fabro renders the goal through
MiniJinja. The run CONFIG is different, and the difference is measured:
`_substitute_input_tokens` records that fabro 0.254.0 renders `inputs.*` in graph
node attributes and "leaves `run.prepare` commands verbatim". A `{{` in a
work-item title is therefore inert in this table, and escaping it would corrupt
the title the maintainer reads on the pull request.

WHY THE BODY TRAVELS BASE64 RATHER THAN IN A HEREDOC. The prepare step is one
shell command and the body is arbitrary ledger prose. A quoted heredoc expands
nothing, but a body line equal to the delimiter closes it early and the tail
becomes shell -- a content-dependent hazard with no safe delimiter, since the
delimiter would itself be the thing to avoid writing about. The base64 alphabet
is `A-Za-z0-9+/=` and nothing else, so an encoded payload is single-quotable
with no escaping at all and no property of the body can reach the shell.
`_assert_shell_safe` HOLDS that invariant rather than trusting it.

BOTH VALUES ARE BOUNDED, and neither bound is cosmetic. The forge REJECTS an
over-long title, which would fail the stage closed on a value that changes
nothing about the work. And a prepare step is one `execve` argument, so an
oversized one kills the run in setup with "argument list too long" before any
work -- `_dispatcher_gh_refresh.MAX_PREPARE_STEP_BYTES` records that incident.
Truncation is NAMED in the rendered text rather than silent, because a body that
stops mid-criterion otherwise reads as a ledger record that was itself truncated.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "PR_BODY_FILE_ENV_VAR",
    "PR_TITLE_ENV_VAR",
    "PUBLICATION_BODY_FILENAME",
    "PUBLICATION_BODY_MARKER",
    "PUBLICATION_BODY_MAX_BYTES",
    "PUBLICATION_TITLE_MAX_CHARS",
    "PublicationMetadata",
    "publication_body_path_expansion",
    "publication_metadata_env_lines",
    "publication_metadata_for",
    "publication_metadata_prepare_steps_block",
]

PR_TITLE_ENV_VAR = "LIVESPEC_PR_TITLE"
PR_BODY_FILE_ENV_VAR = "LIVESPEC_PR_BODY_FILE"

PUBLICATION_BODY_FILENAME = "livespec-pr-body.md"

# The forge's own pull-request title ceiling.
PUBLICATION_TITLE_MAX_CHARS = 256

# Well under both the forge's body ceiling and the per-prepare-step `execve`
# bound: base64 inflates by 4/3, so 30000 bytes of body is a ~40000-character
# payload inside a ~96000-byte step limit. Generous for a title plus a
# Definition of Done, and nowhere near the limit that destroys a run.
PUBLICATION_BODY_MAX_BYTES = 30000

# Emitted on stdout by the step, so a run's setup log says the body landed. A
# step that wrote nothing is otherwise indistinguishable from one that never
# ran, and the stage's own absent-body sentinel fires much later.
PUBLICATION_BODY_MARKER = "LIVESPEC_PR_BODY_MATERIALIZED"

_TRUNCATION_NOTE = (
    "\n\n_[The Dispatcher truncated this body at "
    f"{PUBLICATION_BODY_MAX_BYTES} bytes. The work-item record is authoritative.]_\n"
)

_NO_CRITERIA = (
    "This work-item records no acceptance criteria. Its Definition of Done is "
    "the work-item record itself."
)

_B64_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")


@dataclass(frozen=True, kw_only=True)
class PublicationMetadata:
    """One dispatch's rendered publication metadata.

    A value rather than two loose strings, because the overlay threads them
    through two separate projections -- an env line and a prepare step -- and a
    dispatch rendering one without the other is the half-applied state this
    module exists to retire.
    """

    title: str
    body: str


def _bounded_title(*, title: str, work_item_id: str) -> str:
    """`<title> (<id>)`, within the forge ceiling, keeping the id.

    The id is what makes the pull request findable from the ledger and the
    ledger findable from the pull request, so when something has to go it is the
    prose. A title so long that even the id does not fit is truncated whole
    rather than special-cased: nothing useful survives either way.
    """
    suffix = f" ({work_item_id})"
    budget = PUBLICATION_TITLE_MAX_CHARS - len(suffix)
    if budget <= 0:
        return f"{title}{suffix}"[:PUBLICATION_TITLE_MAX_CHARS]
    return f"{title[:budget].rstrip()}{suffix}"


def _bounded_body(*, body: str) -> str:
    """The body within its byte bound, with any truncation NAMED in the text.

    Measured in BYTES rather than characters, because the bound that matters is
    the `execve` argument the encoded payload rides. `errors="ignore"` on the
    decode is what keeps a cut landing mid-codepoint from raising: the note that
    follows says the text was truncated, so a dropped partial character is
    already covered by what the reader is told.
    """
    if len(body.encode()) <= PUBLICATION_BODY_MAX_BYTES:
        return body
    keep = PUBLICATION_BODY_MAX_BYTES - len(_TRUNCATION_NOTE.encode())
    return body.encode()[:keep].decode(errors="ignore") + _TRUNCATION_NOTE


def publication_metadata_for(*, item: WorkItem) -> PublicationMetadata:
    """Render one work-item's pull-request title and body.

    PURE, and deliberately a CLOSED shape rather than free prose: the body
    carries the item's identity, its acceptance criteria verbatim, and a pointer
    to where the Proof of Done records live. It copies no proof content and
    asserts nothing about the work -- a pull-request body is a reader's
    orientation, and every claim about the change belongs to the records on the
    pull request and to the commits.

    The criteria ride VERBATIM because they are what a reviewer grades the pull
    request against; a reformatted copy would present the Dispatcher's
    paraphrase as the item's own. An item with none SAYS so, rather than leaving
    a section containing nothing, which reads as a body that lost its contents.
    """
    criteria = (item.acceptance_criteria or "").strip() or _NO_CRITERIA
    body = (
        f"Work-item `{item.id}` — {item.title}\n"
        "\n"
        "## Definition of Done\n"
        "\n"
        f"{criteria}\n"
        "\n"
        "---\n"
        "\n"
        "Published by this repository's factory dispatch. The Proof of Done\n"
        "records for each assertion above are comments on this pull request.\n"
        "\n"
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)\n"
    )
    return PublicationMetadata(
        title=_bounded_title(title=item.title, work_item_id=item.id),
        body=_bounded_body(body=body),
    )


def publication_body_path_expansion() -> str:
    """The path both the prepare step and the `pr` stage resolve.

    One spelling, for the reason `_dispatcher_sandbox_plugins` gives: a stage
    resolving a different path than the step that wrote the file finds no file
    and reports it as an absent body -- a diagnosis that names the wrong half of
    the seam.
    """
    return f"{sandbox_plugins_root_expansion()}/{PUBLICATION_BODY_FILENAME}"


def _assert_shell_safe(*, payload: str) -> None:
    """Refuse a payload that could break out of its single-quoted shell literal."""
    if not set(payload) <= _B64_ALPHABET:
        msg = "publication body payload carries characters outside the base64 alphabet"
        raise ValueError(msg)


def publication_metadata_env_lines(*, metadata: PublicationMetadata | None) -> str:
    """The `[environments.<id>.env]` line carrying the rendered title.

    Empty for a caller that rendered no metadata -- a direct caller holding no
    work-item -- so such a caller renders exactly the overlay it did before, and
    the stage's own absent-title sentinel reports the shortfall rather than this
    projection inventing a placeholder.

    Only the TITLE is projected. The body's path cannot be an env value (the
    module docstring records why), so the stage resolves it by the same shell
    expansion the prepare step writes to. The value is `json.dumps`-ed for the
    reason every other line in that table is: the table is TOML, and a title
    carrying a quote written raw would terminate the string early and make the
    WHOLE overlay unparseable -- one item's prose turning into a dispatch-wide
    failure.
    """
    if metadata is None:
        return ""
    return f"{PR_TITLE_ENV_VAR} = {json.dumps(metadata.title)}\n"


def publication_metadata_prepare_steps_block(*, metadata: PublicationMetadata | None) -> str:
    """A prepare step that materializes the rendered body inside the sandbox.

    The decode runs under `python3` rather than `base64 -d`: `python3` is already
    a hard dependency of this prepare chain -- the plugin-cache gate executes
    under it -- while `base64` is a coreutils program whose presence in an
    arbitrary sandbox image is one more thing to be wrong about.

    The root is resolved by the SHELL and handed to the interpreter as argv, so
    the expansion has one spelling rather than a shell copy and a Python copy
    that could disagree.
    """
    if metadata is None:
        return ""
    payload = base64.b64encode(metadata.body.encode()).decode("ascii")
    _assert_shell_safe(payload=payload)
    root = sandbox_plugins_root_expansion()
    decode = (
        "import base64, pathlib, sys; "
        "pathlib.Path(sys.argv[1]).write_bytes(base64.b64decode(sys.argv[2]))"
    )
    script = (
        "set -eu\n"
        f'root="{root}"\n'
        'mkdir -p "$root"\n'
        f"python3 -c '{decode}' \"$root/{PUBLICATION_BODY_FILENAME}\" '{payload}'\n"
        f'echo "{PUBLICATION_BODY_MARKER}: $root/{PUBLICATION_BODY_FILENAME}"'
    )
    return (
        "\n# --- Dispatcher-materialized pull-request body: the `pr` stage applies\n"
        "# --- it with `gh pr edit --body-file`, as DATA rather than shell ---\n"
        "[[run.prepare.steps]]\n"
        f"script = {json.dumps(script)}\n"
    )
