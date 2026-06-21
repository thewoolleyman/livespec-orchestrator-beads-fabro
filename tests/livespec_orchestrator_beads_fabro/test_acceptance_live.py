"""Tests for the LIVE Beads/Fabro greeting assertion (`run_live_acceptance`).

The live tier's runtime leg (creating a throwaway GitHub repo, running the
container/Fabro factory, merging the PR) is exercised by the operator-only
`just acceptance-live-golden-master` target under the 1Password wrapper. The
unit under test here is the PURE-ish discovery + assertion entry point the
live orchestration calls once it has a checkout of the merged repo: it locates
the generated `greet`, calls it, and returns the `AcceptanceResult` the live
tier asserts on. That logic is hermetic — given a checkout on disk it needs no
network — so it is covered here against a seeded checkout.
"""

from pathlib import Path

from livespec_orchestrator_beads_fabro.acceptance import LiveAcceptanceConfig, run_live_acceptance


def _seed_merged_checkout(*, checkout: Path) -> Path:
    """Seed a throwaway-repo checkout shaped like a merged Fabro output.

    The generated program lives under a `src/` package (a plausible Fabro
    layout), and the checkout also carries decoy directories the scan MUST
    skip (`.git`, `SPECIFICATION`, `__pycache__`) and an unrelated module
    that does NOT define `greet`. The discovery must still find the single
    `greet`-defining module and ignore everything else.
    """
    (checkout / ".git").mkdir(parents=True)
    _ = (checkout / ".git" / "config").write_text("[core]\n", encoding="utf-8")

    spec_root = checkout / "SPECIFICATION"
    spec_root.mkdir(parents=True)
    _ = (spec_root / "spec.md").write_text("# greet-me\n", encoding="utf-8")
    # A `.py` under SPECIFICATION must be skipped even though it defines greet.
    _ = (spec_root / "decoy_spec_greet.py").write_text(
        "def greet(name: str) -> str:\n    return f'WRONG-{name}'\n",
        encoding="utf-8",
    )

    pycache = checkout / "src" / "__pycache__"
    pycache.mkdir(parents=True)
    _ = (pycache / "stale.py").write_text(
        "def greet(name: str) -> str:\n    return 'STALE'\n",
        encoding="utf-8",
    )

    _ = (checkout / "src" / "unrelated.py").write_text(
        "def farewell(name: str) -> str:\n    return f'Bye, {name}.'\n",
        encoding="utf-8",
    )
    generated = checkout / "src" / "greeting.py"
    _ = generated.write_text(
        '"""Generated greeting program."""\n\n\ndef greet(name: str) -> str:\n'
        '    return f"Hello, {name}!"\n',
        encoding="utf-8",
    )
    return generated


def test_run_live_acceptance_asserts_merged_repo_greeting(tmp_path: Path) -> None:
    checkout = tmp_path / "merged-checkout"
    generated = _seed_merged_checkout(checkout=checkout)

    result = run_live_acceptance(
        config=LiveAcceptanceConfig(checkout=checkout, name="Ada"),
    )

    assert result.orchestrator_tier == "beads-fabro-live"
    assert result.greeting == "Hello, Ada!"
    assert result.generated_program == generated
    assert result.fixture_name == "greet-me"
