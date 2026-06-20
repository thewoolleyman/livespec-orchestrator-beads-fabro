"""The greeting assertion must work whether `greet` is positional or kw-only.

The fixture contract is `greet(name: str) -> str` (parameter named `name`),
which a generator may satisfy with a positional parameter OR — following the
livespec family keyword-only discipline — a keyword-only one (`def greet(*,
name: str)`). A real merged Fabro run produced exactly the keyword-only form,
and its own test called `greet(name="Ada")`. The live assertion must invoke
`greet` faithfully in either case rather than assuming a positional call (which
raised `TypeError: greet() takes 0 positional arguments but 1 was given`).
"""

from pathlib import Path

from livespec_impl_beads.acceptance import LiveAcceptanceConfig, run_live_acceptance


def _seed_kwonly_greet(*, checkout: Path) -> None:
    (checkout / "SPECIFICATION").mkdir(parents=True)
    _ = (checkout / "SPECIFICATION" / "spec.md").write_text("# greet-me\n", encoding="utf-8")
    # Keyword-only greet — the family discipline the Fabro agent followed.
    _ = (checkout / "greet.py").write_text(
        "def greet(*, name: str) -> str:\n    return f'Hello, {name}!'\n",
        encoding="utf-8",
    )


def test_run_live_acceptance_handles_keyword_only_greet(tmp_path: Path) -> None:
    checkout = tmp_path / "merged"
    _seed_kwonly_greet(checkout=checkout)

    result = run_live_acceptance(config=LiveAcceptanceConfig(checkout=checkout, name="Ada"))

    assert result.greeting == "Hello, Ada!"
    assert result.orchestrator_tier == "beads-fabro-live"
