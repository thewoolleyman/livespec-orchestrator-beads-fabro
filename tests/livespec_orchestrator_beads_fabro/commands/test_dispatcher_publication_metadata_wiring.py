"""How the rendered publication title and body REACH the run.

The rendering itself is asserted beside this file, in
`test_dispatcher_publication_metadata.py`. This file asserts the WIRING, which
is where the clause failed before: the renderer can be perfect and the pull
request still take the publish branch name as its title, because nothing
threaded the values into the overlay. That is exactly what happened when
publication became a command stage -- the shaping was dropped, not re-homed --
and the resulting fallback was silent at every surface.

SO THE POSITIVE CASE IS THE LOAD-BEARING ONE. An overlay rendered WITH metadata
must carry the title in its environment table and a prepare step that
materializes the body, and the step must be real enough to execute. An
assertion on the renderer alone cannot see a dispatch that never calls it.

THE NEGATIVE CASE COVERS THE OTHER DIRECTION, and it is what keeps this
projection from changing anything for a caller that holds no work-item: the
overlay such a caller renders must be BYTE-IDENTICAL to the one it rendered
before, which is stronger than "the title is absent" -- a build that appended an
empty table, a bare comment or a trailing newline would satisfy the weaker form
while changing the document every direct caller writes.

THE OVERLAY IS READ BACK THROUGH `tomli`, because it is a TOML document the
engine parses: a title carrying a quote written raw would make the whole overlay
unparseable, and a `in` check over the rendered text would not notice.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_metadata import (
    PR_TITLE_ENV_VAR,
    PUBLICATION_BODY_FILENAME,
    PublicationMetadata,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)

_ENVIRONMENT_ID = "sandbox"
_WORKFLOW_TOML = (
    f'[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "{_ENVIRONMENT_ID}"\n'
)

# Opaque non-secret placeholders: the overlay renders whatever it is handed, and
# a literal spelled like a credential at the call site reads to the lint rule as
# a hardcoded one.
_FAKE_TOKEN = "overlay-token-placeholder"
_FAKE_GITHUB_TOKEN = "overlay-github-placeholder"

_TITLE = 'Replace the "pr" agent turn with scripted publication (bd-ib-c3txja)'
_BODY = "Work-item `bd-ib-c3txja`\n\n## Definition of Done\n\n- A criterion.\n"


def _overlay(*, tmp_path: Path, metadata: PublicationMetadata | None) -> str:
    rendered = render_run_config_overlay(
        committed_text=_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        publication_metadata=metadata,
    )
    assert rendered is not None
    return rendered


def test_the_rendered_title_reaches_the_runs_environment_table(tmp_path: Path) -> None:
    """The title lands where the command stage reads it, as a parseable value.

    Read back through the engine's own parser rather than matched as text: this
    title carries double quotes, which written raw would terminate the TOML
    string early and make the WHOLE overlay unparseable -- one item's prose
    turning into a dispatch-wide failure rather than a cosmetic one.
    """
    parsed = tomli.loads(_overlay(tmp_path=tmp_path, metadata=_metadata()))

    assert parsed["environments"][_ENVIRONMENT_ID]["env"][PR_TITLE_ENV_VAR] == _TITLE


def test_the_rendered_body_rides_a_prepare_step_that_actually_writes_it(
    tmp_path: Path,
) -> None:
    """The body's step is EXECUTED, because its only job is to leave a file.

    A substring assertion on the script cannot tell a correct decode from one
    that writes the base64 payload, and the stage reads the file rather than the
    script. The step is run with the plugins root pointed at a throwaway
    directory, which is the same expansion the `pr` stage resolves, so the path
    agreement is covered by the same execution.
    """
    parsed = tomli.loads(_overlay(tmp_path=tmp_path, metadata=_metadata()))
    scripts = [step["script"] for step in parsed["run"]["prepare"]["steps"]]
    [body_step] = [script for script in scripts if PUBLICATION_BODY_FILENAME in script]

    completed = subprocess.run(
        ["bash", "-c", body_step],
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
    assert landed.read_text(encoding="utf-8") == _BODY


def test_a_caller_holding_no_work_item_renders_a_byte_identical_overlay(
    tmp_path: Path,
) -> None:
    """Every direct caller's overlay is unchanged, to the byte.

    Byte equality rather than "the title is absent": a build that appended an
    empty env line, a lone comment or a trailing newline would satisfy the
    weaker check while changing the document every other caller writes, and a
    run config the engine parses differently is a dispatch-wide fault rather
    than a cosmetic one.
    """
    without = _overlay(tmp_path=tmp_path, metadata=None)

    assert PR_TITLE_ENV_VAR not in without
    assert PUBLICATION_BODY_FILENAME not in without
    assert without == render_run_config_overlay(
        committed_text=_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )


def _metadata() -> PublicationMetadata:
    return PublicationMetadata(title=_TITLE, body=_BODY)
