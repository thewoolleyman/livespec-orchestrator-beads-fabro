"""An inherited payload is reused only when it came from the SAME source.

Work-item `bd-ib-mtuqxb`'s fourth assertion requires that a normal invocation
"releases its private payload only after its owned consumers finish while
leaving another active invocation and harness-managed plugin installation
usable", and its scope paragraph requires that "original CLAUDE_PLUGIN_ROOT or
later installed-root resolution must not pull assets from an evicted or newer
tree". Hand-down REUSE and source SELECTION are two different questions, and
`retain_payload` answered the second with the first.

`PAYLOAD_ROOT_ENV` exists so the several processes of one dispatch read one
tree: `drive`, the `dispatcher.py` it starts, and the helpers that starts in
turn. That is the case these tests must keep working, and the last two
preserve it.

But the variable is ordinary inherited environment, so it also reaches a
process that was pointed at a DIFFERENT installation on purpose — a second
dispatch launched from inside the first, a helper invoked from an explicitly
named newer install, a developer running their own source checkout from a shell
that still carries a parent's payload. Adoption was unconditional, so the
inherited tree won and the explicitly selected release was silently ignored.
Measured against the pre-fix launcher on 2026-10-06, with an isolated
`environ` per call:

- source A at release 7.1.0 provisioned and published its payload; a call
  explicitly naming install B at release 9.9.9 returned A's payload, so the
  release actually executed was 7.1.0;
- a call explicitly naming this project's own SOURCE CHECKOUT returned A's
  payload too, with `retained` True, where a checkout must be its own payload.

Both are the wrong direction for the same reason the module's own provisioning
comments give: running a release other than the one selected is the defect
retention exists to prevent, and nothing in either result reported the
substitution.

The remedy is a source RECORD written beside the payload at provisioning time
and compared before adoption. It lives in the HOLDER rather than inside
`payload/` so the payload stays a faithful copy of its source and
`payload_fidelity_gaps` keeps comparing like with like. A payload whose source
cannot be established is not adopted: that costs one copy, where adopting on
trust restores the defect.
"""

import importlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

_BIN_DIR = Path(__file__).resolve().parents[2] / ".claude-plugin" / "scripts" / "bin"
_RELEASE_A = "7.1.0"
_RELEASE_B = "9.9.9"
_CHECKOUT_PLUGIN_ROOT = ".claude-plugin"
_THIS_PROJECT = '[project]\nname = "livespec-orchestrator-beads-fabro"\n'


def _import_payload() -> Any:
    if str(_BIN_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_DIR))
    _ = sys.modules.pop("_payload", None)
    return importlib.import_module("_payload")


def _install(*, root: Path, release: str) -> Path:
    """A COMPLETE minimal installed plugin root carrying `release`."""
    for relative in (
        "scripts/bin",
        "scripts/livespec_orchestrator_beads_fabro/commands",
        "scripts/_vendor/livespec_runtime",
        ".fabro/workflows/implement-work-item",
    ):
        (root / relative).mkdir(parents=True)
    for relative in (
        "scripts/bin/_bootstrap.py",
        "scripts/bin/_payload.py",
        "scripts/livespec_orchestrator_beads_fabro/__init__.py",
        "scripts/livespec_orchestrator_beads_fabro/commands/__init__.py",
        "scripts/_vendor/livespec_runtime/__init__.py",
        ".fabro/workflows/implement-work-item/workflow.toml",
    ):
        _ = (root / relative).write_text("", encoding="utf-8")
    _ = (root / "plugin.json").write_text(
        json.dumps({"version": release}),
        encoding="utf-8",
    )
    return root


def _private_tempdir(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))
    return temp_root


def _release_of(*, payload: Any) -> str:
    """The release the payload actually carries, read from its own manifest."""
    manifest = json.loads((payload.root / "plugin.json").read_text(encoding="utf-8"))
    return str(manifest["version"])


