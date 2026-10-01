"""The `just check` runner executes the target list the justfile declares.

The justfile `check:` recipe holds the aggregate's ONE declared target list —
the `targets=(...)` array the shared `aggregate_completeness` gate parses to
prove every canonical slug is wired. `dev-tooling/just-check.sh` used to carry
a SECOND, hardcoded copy of that array and ignore the declaration entirely, so
the fleet gate certified one list while the runner executed another. Ten
declared slugs never ran under `just check`, pre-push or the in-run janitor
gate, and `check-spec-governance-default-block` sat red on master for six weeks
while two gate runs reported `All 80 targets passed` (work-item bd-ib-mxqrr4).

A single declaration cannot be checked by asking the declaration about itself,
so every assertion below reads the executed list back through the extractor's
own process — `bash dev-tooling/aggregate-targets.sh` — and compares it against
an INDEPENDENT Python parse of the justfile. Two instruments, two languages: a
regression in either (a reintroduced hardcoded array, a broken awk program, a
renamed heredoc marker) makes them disagree. The real repository's parity is
asserted directly, so the guard cannot pass by measuring only synthetic input.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXTRACTOR = Path("dev-tooling") / "aggregate-targets.sh"
_RUNNER = Path("dev-tooling") / "just-check.sh"

# The ten slugs the hardcoded runner array omitted. Each one is named here
# rather than derived, because deriving them from the same justfile the
# extractor reads would make the assertion unable to fail.
_PREVIOUSLY_UNRUN = (
    "check-ci-gate-parity",
    "check-fabro-graph-validity",
    "check-heading-coverage-debt-register",
    "check-marketplace-ref-release-only",
    "check-plan-no-live-handoff-file",
    "check-plan-record-conformance",
    "check-self-hosted-uv-lane",
    "check-spec-governance-default-block",
    "check-work-item-interpolation-delimiters",
    "check-work-item-status-vocabulary",
)

_CHECK_RECIPE_HEADER = re.compile(r"^check:[ \t]*$")
_ARRAY_START = re.compile(r"^[ \t]*targets=\([ \t]*$")
_ARRAY_END = re.compile(r"^[ \t]*\)[ \t]*$")


def _declared_targets(*, justfile_text: str) -> list[str]:
    """Parse the `check:` recipe's `targets=(...)` array — the independent instrument.

    Deliberately a hand-rolled line walk rather than a call into the extractor
    or into `livespec_dev_tooling.checks.aggregate_completeness`: a second
    reading taken with the first reading's own code is one measurement, not two.
    The rules mirror what the shared gate applies — the recipe body runs to the
    next unindented line carrying a colon, the first `targets=(` opens the
    array, a bare `)` closes it, and each line is comment-stripped, trimmed and
    kept only when it starts with `check-`.
    """
    in_recipe = False
    in_array = False
    declared: list[str] = []
    for line in justfile_text.splitlines():
        if not in_recipe:
            in_recipe = _CHECK_RECIPE_HEADER.match(line) is not None
            continue
        if line and not line.startswith((" ", "\t")) and ":" in line:
            break
        if not in_array:
            in_array = _ARRAY_START.match(line) is not None
            continue
        if _ARRAY_END.match(line) is not None:
            break
        token = line.split("#", 1)[0].strip()
        if token.startswith("check-"):
            declared.append(token)
    return declared


def _run(
    *, argv: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy()
    if env is not None:
        run_env.update(env)
    return subprocess.run(argv, cwd=cwd, env=run_env, check=False, capture_output=True, text=True)


def _extracted_targets(*, repo: Path) -> list[str]:
    result = _run(argv=["bash", str(repo / _EXTRACTOR)], cwd=repo)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.split()


def _seed_repo(*, tmp_path: Path, slugs: tuple[str, ...]) -> Path:
    """A synthetic repo carrying the REAL scripts and a justfile declaring `slugs`."""
    repo = tmp_path / "repo"
    (repo / "dev-tooling").mkdir(parents=True)
    for relative in (_EXTRACTOR, _RUNNER):
        _ = shutil.copyfile(_REPO_ROOT / relative, repo / relative)
    declaration = "".join(f"        {slug}\n" for slug in slugs)
    _ = (repo / "justfile").write_text(
        "some-other-recipe:\n    echo not-the-aggregate\n\n"
        "check:\n"
        "    #!/usr/bin/env bash\n"
        "    set -uo pipefail\n"
        "    : <<'LIVESPEC_AGGREGATE_TARGETS'\n"
        "    targets=(\n"
        f"{declaration}"
        "    )\n"
        "    LIVESPEC_AGGREGATE_TARGETS\n"
        "    bash dev-tooling/just-check.sh\n",
        encoding="utf-8",
    )
    return repo


def _install_fakes(*, repo: Path) -> dict[str, str]:
    """Put a recording `just` and a no-op `uv` on PATH so the runner can be driven."""
    bin_dir = repo / "fake-bin"
    bin_dir.mkdir()
    for name, body in (
        ("just", 'printf "%s\\n" "$*" >> just.log\n'),
        ("uv", "exit 0\n"),
    ):
        tool = bin_dir / name
        _ = tool.write_text(f"#!/usr/bin/env bash\nset -uo pipefail\n{body}", encoding="utf-8")
        tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    return {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}


def test_the_parser_drops_comments_and_tokens_that_are_not_check_slugs() -> None:
    """The guard's own instrument, pinned on every arm it has.

    An untested parser is the very failure this work-item is a case of: a clean,
    plausible reading that cannot report the thing it is aimed at. Here the
    array holds a comment, a non-`check-` aggregate sub-target, and one real
    slug, and only the slug survives — while `check-dropped`, which sits in the
    recipe but OUTSIDE the array, must not.
    """
    justfile_text = (
        "check:\n"
        "    targets=(\n"
        "        # a comment naming check-commented\n"
        "        bootstrap\n"
        "        check-kept\n"
        "    )\n"
        "    check-dropped\n"
    )

    assert _declared_targets(justfile_text=justfile_text) == ["check-kept"]


def test_the_parser_stops_at_the_next_recipe_when_the_aggregate_declares_no_array() -> None:
    """A later recipe's array must not be mistaken for the aggregate's own."""
    justfile_text = (
        "check:\n"
        "    echo no array here\n"
        "next-recipe:\n"
        "    targets=(\n"
        "        check-elsewhere\n"
        "    )\n"
    )

    assert _declared_targets(justfile_text=justfile_text) == []


def test_the_parser_returns_what_it_saw_when_the_array_never_closes() -> None:
    """An unterminated array yields a SHORT list — which is why the extractor refuses it.

    The extractor exits non-zero on this input rather than printing a partial
    set, so the two instruments disagree here by design: this test pins what the
    partial reading would have been, and the extractor's own refusal test pins
    that the runner never executes it.
    """
    justfile_text = "check:\n    targets=(\n        check-seen\n"

    assert _declared_targets(justfile_text=justfile_text) == ["check-seen"]


def test_the_runner_executes_exactly_the_justfile_declared_list() -> None:
    """The load-bearing case: the COMMITTED declaration and the extractor agree."""
    declared = _declared_targets(
        justfile_text=(_REPO_ROOT / "justfile").read_text(encoding="utf-8")
    )

    assert _extracted_targets(repo=_REPO_ROOT) == declared


def test_the_committed_declaration_is_a_populated_list() -> None:
    """Control: an empty declaration would make the parity test pass vacuously."""
    declared = _declared_targets(
        justfile_text=(_REPO_ROOT / "justfile").read_text(encoding="utf-8")
    )

    assert len(declared) > 50
    assert declared.count("check-aggregate-completeness") == 1


def test_every_previously_unrun_slug_is_in_the_executed_set() -> None:
    extracted = _extracted_targets(repo=_REPO_ROOT)

    assert [slug for slug in _PREVIOUSLY_UNRUN if slug not in extracted] == []


def test_a_slug_added_to_the_declaration_reaches_the_executed_set(*, tmp_path: Path) -> None:
    """The regression this guard exists for: a declared slug the runner never runs.

    `check-newly-declared` appears in no justfile recipe and in no hardcoded
    array anywhere in the repository, so it can reach the executed set only by
    being DERIVED from the declaration — the property whose absence left ten
    slugs unrun. A runner carrying its own list would omit it while still
    returning a plausible, non-empty target list.
    """
    repo = _seed_repo(tmp_path=tmp_path, slugs=("check-first", "check-newly-declared"))

    assert _extracted_targets(repo=repo) == ["check-first", "check-newly-declared"]


def test_the_runner_reports_the_count_it_actually_executed(*, tmp_path: Path) -> None:
    slugs = ("check-first", "check-second", "check-newly-declared")
    repo = _seed_repo(tmp_path=tmp_path, slugs=slugs)
    env = _install_fakes(repo=repo)

    result = _run(argv=["bash", str(repo / _RUNNER)], cwd=repo, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"All {len(slugs)} targets passed." in result.stdout
    assert (repo / "just.log").read_text(encoding="utf-8").split() == list(slugs)


def test_the_count_excludes_skipped_targets_and_says_how_many_were_skipped(
    *, tmp_path: Path
) -> None:
    """A skipped target is not a passed target.

    `check-skipping` is the route pre-commit takes, so this is the summary a
    commit gate prints. Counting the declared length there would report the same
    number a full run reports — broader assurance than the run earned, which is
    the same false green a stale hardcoded list produced.
    """
    slugs = ("check-first", "check-second", "check-third")
    repo = _seed_repo(tmp_path=tmp_path, slugs=slugs)
    env = _install_fakes(repo=repo)

    result = _run(argv=["bash", str(repo / _RUNNER), "check-second"], cwd=repo, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "All 2 targets passed (1 of 3 declared skipped)." in result.stdout
    assert (repo / "just.log").read_text(encoding="utf-8").split() == [
        "check-first",
        "check-third",
    ]


def test_the_runner_refuses_a_justfile_whose_aggregate_declares_nothing(*, tmp_path: Path) -> None:
    """Fail-closed: an unparseable declaration must stop the aggregate, not empty it.

    A runner that silently ran zero targets would print a passing summary — the
    same observation a fully green aggregate produces, which is precisely the
    false green this work-item removes.
    """
    repo = _seed_repo(tmp_path=tmp_path, slugs=())
    env = _install_fakes(repo=repo)

    result = _run(argv=["bash", str(repo / _RUNNER)], cwd=repo, env=env)

    assert result.returncode != 0
    assert "targets passed" not in result.stdout
    assert not (repo / "just.log").exists()


def test_the_extractor_refuses_an_unterminated_array_instead_of_a_partial_list(
    *, tmp_path: Path
) -> None:
    """Fail-closed on the input whose partial reading the parser test pins.

    A truncated declaration must stop the aggregate, not quietly shrink it —
    that shrinking is precisely how ten slugs went unrun while the summary line
    still read as a pass.
    """
    repo = _seed_repo(tmp_path=tmp_path, slugs=("check-first",))
    justfile = repo / "justfile"
    truncated = justfile.read_text(encoding="utf-8").replace("    )\n", "")
    _ = justfile.write_text(truncated, encoding="utf-8")

    result = _run(argv=["bash", str(repo / _EXTRACTOR)], cwd=repo)

    assert result.returncode != 0
    assert "unterminated" in result.stderr
    assert "check-first" not in result.stdout
