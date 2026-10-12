"""The sandbox image source decision, and how the overlay renders each of its arms.

The end-to-end acceptance for Scenario 169 lives in
`tests/integration/test_sandbox_image_source_scenario169.py`, which drives a real
dispatch. These cases cover the decision's own arms and the two run-config shapes
the withholding has to survive, neither of which a dispatch through this
repository's committed run config can produce.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source import (
    CATALOG_ENVIRONMENT_SOURCE,
    COMMITTED_RUN_CONFIG_IMAGE,
    COMMITTED_RUN_CONFIG_SOURCE,
    CONFIGURED_IMAGE_SOURCE,
    sandbox_image_source,
)

_ENV_ID = "livespec-ci"
_COMMITTED_IMAGE = "ghcr.io/example/sandbox:committed"
_CONFIGURED_IMAGE = "ghcr.io/example/sandbox:configured"
_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"

_HEAD = f'[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "{_ENV_ID}"\n'
# A run config whose image table is the LAST table in the file, so withholding it
# runs off the end rather than stopping at a following header.
_IMAGE_TABLE_LAST = (
    f'{_HEAD}\n[environments.{_ENV_ID}]\nprovider = "docker"\n'
    f'\n[environments.{_ENV_ID}.image]\ndocker = "{_COMMITTED_IMAGE}"\n'
)
# A run config declaring NO image table at all: the catalog is already the only
# source, so there is nothing to withhold.
_NO_IMAGE_TABLE = f'{_HEAD}\n[environments.{_ENV_ID}]\nprovider = "docker"\n'


def _rendered(*, committed_text: str, environment: str | None, configured: str | None) -> str:
    rendered = render_run_config_overlay(
        committed_text=committed_text,
        workflow_dir=Path("/workflow"),
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        sandbox_image=sandbox_image_source(
            factory_environment=environment, configured_image=configured
        ),
    )
    assert rendered is not None
    return rendered


def test_a_declared_catalog_environment_wins_over_the_configured_override() -> None:
    """The catalog arm is reached even with `dispatcher.fabro_sandbox_image` set.

    The configured key is a repository-wide pin and the catalog environment is
    the placement this dispatch was routed to, so the routing decides. A
    resolution that let the pin win would be the measured defect.
    """
    resolved = sandbox_image_source(factory_environment=_ENV_ID, configured_image=_CONFIGURED_IMAGE)

    assert (resolved.source, resolved.environment_id, resolved.overlay_image) == (
        CATALOG_ENVIRONMENT_SOURCE,
        _ENV_ID,
        None,
    )
    assert resolved.catalog_governs is True


def test_no_catalog_environment_resolves_the_configured_override() -> None:
    """The configured arm carries the image and names no environment."""
    resolved = sandbox_image_source(factory_environment=None, configured_image=_CONFIGURED_IMAGE)

    assert (resolved.source, resolved.environment_id, resolved.overlay_image) == (
        CONFIGURED_IMAGE_SOURCE,
        None,
        _CONFIGURED_IMAGE,
    )
    assert resolved.catalog_governs is False


def test_neither_declaration_resolves_the_committed_run_config() -> None:
    """A target declaring neither leaves its committed run config's image standing.

    `catalog_governs` is asserted False even though `overlay_image` is None, the
    same pair the catalog arm carries inverted: the two arms are distinguished by
    the SOURCE and not by the absent image, and collapsing them would make this
    one withhold a declaration nothing is competing with.
    """
    resolved = sandbox_image_source(factory_environment=None, configured_image=None)

    assert resolved == COMMITTED_RUN_CONFIG_IMAGE
    assert (resolved.source, resolved.overlay_image) == (COMMITTED_RUN_CONFIG_SOURCE, None)
    assert resolved.catalog_governs is False


def test_the_catalog_arm_withholds_an_image_table_that_ends_the_run_config() -> None:
    """Withholding the last table in the file takes it to the end of the file."""
    rendered = _rendered(
        committed_text=_IMAGE_TABLE_LAST, environment=_ENV_ID, configured=_CONFIGURED_IMAGE
    )

    assert f"[environments.{_ENV_ID}.image]" not in rendered
    assert _COMMITTED_IMAGE not in rendered
    assert _CONFIGURED_IMAGE not in rendered
    assert f'[environments.{_ENV_ID}]\nprovider = "docker"\n' in rendered


def test_the_catalog_arm_leaves_a_run_config_declaring_no_image_alone() -> None:
    """No image table is not a refusal: the catalog is already the only source.

    A refusal here would reject exactly the configuration the clause asks for,
    and it is the natural coding of "the table I was told to remove is not
    there" — which is why the case is asserted rather than left to inference.
    """
    rendered = _rendered(
        committed_text=_NO_IMAGE_TABLE, environment=_ENV_ID, configured=_CONFIGURED_IMAGE
    )

    assert f"[environments.{_ENV_ID}.image]" not in rendered
    assert _CONFIGURED_IMAGE not in rendered
    assert f'[environments.{_ENV_ID}]\nprovider = "docker"\n' in rendered
