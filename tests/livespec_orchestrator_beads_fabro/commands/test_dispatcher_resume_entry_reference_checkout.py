"""A stale seed's preserved ref is fetched into the sandbox as a reference, not checked out."""

from __future__ import annotations

import argparse
import importlib
from typing import Any

import tomli

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry"
_ITEM = "bd-ib-zzhy5t"
_BRANCH = f"feat/{_ITEM}"
_COMMIT = "3" * 40
_REF = "refs/heads/needs-human/01M6N2HSWGJSR97HJK7J736AQ8"


def _module() -> Any:
    """Load the resume-entry module from the plugin package."""
    return importlib.import_module(_MODULE)


def _reference_args() -> argparse.Namespace:
    """The arguments a fresh route for a stale seed carries."""
    return argparse.Namespace(resume_fetch_ref=_REF, resume_reference_commit=_COMMIT)


def _script() -> str:
    """The prepare script the reference arguments render."""
    module = _module()
    checkout = module.resume_checkout_for(args=_reference_args(), branch=_BRANCH)
    assert checkout is not None
    block = str(module.resume_checkout_prepare_steps_block(checkout=checkout))
    return str(tomli.loads(block)["run"]["prepare"]["steps"][0]["script"])


def test_a_reference_is_fetched_from_the_preservation_ref_and_verified() -> None:
    """The ref is fetched and the commit must have arrived, so the reference is usable."""
    script = _script()
    assert _REF in script
    assert _COMMIT in script
    assert "set -e" in script


def test_a_reference_is_never_checked_out() -> None:
    """The sandbox stays on the default branch's tree, which carries the current hook body."""
    assert "checkout" not in _script()
