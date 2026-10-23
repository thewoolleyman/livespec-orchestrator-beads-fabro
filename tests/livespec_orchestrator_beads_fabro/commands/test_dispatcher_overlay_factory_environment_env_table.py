"""The env table is keyed on the FACTORY's catalog environment, the image on the committed one.

`bd-ib-kyeor4`. The overlay used to key BOTH of its `[environments.<id>.*]`
tables on the committed workflow's `[run.environment] id`, which was right while
that id was also the environment the run intent selected. `bd-ib-fgre25` made the
dispatch pass `--environment <the factory's declared catalog environment>`, and
the engine reads an overlay only from `[environments.<selected id>]` plus the
id-less `[run.environment]` — so on any factory whose catalog environment is not
spelled exactly like the committed id, every projected variable and every
credential was SILENTLY DROPPED.

Measured 2026-10-23 on gmktec: run 01M5MH0JBKGJ2HRW7VCBP3PGK4, dispatched with
`--environment livespec-ci-k8s` against a committed id of `livespec-ci`,
resolved an environment whose `env` was empty and died in `run_prepare_35` with
an empty `CODEX_HOME`. A Docker run on the same server minutes earlier, with
environment `livespec-ci`, resolved 37 keys including `CODEX_HOME`,
`CODEX_AUTH_JSON`, `GITHUB_TOKEN` and `CLAUDE_CODE_OAUTH_TOKEN`.

THE TWO TABLES MOVE SEPARATELY, AND THAT IS THE WHOLE OF THE FIX. The ENV table
follows the selected environment, because that is the only table the engine
reads. The IMAGE table must NOT: on a registered-provider environment Petri
REFUSES an image found under the selected id, and the image is the catalog's to
supply — so the committed declaration stays keyed on the committed id, where
`resolve_sandbox_image` can find it and WITHHOLD it. A fix that moved both
tables together would look correct at the env table and leave the committed pin
standing under a key nothing reads, which overrides the catalog.

WHY THE FIRST ASSERTION IS A SIGNATURE READING. The parameter does not exist
when this module's Red is authored, so a call carrying it raises `TypeError` —
an error, not a failing assertion, which proves only that the keyword is
unknown. Asserting the SIGNATURE fails as an ordinary assertion before any call
is attempted, which is the pattern the sibling overlay modules use.

WHY THE CONTROL IS NOT OPTIONAL. Every case here that names a factory
environment is satisfied by a build that keys the env table on the FACTORY id
unconditionally — including one that keys it there when no factory environment
was declared at all, which would move the table out from under every dispatch on
the pinned engine, where no factory declares one. So the no-factory-environment
case asserts the committed id is still what the table is keyed on.
"""

from __future__ import annotations

from inspect import signature
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_sibling_clones
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source import (
    CATALOG_ENVIRONMENT_SOURCE,
    CONFIGURED_IMAGE_SOURCE,
    SandboxImageSource,
)

# The two ids the measured incident actually carried: the factory's declared
# catalog environment, and the id this repository's committed run config
# declares. They differ, which is the entire precondition for the defect.
_FACTORY_ENVIRONMENT = "livespec-ci-k8s"
_COMMITTED_ENVIRONMENT = "livespec-ci"

_REVIEW_FIX_VISIT_CAP = 4
_GIT_AUTHOR = GitAuthor(name="Operator", email="operator@example.com")

# Bound to locals before use so ruff's S106 does not flag the literals.
_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"

# A committed config of the shape every dispatch target in this fleet carries:
# the graph, the `[run.environment]` id, and an image pin under THAT id.
_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    f'id = "{_COMMITTED_ENVIRONMENT}"\n'
    "\n"
    f"[environments.{_COMMITTED_ENVIRONMENT}.image]\n"
    'docker = "ghcr.io/example/committed:1"\n'
)

_MINIMAL_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)

# A canned fleet manifest so `resolve_sibling_clones` never shells out.
_FLEET_MANIFEST_TEXT = (
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [{ "repo": "livespec", "class": "core" }]\n'
    "}\n"
)

_CATALOG_IMAGE = SandboxImageSource(
    source=CATALOG_ENVIRONMENT_SOURCE,
    environment_id=_FACTORY_ENVIRONMENT,
    overlay_image=None,
)


def _credential_block(*, environment_id: str) -> str:
    """The two credential lines as the overlay renders them under one id.

    The whole BLOCK rather than the header alone: a table header rendered under
    the right id while the credentials landed under another would satisfy a
    header-only assertion and project nothing.
    """
    return (
        f"[environments.{environment_id}.env]\n"
        f'CLAUDE_CODE_OAUTH_TOKEN = "{_FAKE_TOKEN}"\n'
        f'GITHUB_TOKEN = "{_FAKE_GITHUB_TOKEN}"\n'
    )


