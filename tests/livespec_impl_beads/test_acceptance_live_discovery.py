"""Edge-case coverage for LIVE greeting-module discovery.

The happy-path live assertion is covered by `test_acceptance_live`. This
module exercises the discovery branches that a malformed merged checkout
can produce: no `greet` at all, more than one `greet`-defining module, a
non-importable sibling `.py`, and a `greet` symbol that is not callable.
Each is a factory bug the live runner must surface rather than fake.
"""

from pathlib import Path

import pytest
from livespec_impl_beads.acceptance import (
    GreetDiscoveryError,
    LiveAcceptanceConfig,
    run_live_acceptance,
)


def _seed_spec(*, checkout: Path) -> None:
    spec_root = checkout / "SPECIFICATION"
    spec_root.mkdir(parents=True)
    _ = (spec_root / "spec.md").write_text("# greet-me\n", encoding="utf-8")


def test_no_greet_module_raises(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    _seed_spec(checkout=checkout)
    _ = (checkout / "unrelated.py").write_text(
        "def farewell(name: str) -> str:\n    return name\n",
        encoding="utf-8",
    )

    with pytest.raises(GreetDiscoveryError, match="no module exposing"):
        _ = run_live_acceptance(config=LiveAcceptanceConfig(checkout=checkout, name="Ada"))


def test_multiple_greet_modules_raises(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    _seed_spec(checkout=checkout)
    for stem in ("a", "b"):
        _ = (checkout / f"{stem}.py").write_text(
            "def greet(name: str) -> str:\n    return f'Hello, {name}!'\n",
            encoding="utf-8",
        )

    with pytest.raises(GreetDiscoveryError, match="expected exactly one module"):
        _ = run_live_acceptance(config=LiveAcceptanceConfig(checkout=checkout, name="Ada"))


def test_non_importable_sibling_is_skipped(tmp_path: Path) -> None:
    """A `.py` that raises on import is not a candidate; the real one wins."""
    checkout = tmp_path / "checkout"
    _seed_spec(checkout=checkout)
    # Mentions `greet` (passes the cheap text prefilter) but raises on import.
    _ = (checkout / "broken.py").write_text(
        "raise RuntimeError('greet boom on import')\n",
        encoding="utf-8",
    )
    good = checkout / "greeting.py"
    _ = good.write_text(
        "def greet(name: str) -> str:\n    return f'Hello, {name}!'\n",
        encoding="utf-8",
    )

    result = run_live_acceptance(config=LiveAcceptanceConfig(checkout=checkout, name="Ada"))

    assert result.generated_program == good
    assert result.greeting == "Hello, Ada!"


def test_non_callable_greet_is_skipped(tmp_path: Path) -> None:
    """A module binding `greet` to a non-callable does not qualify."""
    checkout = tmp_path / "checkout"
    _seed_spec(checkout=checkout)
    _ = (checkout / "constant.py").write_text("greet = 42\n", encoding="utf-8")
    good = checkout / "greeting.py"
    _ = good.write_text(
        "def greet(name: str) -> str:\n    return f'Hello, {name}!'\n",
        encoding="utf-8",
    )

    result = run_live_acceptance(config=LiveAcceptanceConfig(checkout=checkout, name="Ada"))

    assert result.generated_program == good
