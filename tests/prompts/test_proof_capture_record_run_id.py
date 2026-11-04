"""The record header's run id is resolved where the header is WRITTEN.

bd-ib-oa67lv. `proof_capture` authored the header by hand, took the run id from
Step 4's resolution, and wrote it in a LATER AND SEPARATE tool call with
`printf '... run %s ...' "$FABRO_RUN_ID"`. That variable is exported to HOOKS
only and is unset in every agent and script-node shell (established by
bd-ib-bb41.1), so the header's publishing identity field came out as the bare
word `run`. Measured on `livespec-dev-tooling-r6kagr`, run 01M5E8H65Z04: the
record reader treats such a header as NO RECORD, `proof_verify` nonetheless
replayed the body and published `verified`, `review` approved, and
`publication-head` refused three stages later — and a resume restarts at the
FAILED stage, so `proof_capture` never re-ran and the run was unrecoverable.
The agent's own final reply still said the id came "from `$FABRO_RUN_ID`", which
is how the misattribution survived the run.

A prompt test because the header is authored by the agent out of this prose and
is rendered by no Python caller: nothing host-side can observe which source a
turn reached for, and the two mechanical halves that CAN be observed — the
publication-head refusal and the `proof_grade` refusal — both fire only after
the capture has already posted. The prompt is the one place the empty header can
be prevented rather than detected.

The two cases are deliberately about the SAME command rather than about the
presence of a source anywhere in the prompt. Step 4 already named
`livespec.factoryRunId`, correctly, as its second source; that is exactly the
shape that failed, because a value resolved in one tool call is not a value the
next tool call holds.
"""

from __future__ import annotations

from itertools import groupby
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPT = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "prompts"
    / "proof-capture.md"
)

# The dispatch id the sandbox's own prepare step declares in the clone's local
# git config, which is the ONE source an agent shell can read. Spelled as the
# config key rather than as a command, so a reworded invocation still matches.
_GIT_CONFIG_SOURCE = "livespec.factoryRunId"
# The hook-only variable. Naming it in a PROHIBITION is wanted — an agent that
# reaches for it from memory needs to be told why not — so the cases below pin
# the ORDER rather than probing for its absence.
_HOOK_ONLY_SOURCE = "FABRO_RUN_ID"
# Any command that writes a record header. Both headers this prompt publishes —
# the `captured` record and the `not_captured` finding — are matched by it.
_HEADER_WRITE = "printf 'Proof of Done — "
_RECORD_HEADERS = 2


def _text() -> str:
    return _PROMPT.read_text(encoding="utf-8")


def _prose() -> str:
    """The prompt whitespace-COLLAPSED, so a needle cannot straddle a line break.

    The prose is hard-wrapped, so a probe against the raw bytes can only fail
    silently while the prompt says exactly the thing.
    """
    return " ".join(_text().split())


def _header_command_blocks() -> list[list[str]]:
    """Every indented command block whose `printf` writes a record header.

    BLOCKS rather than the whole prompt, because the claim is that the
    resolution and the write are ONE command: a `livespec.factoryRunId` named
    three paragraphs earlier is precisely the shape that lost run
    01M5E8H65Z04, and a whole-file probe would read it as satisfied.
    """
    runs = groupby(_text().splitlines(), key=lambda line: line.startswith("    "))
    blocks = [list(lines) for indented, lines in runs if indented]
    return [one for one in blocks if any(_HEADER_WRITE in line for line in one)]


def test_every_record_header_resolves_its_run_id_in_the_command_that_writes_it() -> None:
    """Both published headers carry their own resolution, inside one command.

    The count is asserted as well as the property: a splitter that matched
    nothing would report clean over a prompt that still writes the header from
    an inherited variable, and the `not_captured` finding is a record header too
    — it reaches the `fix` node as the only durable account of the defect, so a
    non-record there loses the finding exactly as a non-record capture loses the
    proof.
    """
    blocks = _header_command_blocks()

    assert len(blocks) == _RECORD_HEADERS, blocks
    for block in blocks:
        assert any(_GIT_CONFIG_SOURCE in line for line in block), block


def test_the_capture_stops_rather_than_posting_a_header_with_an_empty_run_id() -> None:
    """An unresolvable run id ends the turn; it never becomes an empty header.

    A record comment MUST NOT be edited after posting, so a header posted with
    an empty run id is unrecoverable within the run — and the needs-human
    protocol is the rest state this prompt already uses for every other
    condition it cannot resolve.
    """
    prose = _prose()

    assert "never post a header with an empty run id" in prose, prose
    assert "end with the needs-human protocol" in prose, prose


def test_the_hook_only_variable_is_not_the_first_run_id_source_the_prompt_names() -> None:
    """`livespec.factoryRunId` is named before `FABRO_RUN_ID` is mentioned at all.

    This is the item's own title — the prompt "names the hook-only FABRO_RUN_ID
    first" — and it is asserted as an ORDER rather than as an absence so it can
    fail today and so the prohibition that explains the hazard is still allowed
    to name the variable. An agent reading a resolution ladder top-down reaches
    for the first source it is offered.
    """
    text = _text()

    assert _GIT_CONFIG_SOURCE in text
    assert _HOOK_ONLY_SOURCE in text, "the prohibition must still name the variable"
    assert text.index(_GIT_CONFIG_SOURCE) < text.index(_HOOK_ONLY_SOURCE)