def test_a_declared_factory_environment_keys_the_env_table_on_that_environment(
    tmp_path: Path,
) -> None:
    """The credentials land under the environment the run intent selects."""
    assert "factory_environment" in signature(render_run_config_overlay).parameters

    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        factory_environment=_FACTORY_ENVIRONMENT,
        sandbox_image=_CATALOG_IMAGE,
    )

    assert rendered is not None
    assert _credential_block(environment_id=_FACTORY_ENVIRONMENT) in rendered
    # And NOT under the committed id, which the engine would never read.
    assert f"[environments.{_COMMITTED_ENVIRONMENT}.env]" not in rendered


def test_a_declared_factory_environment_renders_no_image_table_of_its_own(
    tmp_path: Path,
) -> None:
    """The image stays the catalog's: no factory-keyed table, committed pin withheld.

    Both halves are the same claim read from the two directions a wrong keying
    fails in. A build that moved the image table onto the factory id would
    render `[environments.livespec-ci-k8s.image]` — which Petri refuses on a
    registered-provider environment — and a build that moved only the LOOKUP
    would leave the committed pin standing, overriding the catalog's image under
    a key the engine does read.
    """
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        factory_environment=_FACTORY_ENVIRONMENT,
        sandbox_image=_CATALOG_IMAGE,
    )

    assert rendered is not None
    assert f"[environments.{_FACTORY_ENVIRONMENT}.image]" not in rendered
    assert f"[environments.{_COMMITTED_ENVIRONMENT}.image]" not in rendered
    assert "ghcr.io/example/committed:1" not in rendered


def test_no_declared_factory_environment_keys_the_env_table_on_the_committed_id(
    tmp_path: Path,
) -> None:
    """The control: a factory naming no catalog environment renders as before.

    No factory in this fleet's pinned-engine posture declares one, so a build
    that keyed the env table on the factory id unconditionally would render the
    credentials under `None` for every such dispatch.
    """
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )

    assert rendered is not None
    assert _credential_block(environment_id=_COMMITTED_ENVIRONMENT) in rendered
    # The committed image pin stands untouched, which is this arm's own
    # behaviour and not a consequence of the keying.
    assert f"[environments.{_COMMITTED_ENVIRONMENT}.image]" in rendered
    assert "ghcr.io/example/committed:1" in rendered


def test_the_rendered_image_table_is_keyed_on_the_committed_environment_id(
    tmp_path: Path,
) -> None:
    """The image substitution is addressed by the committed id, never the factory's.

    A DIRECT-CALLER combination: `sandbox_image_source` lets the catalog win
    over a configured pin, so no dispatch resolves a configured image beside a
    declared factory environment. It is the sharpest available reading of
    "the image table stays keyed on the committed id" — it isolates the keying
    from the source decision, where the catalog arm can only ever show a
    withholding.
    """
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        factory_environment=_FACTORY_ENVIRONMENT,
        sandbox_image=SandboxImageSource(
            source=CONFIGURED_IMAGE_SOURCE,
            environment_id=None,
            overlay_image="ghcr.io/example/configured:2",
        ),
    )

    assert rendered is not None
    assert f"[environments.{_COMMITTED_ENVIRONMENT}.image]" in rendered
    assert 'docker = "ghcr.io/example/configured:2"' in rendered
    assert _credential_block(environment_id=_FACTORY_ENVIRONMENT) in rendered


def test_materialize_overlay_passes_the_resolved_factory_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The written overlay keys its env table on the factory environment.

    Driven through `materialize_overlay` rather than asserted off the call,
    because the forwarding is only worth anything if it reaches the BYTES the
    launch submits — a renderer that accepted the keyword while the materializer
    withheld it is exactly the state this repository shipped.
    """
    assert "factory_environment" in signature(materialize_overlay).parameters

    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (committed.parent / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    overlay = tmp_path / "overlay.toml"
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _FAKE_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )

    error = materialize_overlay(
        committed=committed,
        overlay=overlay,
        repo=tmp_path / "repo",
        work_item_id="wi-1",
        dispatch_id="01M23CD51JNGY3R1AKN2WNP4WB",
        token=lambda: _FAKE_GITHUB_TOKEN,
        git_author=_GIT_AUTHOR,
        review_fix_visit_cap=_REVIEW_FIX_VISIT_CAP,
        factory_environment=_FACTORY_ENVIRONMENT,
        sandbox_image=_CATALOG_IMAGE,
    )

    assert error is None
    written = overlay.read_text(encoding="utf-8")
    assert _credential_block(environment_id=_FACTORY_ENVIRONMENT) in written
    assert f"[environments.{_COMMITTED_ENVIRONMENT}.env]" not in written
