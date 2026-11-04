"""The proof-only arm's sandbox is the merged pull request's head, read-only."""

from __future__ import annotations

import argparse
import importlib
from typing import Any

import tomli

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry"
_ITEM = "bd-ib-ixmxqy"
_BRANCH = f"feat/{_ITEM}"
_HEAD = "1" * 40
_PULL_REF = "refs/pull/4137/head"


def _module() -> Any:
    """Load the resume-entry module from the plugin package."""
    return importlib.import_module(_MODULE)


def _proof_only_block() -> str:
    """The prepare script a proof-only invocation renders, built from its arguments."""
    module = _module()
    args = argparse.Namespace(
        **{
            module.RESUME_HEAD_ARG: _HEAD,
            module.RESUME_FETCH_REF_ARG: _PULL_REF,
            module.RESUME_PROOF_ONLY_ARG: True,
        }
    )
    checkout = module.resume_checkout_for(args=args, branch=_BRANCH)
    assert checkout is not None
    block = str(module.resume_checkout_prepare_steps_block(checkout=checkout))
    return str(tomli.loads(block)["run"]["prepare"]["steps"][0]["script"])


def test_the_proof_only_checkout_is_the_head_at_merge_fetched_from_the_pull_ref() -> None:
    """The head commit is checked out detached from the pull ref, never a merge commit."""
    block = _proof_only_block()
    assert _PULL_REF in block
    assert f"git checkout --detach {_HEAD}" in block
    assert f'test "$(git rev-parse HEAD)" = {_HEAD}' in block


def test_the_proof_only_checkout_cannot_push() -> None:
    """Read-only is mechanical: the clone's push destination is disabled."""
    block = _proof_only_block()
    assert "git remote set-url --push origin" in block
    assert "set -e" in block


def test_an_ordinary_resume_checkout_is_not_made_read_only() -> None:
    """The resume that must push its own publish branch keeps a working push."""
    module = _module()
    args = argparse.Namespace(**{module.RESUME_HEAD_ARG: _HEAD})
    checkout = module.resume_checkout_for(args=args, branch=_BRANCH)
    assert checkout is not None
    block = module.resume_checkout_prepare_steps_block(checkout=checkout)
    assert f"refs/heads/{_BRANCH}" in block
    assert "set-url" not in block
    assert getattr(checkout, "read_only", None) is False
