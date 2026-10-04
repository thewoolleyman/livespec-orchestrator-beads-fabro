"""The committed sandbox-capability mirror: `dispatcher.sandbox_capabilities`.

Binds the `SPECIFICATION/contracts.md` clause (ratified v115, section
"Definition-of-Done and Proof-of-Done stages", sub-clause "Sandbox
capabilities") that a governed repository MAY mirror the sandbox image's
published capability list as the committed `dispatcher.sandbox_capabilities`
array, one lowercase snake_case name per entry, so the gate has a fallback
and the filing displays can show the set without a sandbox.

WHY THE MIRROR IS VALIDATED AT DISPATCH rather than left to whoever reads it.
The mirror is consulted by the `dod_gate` node when the image publishes no
capability file, and the gate's missing-capability finding is computed FROM
it. A mis-cased or hyphenated name therefore does not fail loudly — it
silently fails to match the capability an assertion needs, and the gate
reports a finding against an item whose declaration was correct all along.
That is the wrong-population trap one level down, so the refusal sits in the
pre-dispatch preamble beside the node-timeout refusal, which exists for the
same reason: a config typo is discovered by the dispatch that would have run
with it, before any Fabro run exists.

THE IMPORT IS INSIDE THE TEST BODIES, deliberately. The module under test did
not exist when this file was authored, and a top-level import would have made
the Red a COLLECTION error — a failure proving only unimportability, never
that the behaviour was unimplemented. The first assertion is the module
path's own existence, which fails as a genuine assertion before any import is
attempted.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_NAME = "_dispatcher_sandbox_capabilities"
_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / f"{_MODULE_NAME}.py"
)
_IMPORT_PATH = f"livespec_orchestrator_beads_fabro.commands.{_MODULE_NAME}"


def _module() -> ModuleType:
    """The module under test, imported only after its file is proved present."""
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    return importlib.import_module(_IMPORT_PATH)


def _resolve(*, mirror: Any) -> Any:
    """The mirror resolution for a dispatcher block carrying `mirror` verbatim."""
    module = _module()
    block: dict[str, Any] = {module.SANDBOX_CAPABILITIES_KEY: mirror}
    return module.mirrored_sandbox_capabilities(block=block)


def test_the_module_names_the_published_capability_file_and_the_baseline() -> None:
    """The two literals the gate prompt and this module must not let drift.

    The prompt directs the gate to read `/etc/livespec/sandbox-capabilities`
    and names `terminal` as the baseline every image carries. Both strings are
    single-sourced here so the prompt's own binding test can compare against
    the module rather than against a second hand-typed copy.
    """
    module = _module()

    assert module.PUBLISHED_CAPABILITIES_PATH == "/etc/livespec/sandbox-capabilities"
    assert module.BASELINE_CAPABILITY == "terminal"
    assert module.SANDBOX_CAPABILITIES_KEY == "sandbox_capabilities"
    assert module.UNPUBLISHED_REPORT == "sandbox-capabilities: unpublished"


def test_a_conforming_mirror_resolves_to_its_names_in_order() -> None:
    """A list of lowercase snake_case names is ACCEPTED, order preserved."""
    assert _resolve(mirror=["terminal", "headless_browser", "tmux"]) == (
        "terminal",
        "headless_browser",
        "tmux",
    )


def test_an_absent_key_resolves_to_the_empty_unknown_set() -> None:
    """No mirror is an ANSWER, not a refusal: the set is simply unknown here.

    The contract withholds ONLY the missing-capability finding when the set is
    unknown, so an absent key must ride the success track — a refusal here
    would turn "this repository declares no mirror" into a failed dispatch.
    """
    module = _module()

    assert module.mirrored_sandbox_capabilities(block={}) == ()


def test_a_non_list_mirror_is_refused_naming_the_key() -> None:
    """A string where an array belongs is a config typo, named as one."""
    refusal = _resolve(mirror="terminal")

    assert isinstance(refusal, str)
    assert "dispatcher.sandbox_capabilities" in refusal
    assert "'terminal'" in refusal


def test_a_non_string_entry_is_refused_naming_the_entry() -> None:
    """A number among the names cannot be a capability, and says so."""
    refusal = _resolve(mirror=["terminal", 7])

    assert isinstance(refusal, str)
    assert "dispatcher.sandbox_capabilities" in refusal
    assert "7" in refusal


def test_a_name_that_is_not_lowercase_snake_case_is_refused_naming_the_name() -> None:
    """The three near-miss spellings a mirror actually acquires are all refused.

    Each of these is the spelling a human reaches for, and each would silently
    fail to match the capability the gate is looking for rather than erroring:
    the hyphenated form, the capitalised form, and the empty entry a trailing
    comma leaves behind.
    """
    for name in ("headless-browser", "HeadlessBrowser", ""):
        refusal = _resolve(mirror=["terminal", name])

        assert isinstance(refusal, str), name
        assert "dispatcher.sandbox_capabilities" in refusal, name
        assert "lowercase snake_case" in refusal, name


def test_a_digit_bearing_name_is_accepted_but_a_leading_digit_is_not() -> None:
    """snake_case admits digits after the first character and nowhere else."""
    assert _resolve(mirror=["x11_display"]) == ("x11_display",)

    refusal = _resolve(mirror=["3d_printer"])

    assert isinstance(refusal, str)
    assert "lowercase snake_case" in refusal


def test_this_repository_declares_the_four_capabilities_its_pinned_image_publishes() -> None:
    """The committed mirror of THIS repository, read through the real reader.

    Read from the repository's own `.livespec.jsonc` rather than a fixture:
    the assertion is about the delivered configuration state, so a fixture
    could not return the other answer.
    """
    module = _module()
    from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block

    resolved = module.mirrored_sandbox_capabilities(block=dispatcher_block(cwd=_REPO_ROOT))

    assert resolved == ("terminal", "headless_browser", "tmux", "herdr")


def test_the_repository_mirror_refuses_nothing_and_a_broken_one_refuses(
    tmp_path: Path,
) -> None:
    """The pre-dispatch seam: `None` to proceed, the refusal text to stop.

    Exercised through the repository's own committed configuration for the
    proceed arm — the positive control that the seam can return `None` at all
    — and through a written-out broken config for the refusal arm.
    """
    module = _module()

    assert module.sandbox_capabilities_refusal(repo=_REPO_ROOT) is None

    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": '
        '{"sandbox_capabilities": ["Headless-Browser"]}}}',
        encoding="utf-8",
    )
    refusal = module.sandbox_capabilities_refusal(repo=tmp_path)

    assert isinstance(refusal, str)
    assert "lowercase snake_case" in refusal
