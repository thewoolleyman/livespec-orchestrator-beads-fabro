"""The vendored livespec-runtime boundary: the shared judgement, and the pin.

Two assertions of work-item `bd-ib-ouk27x`, and they are the two that CAN be
proved hermetically. The item's remaining assertions compare the vendored tree
against the release itself, which needs the release's bytes and therefore a
network fetch; `dev-tooling/check-vendored-livespec-runtime-release.sh` is their
instrument and reads the pin this module asserts.

WHY THE IMPORT TEST ASSERTS WHERE THE MODULE CAME FROM, and not merely that it
imported. Two copies of `livespec_runtime` exist in this repository — the
vendored tree under `.claude-plugin/scripts/_vendor/`, and the `livespec-runtime`
distribution installed into `.venv` from the pin in `pyproject.toml` — and a bare
`import livespec_runtime.spec_stated` resolves to whichever one `sys.path`
happens to reach first. The published plugin bundle carries ONLY the vendored
tree and no virtualenv at all, so an import satisfied by site-packages proves
nothing about the artifact the consumers actually run. Asserting the resolved
`__file__` is under the vendored root is what makes the test about the bundle.
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

_VENDOR_ROOT = Path(".claude-plugin/scripts/_vendor/livespec_runtime")
_MANIFEST = Path(".vendor.jsonc")
_EXPECTED_PIN = "v0.28.0"
_LINE_COMMENT = re.compile(r'("(?:\\.|[^"\\])*")|(//[^\n]*)')


def _manifest_entry(*, name: str) -> dict[str, object]:
    """One `.vendor.jsonc` library entry, read through the manifest's own syntax.

    `.vendor.jsonc` is JSON with `//` line comments, and its comment block is the
    bulk of the file, so the comments are stripped before the parse rather than
    the file being read by pattern. Reading the entry — instead of grepping the
    pin out of the prose — is what keeps this test measuring the value
    `vendor-update` and every consumer resolve, which is the same discipline the
    release-check script follows for the same reason.
    """
    stripped = _LINE_COMMENT.sub(lambda m: m.group(1) or "", _MANIFEST.read_text(encoding="utf-8"))
    libraries = json.loads(stripped)["libraries"]
    [entry] = [one for one in libraries if one["name"] == name]
    return entry


def test_spec_stated_judgement_surface_imports_from_the_vendored_runtime() -> None:
    """The plugin bundle's own tree supplies the whole shared judgement surface."""
    module = importlib.import_module("livespec_runtime.spec_stated")

    assert module.__file__ is not None
    assert Path(module.__file__).resolve().is_relative_to(_VENDOR_ROOT.resolve())
    assert callable(module.judge)
    assert callable(module.classify)
    assert callable(module.parse_verdict)


def test_vendored_livespec_runtime_is_pinned_to_the_spec_stated_release() -> None:
    """The manifest pins v0.28.0, the first release carrying `spec_stated`."""
    assert _manifest_entry(name="livespec_runtime")["upstream_ref"] == _EXPECTED_PIN
