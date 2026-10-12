"""The overlay's sandbox-image rendering, as its own cohesive module.

`_dispatcher_overlay` had accreted two concerns: assembling the whole run-config
overlay, and rendering ONE resolved decision -- which of three sources supplies
this dispatch's sandbox image -- into an `[environments.<id>.image]` table. The
second is a self-contained chain (`resolve_sandbox_image` ->
`_withhold_image_table` -> `_opens_toml_table`) reached from exactly one call
site, so it is the seam the file decomposes along.

ONLY THE ENTRY POINT CROSSES THE BOUNDARY. The two helpers below it stay private
INSIDE the new module: pyright strict's `reportPrivateUsage` and this repo's
`private_calls` check both reject importing a `_`-prefixed name across modules,
and that is the usual way a size-split fails. So the move promotes
`_resolve_sandbox_image` to a public `resolve_sandbox_image` and leaves the rest
alone.

THE FIRST ASSERTION IS WHAT MAKES THE RED GENUINE. A top-level import of a
module that does not exist yet dies at COLLECTION, which proves only
unimportability -- never that the behaviour is unimplemented. Asserting the
module PATH is a file fails as an ordinary assertion before any import is
attempted, so the import stays inside the test body.

THE LAST TWO ASSERTIONS ARE THE HALF THAT CANNOT BE FAKED BY ADDING A FILE. A
new module re-exporting from the old one, or an old module that kept its copy,
would satisfy every existence check above while leaving the file exactly as
large as it was -- which is the whole reason for the move. So the source module
must no longer define the moved names, and the rendering must still be reached
through it.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source import (
    CATALOG_ENVIRONMENT_SOURCE,
    CONFIGURED_IMAGE_SOURCE,
    SandboxImageSource,
)

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = f"{_PACKAGE}._dispatcher_overlay_sandbox_image"
_SOURCE = f"{_PACKAGE}._dispatcher_overlay"

_MOVED = ("_resolve_sandbox_image", "_withhold_image_table", "_opens_toml_table")

_COMMITTED = (
    "[environments.fabro-sandbox]\n"
    "\n"
    "[environments.fabro-sandbox.image]\n"
    "# the pin this dispatch may or may not assert\n"
    'docker = "ghcr.io/example/committed:1"\n'
    "\n"
    "[run]\n"
)


def _module_path() -> Path:
    package = Path(__file__).resolve().parents[3] / ".claude-plugin" / "scripts"
    return package.joinpath(*_MODULE.split(".")).with_suffix(".py")


def test_the_sandbox_image_rendering_is_its_own_module() -> None:
    """The moved chain lives in a module of its own, entry point only."""
    assert _module_path().is_file()

    moved = import_module(_MODULE)

    assert callable(moved.resolve_sandbox_image)
    assert moved.__all__ == ["resolve_sandbox_image"]
    # The two helpers below the entry point stayed private INSIDE the new
    # module rather than becoming part of its surface.
    assert "_withhold_image_table" not in moved.__all__
    assert "_opens_toml_table" not in moved.__all__


def test_the_moved_names_are_gone_from_the_source_module() -> None:
    """A re-export shim would pass every existence check and shrink nothing."""
    source = import_module(_SOURCE)

    for name in _MOVED:
        assert not hasattr(source, name), f"{name} is still defined on {_SOURCE}"


def test_the_catalog_arm_still_withholds_the_whole_image_table() -> None:
    """The behaviour the move must preserve, reached through the new module."""
    moved = import_module(_MODULE)

    rendered = moved.resolve_sandbox_image(
        text=_COMMITTED,
        environment_id="fabro-sandbox",
        sandbox_image=SandboxImageSource(
            source=CATALOG_ENVIRONMENT_SOURCE,
            environment_id="fabro-sandbox",
            overlay_image=None,
        ),
    )

    assert rendered is not None
    # The TABLE goes, not just its `docker` key, and its comment block with it.
    assert "[environments.fabro-sandbox.image]" not in rendered
    assert "committed:1" not in rendered
    assert "may or may not assert" not in rendered
    # Its neighbours survive, so the withholding did not run past the table.
    assert "[environments.fabro-sandbox]" in rendered
    assert "[run]" in rendered


def test_a_configured_pin_is_substituted_rather_than_withheld() -> None:
    """The control: withholding is the CATALOG arm, not what every arm does."""
    moved = import_module(_MODULE)

    rendered = moved.resolve_sandbox_image(
        text=_COMMITTED,
        environment_id="fabro-sandbox",
        sandbox_image=SandboxImageSource(
            source=CONFIGURED_IMAGE_SOURCE,
            environment_id=None,
            overlay_image="ghcr.io/example/configured:2",
        ),
    )

    assert rendered is not None
    assert 'docker = "ghcr.io/example/configured:2"' in rendered
    assert "[environments.fabro-sandbox.image]" in rendered
