"""The title and body the scripted `pr` stage applies, and how each is transported.

WHAT THE CLAUSE REQUIRES AND WHAT WAS MISSING. `SPECIFICATION/contracts.md`
section "Definition-of-Done and Proof-of-Done stages" -> "Scripted publication
and proof-head integrity" requires `pr` to "apply the Dispatcher-rendered title
and body", and the named-workflow-variants clause fixes the transport:
`LIVESPEC_PR_TITLE` plus a sandbox-readable `LIVESPEC_PR_BODY_FILE`, "not new
`inputs.*` tokens". Nothing produced either value, so every implementation pull
request kept the publish branch name as its title and `publish_draft`'s
placeholder body -- silently, at exit 0, with no sentinel on the run record.

THE RENDERED VALUE IS ASSERTED, NOT ITS SHAPE. Each case below reads the title
or body this module produces for a work-item and checks the part the clause
makes load-bearing: that the title carries the item's own words and its id, that
the body carries the acceptance criteria VERBATIM, and that both are bounded in
the direction that cannot destroy a run. A case asserting only "the string is
non-empty" would pass for a build that rendered the branch name again.

THE TRANSPORT IS ASSERTED THROUGH THE PARSER, because the projections land in a
TOML document the engine reads: `tomli.loads` is what shows a title carrying a
quote, a backslash or a newline reaches the sandbox as that title rather than
making the whole overlay unparseable. The body's prepare step is EXECUTED under
bash in a throwaway root, because the thing under test is whether a file with
the right bytes appears at the path the stage resolves -- and a substring check
on the script cannot tell a correct decode from one that writes the base64.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_metadata import (
    PR_BODY_FILE_ENV_VAR,
    PR_TITLE_ENV_VAR,
    PUBLICATION_BODY_FILENAME,
    PUBLICATION_BODY_MAX_BYTES,
    PUBLICATION_TITLE_MAX_CHARS,
    PublicationMetadata,
    publication_body_path_expansion,
    publication_metadata_env_lines,
    publication_metadata_for,
    publication_metadata_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "bd-ib-c3txja"
_CRITERIA = """- The implementation workflow renders pr_refresh and pr as command stages.
- An implementation dispatch requesting an ACP adapter for pr refuses before claim.
"""


def _item(
    *,
    title: str = "Replace the implementation PR agent turn with scripted publication",
    acceptance_criteria: str | None = _CRITERIA,
    item_id: str = _ITEM_ID,
) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="ready",
        title=title,
        description="The description is deliberately NOT part of the rendered body.",
        acceptance_criteria=acceptance_criteria,
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-12T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_the_rendered_title_carries_the_items_own_words_and_its_id() -> None:
    """Both halves, because each alone is satisfied by the regression.

    The branch-name fallback the stage used to take IS `feat/<id>`, so it
    contains the id -- a case asserting only "the id appears" would pass against
    exactly the regression this module repairs. The item's own title text is
    what discriminates.
    """
    item = _item()

    metadata = publication_metadata_for(item=item)

    assert item.title in metadata.title
    assert f"({_ITEM_ID})" in metadata.title
    assert not metadata.title.startswith("feat/"), "the branch-name fallback was rendered"


def test_the_rendered_body_carries_the_acceptance_criteria_verbatim() -> None:
    """The Definition of Done rides the body as the ledger wrote it.

    Asserted as a VERBATIM substring rather than line by line: the criteria are
    what a reviewer grades the pull request against, and a body that reformatted
    them would be presenting the Dispatcher's paraphrase as the item's own.
    """
    metadata = publication_metadata_for(item=_item())

    assert _CRITERIA.strip() in metadata.body
    assert f"`{_ITEM_ID}`" in metadata.body
    assert "## Definition of Done" in metadata.body
    assert metadata.body.rstrip().endswith(
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)"
    )
    # The description is NOT copied: a pull-request body is orientation, and the
    # work-item record is where the full brief lives.
    assert "deliberately NOT part" not in metadata.body


def test_an_item_with_no_acceptance_criteria_says_so_rather_than_rendering_a_gap() -> None:
    """An empty Definition of Done is STATED, not left as a blank section.

    Both the absent and the whitespace-only forms, because a store that reads a
    legacy record back as `None` and one that read an empty field are different
    inputs reaching the same place, and a build handling only `None` renders a
    section containing nothing at all.
    """
    for criteria in (None, "   \n\n"):
        metadata = publication_metadata_for(item=_item(acceptance_criteria=criteria))

        assert "## Definition of Done" in metadata.body
        assert "records no acceptance criteria" in metadata.body


def test_an_over_long_title_is_bounded_while_keeping_the_id() -> None:
    """The forge REJECTS an over-long title, so the bound is not cosmetic.

    The id is what survives truncation, because it is what makes the pull
    request findable from the ledger and the ledger findable from the pull
    request; the prose is what goes. A `gh pr edit` refused on a long title
    would fail the stage closed on a value that changes nothing about the work.
    """
    metadata = publication_metadata_for(item=_item(title="word " * 200))

    assert len(metadata.title) <= PUBLICATION_TITLE_MAX_CHARS
    assert metadata.title.endswith(f"({_ITEM_ID})")


def test_an_over_long_body_is_bounded_and_says_that_it_was_truncated() -> None:
    """A truncated body that did not SAY so reads as a truncated ledger record.

    The bound is in BYTES, which is the half most easily simplified into a
    character count: the payload rides a prepare step bounded by `execve`, and
    an oversized step kills the run in setup before any work. The fixture is
    therefore multi-byte, so a character-counting build overshoots.
    """
    metadata = publication_metadata_for(item=_item(acceptance_criteria="— a criterion\n" * 4000))

    assert len(metadata.body.encode()) <= PUBLICATION_BODY_MAX_BYTES
    assert "truncated this body" in metadata.body


def test_the_title_rides_the_environment_table_as_a_parseable_toml_value() -> None:
    """A hostile title reaches the sandbox as that title, not as a parse hazard.

    Every value in this table is a TOML basic string, so a title carrying a
    quote or a backslash written raw would terminate the string early and make
    the WHOLE overlay unparseable -- one item's prose turning into a
    dispatch-wide failure. Read back through `tomli` rather than compared as
    text, because that is the reader the engine uses.
    """
    hostile = 'a "quoted" title with a \\ backslash and {{ braces }}'
    lines = publication_metadata_env_lines(
        metadata=PublicationMetadata(title=hostile, body="unused")
    )

    parsed = tomli.loads(f"[env]\n{lines}")

    assert parsed["env"][PR_TITLE_ENV_VAR] == hostile
    # The BODY is deliberately absent from this table: its path is not known
    # host-side, so the stage resolves it by shell expansion instead.
    assert PR_BODY_FILE_ENV_VAR not in parsed["env"]


def test_a_caller_rendering_no_metadata_projects_nothing_at_all(tmp_path: Path) -> None:
    """The absent arm renders exactly the overlay it rendered before.

    A direct caller holding no work-item must not get a placeholder title: the
    stage's own absent-title sentinel is what reports the shortfall, and a
    projection inventing a value would make that sentinel unreachable.
    """
    assert publication_metadata_env_lines(metadata=None) == ""
    assert publication_metadata_prepare_steps_block(metadata=None) == ""
    assert not list(tmp_path.iterdir())


def test_the_body_prepare_step_writes_the_rendered_bytes_where_the_stage_reads(
    tmp_path: Path,
) -> None:
    """EXECUTED, because the claim is that a file with the right bytes appears.

    The body is arbitrary ledger prose, so the fixture carries the two things
    that break a naive transport: shell metacharacters, which a heredoc or an
    interpolated value would execute, and multi-byte text, which a latin-1 write
    would mangle. The step is read out of the rendered TOML and run under bash
    with the plugins root pointed at a throwaway directory, so the path it
    resolves is the same expansion the `pr` stage resolves.
    """
    body = "A body with $(touch /tmp/livespec-body-should-not-exist) `date` 'quotes' — and é.\n"
    block = publication_metadata_prepare_steps_block(
        metadata=PublicationMetadata(title="unused", body=body)
    )
    parsed = tomli.loads(block)
    [step] = parsed["run"]["prepare"]["steps"]

    completed = subprocess.run(
        ["bash", "-c", step["script"]],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(tmp_path / "home"),
            SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(tmp_path / "plugins"),
        },
    )

    assert completed.returncode == 0, completed.stderr
    landed = tmp_path / "plugins" / PUBLICATION_BODY_FILENAME
    assert landed.read_text(encoding="utf-8") == body
    assert not Path("/tmp/livespec-body-should-not-exist").exists()
    assert str(landed) in completed.stdout


def test_the_step_and_the_stage_resolve_one_path_by_shell_expansion() -> None:
    """A step writing where the stage does not read reports an absent body.

    That diagnosis would name the wrong half of the seam, so the agreement is
    asserted on both sides: the published expansion names the sandbox
    plugins-root variable, so an image override moves both together, and the
    step's own script resolves its root from that same expansion rather than
    from a second spelling.
    """
    expansion = publication_body_path_expansion()
    parsed = tomli.loads(
        publication_metadata_prepare_steps_block(metadata=PublicationMetadata(title="t", body="b"))
    )
    [step] = parsed["run"]["prepare"]["steps"]

    assert SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR in expansion
    assert expansion.endswith(f"/{PUBLICATION_BODY_FILENAME}")
    root, _, filename = expansion.rpartition("/")
    assert f'root="{root}"' in step["script"]
    assert f'"$root/{filename}"' in step["script"]


def test_a_title_longer_than_the_ceiling_even_without_prose_is_bounded_whole() -> None:
    """The degenerate arm: an id so long that no prose budget is left.

    No real record reaches it, and it exists so the bound holds for every input
    rather than for the ones a fixture happens to supply -- a ceiling that can be
    exceeded by a sufficiently odd id is not a ceiling.
    """
    metadata = publication_metadata_for(item=_item(item_id="z" * (PUBLICATION_TITLE_MAX_CHARS + 8)))

    assert len(metadata.title) <= PUBLICATION_TITLE_MAX_CHARS


def test_a_payload_outside_the_base64_alphabet_refuses_rather_than_rendering() -> None:
    """The invariant that makes the single-quoted payload safe is HELD, not trusted.

    The payload is single-quoted in shell with no escaping, which is sound only
    because base64 emits `A-Za-z0-9+/=` and nothing else. A build whose encoder
    changed would otherwise render a step that breaks out of its own quoting, so
    the guard is reached directly -- by monkeypatching the encoder, since no
    body can produce a bad payload through the real one.
    """
    from livespec_orchestrator_beads_fabro.commands import (
        _dispatcher_publication_metadata as module,
    )

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(module.base64, "b64encode", lambda _: b"not'base64")
        with pytest.raises(ValueError, match="base64 alphabet"):
            _ = publication_metadata_prepare_steps_block(
                metadata=PublicationMetadata(title="t", body="b")
            )