def test_an_inherited_payload_never_overrides_an_explicitly_selected_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Install B was named, so B's release must execute — not the inherited A."""
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_a = _install(root=tmp_path / "cache" / "aaaaaaa1111", release=_RELEASE_A)
    source_b = _install(root=tmp_path / "cache" / "bbbbbbb2222", release=_RELEASE_B)

    environ: dict[str, str] = {}
    parent = payload.retain_payload(source_root=source_a, environ=environ)
    assert _release_of(payload=parent) == _RELEASE_A, "fixture: A did not provision as A"
    assert environ[payload.PAYLOAD_ROOT_ENV] == str(parent.root), "fixture: A published nothing"

    selected = payload.retain_payload(source_root=source_b, environ=dict(environ))

    assert _release_of(payload=selected) == _RELEASE_B, (
        "the inherited payload from install A overrode the explicitly selected "
        f"install B, so this invocation executes release {_release_of(payload=selected)} "
        f"where {_RELEASE_B} was named"
    )
    assert selected.root != parent.root, "B resolved to A's payload tree"


def test_an_inherited_payload_never_overrides_an_explicitly_selected_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A developer's own checkout is its own payload, inherited variable or not."""
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_a = _install(root=tmp_path / "cache" / "aaaaaaa1111", release=_RELEASE_A)
    checkout_parent = tmp_path / "checkout"
    checkout_parent.mkdir()
    _ = (checkout_parent / "pyproject.toml").write_text(_THIS_PROJECT, encoding="utf-8")
    checkout = _install(
        root=checkout_parent / _CHECKOUT_PLUGIN_ROOT,
        release=_RELEASE_B,
    )

    environ: dict[str, str] = {}
    _ = payload.retain_payload(source_root=source_a, environ=environ)
    selected = payload.retain_payload(source_root=checkout, environ=dict(environ))

    assert selected.root == checkout, (
        "an inherited payload displaced the explicitly selected source checkout, "
        f"so the checkout's own code is not what runs: {selected.root}"
    )
    assert selected.retained is False, "a checkout is its own payload; nothing is retained"
    assert selected.holder is None, "a checkout payload owns no holder to remove"


def test_a_same_source_helper_still_reuses_the_payload_it_inherited(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The case the hand-down exists for, which the source check must not break."""
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "aaaaaaa1111", release=_RELEASE_A)

    environ: dict[str, str] = {}
    parent = payload.retain_payload(source_root=source_root, environ=environ)
    helper = payload.retain_payload(source_root=source_root, environ=dict(environ))

    assert helper.root == parent.root, "a same-source helper must read the parent's tree"
    assert helper.retained is True
    assert helper.holder is None, "a helper must not own the payload its parent created"
    assert len(list(temp_root.iterdir())) == 1, "the helper provisioned a copy of the copy"


def test_a_helper_that_finishes_leaves_the_payload_readable_by_its_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Release is the CREATOR's to perform, so a finished helper removes nothing.

    The parent reads its packaged assets after the helper it waited on has
    exited and before its own exit, which is the ordering `release_payload`
    documents. A helper that released what it inherited would pull the tree out
    from under the process that owns it.
    """
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "aaaaaaa1111", release=_RELEASE_A)

    environ: dict[str, str] = {}
    parent = payload.retain_payload(source_root=source_root, environ=environ)
    helper = payload.retain_payload(source_root=source_root, environ=dict(environ))

    payload.release_payload(payload=helper)

    assert _release_of(payload=parent) == _RELEASE_A, (
        "the helper's release removed the payload its parent still owns, so the "
        "parent can no longer read its own packaged assets"
    )
    assert parent.vendor_root.is_dir(), "the parent's vendored modules are gone"

    payload.release_payload(payload=parent)
    assert (
        parent.holder is not None and not parent.holder.exists()
    ), "the creator's own release did not remove the holder it owns"
