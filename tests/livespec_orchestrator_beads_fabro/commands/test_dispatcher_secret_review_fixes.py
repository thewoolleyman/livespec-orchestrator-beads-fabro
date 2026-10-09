"""Regression coverage for the accepted native-secret review findings.

These cases bind the three failure modes found after the first implementation:
server rejections must be scrubbed before they are shortened, overlapping
launches must never address the same vault entry, and residual detection must
search the exact JSON/TOML rendering that the overlay renderer emits.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import (
    SECRET_CHANNEL_NATIVE_SECRETS,
    RoutedOverlay,
    SecretChannelRefusal,
    VaultSecret,
    route_secrets_through_vault,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_vault import FabroVaultSink

_REVIEW_VAULT_KEY = "LIVESPEC_DISPATCH_REVIEW_GITHUB_TOKEN"


@dataclass(kw_only=True)
class _RejectingRunner:
    """A vault command runner that echoes the submitted value in its failure."""

    rejection: str

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = argv, cwd, timeout_seconds, env, stdin
        return CommandResult(exit_code=2, stdout="", stderr=self.rejection)


def _route(*, text: str, value_name: str, scope: str) -> RoutedOverlay | SecretChannelRefusal:
    """Call the routing seam across the Red interface transition.

    Before the fix the seam has no launch scope; after it, the same helper passes
    the scope. Keeping that compatibility here makes Red fail on the behavioural
    assertion (shared keys), rather than on an unexpected-keyword ``TypeError``.
    """
    route = cast(
        "Callable[..., RoutedOverlay | SecretChannelRefusal]",
        route_secrets_through_vault,
    )
    kwargs: dict[str, object] = {
        "overlay_text": text,
        "channel": SECRET_CHANNEL_NATIVE_SECRETS,
        "env_names": (value_name,),
    }
    if "scope" in inspect.signature(route_secrets_through_vault).parameters:
        kwargs["scope"] = scope
    return route(**kwargs)


def test_rejection_is_scrubbed_before_its_excerpt_is_taken() -> None:
    """A long echoed credential cannot leave a recognizable truncated prefix."""
    value = "long-credential-canary-" + ("v" * 600)
    runner = _RejectingRunner(rejection=f"server rejected {value}: invalid value")
    sink = FabroVaultSink(
        fabro_bin="/usr/local/bin/fabro",
        server_url=None,
        runner=runner,
        cwd=Path("/workspace/repo"),
    )
    message = cast(
        "str",
        sink.set(
            secret=VaultSecret(
                env_name="GITHUB_TOKEN",
                secret_name=_REVIEW_VAULT_KEY,
                value=value,
            )
        ),
    )
    assert "long-credential-canary-" not in message
    assert "<value withheld>" in message


def test_overlapping_launches_route_to_distinct_vault_entries() -> None:
    """One launch cannot overwrite globally addressed entries another references."""
    first = _route(
        text=f"[environments.sandbox.env]\nGITHUB_TOKEN = {json.dumps('first-value')}\n",
        value_name="GITHUB_TOKEN",
        scope="dispatch-first",
    )
    second = _route(
        text=f"[environments.sandbox.env]\nGITHUB_TOKEN = {json.dumps('second-value')}\n",
        value_name="GITHUB_TOKEN",
        scope="dispatch-second",
    )
    assert isinstance(first, RoutedOverlay)
    assert isinstance(second, RoutedOverlay)
    assert first.secrets[0].secret_name != second.secrets[0].secret_name
    assert first.secrets[0].secret_name in first.overlay_text
    assert second.secrets[0].secret_name in second.overlay_text


def test_residual_guard_matches_the_overlay_renderers_exact_encoding() -> None:
    """Encoded newlines, controls and non-ASCII cannot evade residual refusal."""
    value = "first line\nsecond line\x01snowman:\u2603"
    bundle = (
        "[environments.sandbox.env]\n"
        f"GITHUB_TOKEN = {json.dumps(value)}\n"
        "\n[[run.prepare.steps]]\n"
        f"script = {json.dumps(f'use duplicated credential {value}')}\n"
    )
    result = _route(text=bundle, value_name="GITHUB_TOKEN", scope="dispatch-residual")
    assert isinstance(result, SecretChannelRefusal)
    assert "resolved value still appears" in result.message
    assert value not in result.message
