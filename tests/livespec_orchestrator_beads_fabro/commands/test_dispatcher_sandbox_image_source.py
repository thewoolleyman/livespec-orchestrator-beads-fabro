"""Which source supplies a dispatch's sandbox image, and what the journal says.

`SPECIFICATION/contracts.md` section "Sandbox image source" and Scenario 169:
a dispatch whose resolved factory declares a catalog environment MUST launch
from the image that environment declares on the factory server, the launch
overlay MUST NOT substitute `dispatcher.fabro_sandbox_image` for it, a dispatch
whose factory declares no catalog environment MUST still launch from that key,
and the dispatch journal MUST name which source supplied the image for each
launch.

Measured 2026-10-11 on hp-candidate run 01M4PBFW4MP8: the run declared catalog
environment `livespec-ci`, whose image is `python-agent-v1.93.5`, and `inspect`
reported `sandbox.plan.image` at that tag while the container Petri actually
started (`sandbox.instance.image`) ran `python-agent-v1.92.0` — the value of
this repository's `dispatcher.fabro_sandbox_image`, which the launch overlay
rewrote into the launch. Two sources of truth, so a proof reading the plan
reports an image that did not run.
"""

from __future__ import annotations

import importlib
from inspect import signature
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source"
_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    / "_dispatcher_sandbox_image_source.py"
)

_CONFIGURED_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.92.0"
_CATALOG_ENVIRONMENT = "livespec-ci"
# The image the catalog environment of the same name declares on the factory
# server. The host never reads it; it is the committed workflow's own value
# here, which is exactly what the overlay must leave standing.
_COMMITTED_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.93.5"
_WORKFLOW_WITH_IMAGE = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    f"[run.environment]\n"
    f'id = "{_CATALOG_ENVIRONMENT}"\n'
    "\n"
    f"[environments.{_CATALOG_ENVIRONMENT}]\n"
    'provider = "docker"\n'
    "\n"
    f"[environments.{_CATALOG_ENVIRONMENT}.image]\n"
    f'docker = "{_COMMITTED_IMAGE}"\n'
)
_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"


def test_a_dispatch_naming_no_catalog_environment_still_takes_the_committed_key() -> None:
    """`dispatcher.fabro_sandbox_image` supplies the image, and only then.

    The module import rides `importlib` INSIDE the test body, with the file
    existence as the first assertion, so the Red that precedes this module
    fails on a genuine assertion rather than at collection.

    Both branches are asserted in one case because they are one decision: the
    committed key reaches the launch exactly when no catalog environment is
    named, and `None` — the overlay's documented no-op, which leaves the
    committed image table byte-for-byte as shipped — is what the catalog case
    resolves to instead.
    """
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    assert (
        module.overlay_sandbox_image(factory_environment=None, configured_image=_CONFIGURED_IMAGE)
        == _CONFIGURED_IMAGE
    )
    assert (
        module.overlay_sandbox_image(
            factory_environment=_CATALOG_ENVIRONMENT, configured_image=_CONFIGURED_IMAGE
        )
        is None
    )
    # An unset key is still unset: a factory declaring no catalog environment
    # has nothing to substitute either, which is the pre-key no-op.
    assert module.overlay_sandbox_image(factory_environment=None, configured_image=None) is None


def test_the_launch_overlay_leaves_a_catalog_dispatch_image_unchanged(tmp_path: Path) -> None:
    """A named catalog environment makes the image rewrite a no-op, byte for byte.

    The measurement is WHOLE-TEXT EQUALITY against the render that passes no
    image at all, not a `docker = ` substring check. A substring check passes
    for any build that happens to write the committed tag somewhere while
    rewriting it elsewhere, and "unchanged" is a claim about the bytes — the
    overlay's own byte-identity case in `test_config.py` is the control this
    mirrors.

    The pin is asserted ABSENT from the whole rendered text rather than only
    from the image table, because the failure this closes was an image reaching
    the launch from the wrong source; a pin that survived anywhere in the
    overlay could still reach it.
    """
    assert "factory_environment" in signature(render_run_config_overlay).parameters

    unchanged = render_run_config_overlay(
        committed_text=_WORKFLOW_WITH_IMAGE,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )
    catalog = render_run_config_overlay(
        committed_text=_WORKFLOW_WITH_IMAGE,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        fabro_sandbox_image=_CONFIGURED_IMAGE,
        factory_environment=_CATALOG_ENVIRONMENT,
    )
    assert unchanged is not None
    assert catalog == unchanged
    assert f'docker = "{_COMMITTED_IMAGE}"' in catalog
    assert _CONFIGURED_IMAGE not in catalog

    # The control, in the same case so neither reading can stand alone: with NO
    # catalog environment the same pin DOES reach the image table. Without it a
    # renderer that had stopped substituting entirely would pass above.
    substituted = render_run_config_overlay(
        committed_text=_WORKFLOW_WITH_IMAGE,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        fabro_sandbox_image=_CONFIGURED_IMAGE,
        factory_environment=None,
    )
    assert substituted is not None
    assert f'docker = "{_CONFIGURED_IMAGE}"' in substituted
    assert _COMMITTED_IMAGE not in substituted
