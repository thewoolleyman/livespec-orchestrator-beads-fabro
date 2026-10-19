"""Tests for the test-suite real-time gate.

The gate reports an ABSENCE — a test that sleeps in real time, or asserts on a
difference of real clock readings — so a scan that walked the wrong tree, or a
matcher that stopped recognising a form, prints exactly what a clean suite
prints. Every case here therefore either asserts against a SEEDED source read
through the gate's own matcher, or asserts that one of its two positive
controls fires when it should.

The REPOSITORY'S OWN tests tree is the happy-path fixture, deliberately. The
gate's contract is that this suite is clean, and nothing short of reading it
establishes that: a hand-written clean file would pass against a matcher
pointed at nothing at all.

The gate is loaded INSIDE each test body rather than by a pytest fixture, and
that is not stylistic. It lives outside the pytest path roots, so it is loaded
by path; done in a fixture, the "does this module exist yet" assertion reports
as a setup ERROR rather than as a failing assertion, which is exactly the
distinction the Red of a new module turns on.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "tests_no_real_time.py"
_CONTROL_FIXTURE = Path("dev-tooling") / "checks" / "fixtures" / "real_time_control.py.txt"


def _load_check() -> ModuleType:
    """Import the gate by path, asserting it exists before trying to."""
    assert _CHECK_PATH.is_file(), f"{_CHECK_PATH} does not exist"
    spec = importlib.util.spec_from_file_location("tests_no_real_time", _CHECK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _seed_tests_tree(*, root: Path, sources: dict[str, str]) -> None:
    tests = root / "tests"
    tests.mkdir(parents=True)
    for name, source in sources.items():
        _ = (tests / name).write_text(source, encoding="utf-8")


def test_a_real_sleep_is_refused_naming_its_file_and_line() -> None:
    """The first form: a wait whose length the host decides."""
    check = _load_check()
    source = "import time\n\n\ndef test_x() -> None:\n    time.sleep(0.25)\n"

    found = check.file_findings(source=source, label="tests/test_x.py")

    assert found == ["tests/test_x.py:5: waits in real time through time.sleep"]


def test_an_elapsed_difference_assertion_is_refused_naming_its_file_and_line() -> None:
    """The second form, through the ordinary two-line spelling of it."""
    check = _load_check()
    source = (
        "import time\n"
        "\n"
        "\n"
        "def test_x() -> None:\n"
        "    started = time.monotonic()\n"
        "    elapsed = time.monotonic() - started\n"
        "    assert elapsed < 5.0\n"
    )

    found = check.file_findings(source=source, label="tests/test_x.py")

    assert found == ["tests/test_x.py:7: asserts on a difference of real clock readings"]


def test_a_clock_reading_used_as_fixture_data_is_not_refused() -> None:
    """The exclusion that keeps the gate pointed at the flaky class.

    A reading SEEDS a value here and renders no verdict, so neither the
    assignment nor the assertion on the result is an offence. Without this the
    gate would fire on every test that mentions time, which is how a gate comes
    to be switched off.
    """
    check = _load_check()
    source = (
        "import time\n"
        "\n"
        "\n"
        "def test_x() -> None:\n"
        "    deadline = int(time.time()) + 3600\n"
        "    assert deadline > 0\n"
        "    assert deadline - 3600 > 0\n"
    )

    assert check.file_findings(source=source, label="tests/test_x.py") == []


def test_a_name_tracked_in_one_scope_does_not_taint_another() -> None:
    """Per-scope tracking, which is what stops the over-reporting.

    The first function makes `elapsed` a real difference; the second binds the
    same name to something ordinary. A flat, module-wide reading of names
    reports the second function too, and a gate that reports a correct test is
    a gate that gets removed.
    """
    check = _load_check()
    source = (
        "import time\n"
        "\n"
        "\n"
        "def test_measured() -> None:\n"
        "    started = time.monotonic()\n"
        "    elapsed = time.monotonic() - started\n"
        "    assert elapsed < 5.0\n"
        "\n"
        "\n"
        "def test_unmeasured() -> None:\n"
        "    elapsed = len('not a measurement')\n"
        "    assert elapsed < 5.0\n"
    )

    found = check.file_findings(source=source, label="tests/test_x.py")

    assert found == ["tests/test_x.py:7: asserts on a difference of real clock readings"]


def test_a_deterministic_tree_passing_both_controls_reports_nothing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The composition's happy path: a clean tree AND both controls satisfied.

    The COMMITTED control fixture is what gets copied in, so the matcher
    control runs for real here rather than against a reduced stand-in. Only the
    discovery floor is lowered, because it is the one thing a seeded tree cannot
    satisfy honestly: seeding hundreds of files to clear it would make the case
    about the fixture rather than about the gate.
    """
    check = _load_check()
    monkeypatch.setattr(check, "MINIMUM_SCANNED_FILES", 1)
    fixture = tmp_path / _CONTROL_FIXTURE
    fixture.parent.mkdir(parents=True)
    _ = fixture.write_text(
        (_REPO_ROOT / _CONTROL_FIXTURE).read_text(encoding="utf-8"), encoding="utf-8"
    )
    _seed_tests_tree(
        root=tmp_path,
        sources={"test_a.py": "import time\n\n\ndef test_a() -> None:\n    assert time.time()\n"},
    )

    assert check.findings(repo_root=tmp_path) == []


def test_the_discovery_control_fires_on_a_tree_too_small_to_be_the_suite(*, tmp_path: Path) -> None:
    """A walk that lost the tree must say so rather than report clean.

    Both controls fire here, and both are the point: a two-file tree is not
    this suite, and a repository root carrying no control fixture cannot have
    had its matcher checked at all.
    """
    check = _load_check()
    _seed_tests_tree(
        root=tmp_path,
        sources={"test_a.py": "def test_a() -> None:\n    assert True\n", "test_b.py": "\n"},
    )

    found = check.findings(repo_root=tmp_path)

    assert f"control: the tests walk returned 2, below {check.MINIMUM_SCANNED_FILES}" in found
    assert f"control: the matcher control fixture {_CONTROL_FIXTURE} is missing" in found


def test_the_matcher_control_fires_when_a_marked_form_stops_being_found(*, tmp_path: Path) -> None:
    """A matcher that went blind must fail rather than certify the suite.

    The fixture is copied with one marked offence NEUTERED — its sleep becomes
    an ordinary call — so the markers still claim that line and the matcher no
    longer finds it. That is exactly the shape of a matcher regression, and it
    is the one thing a clean scan of 860 files cannot distinguish from health.
    """
    check = _load_check()
    fixture = tmp_path / _CONTROL_FIXTURE
    fixture.parent.mkdir(parents=True)
    original = (_REPO_ROOT / _CONTROL_FIXTURE).read_text(encoding="utf-8")
    _ = fixture.write_text(original.replace("time.sleep(0.05)", "len('x')", 1), encoding="utf-8")
    _seed_tests_tree(root=tmp_path, sources={"test_a.py": "\n"})

    found = [entry for entry in check.findings(repo_root=tmp_path) if "its markers say" in entry]

    assert found, "a matcher that lost a marked form reported nothing"
    assert all(str(_CONTROL_FIXTURE) in entry for entry in found)


def test_main_reports_every_finding_and_exits_non_zero(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The entry point's two outcomes, and that a finding reaches stderr.

    `findings` is stood in rather than reproduced on disk: the composition is
    asserted above against real trees, and what is left to establish here is
    that `main` renders what it was given and grades on whether there was any.
    """
    check = _load_check()
    monkeypatch.setattr(check, "findings", lambda **_kwargs: ["tests/test_x.py:5: a finding"])
    assert check.main() == 1
    assert "tests/test_x.py:5: a finding" in capsys.readouterr().err

    monkeypatch.setattr(check, "findings", lambda **_kwargs: [])
    assert check.main() == 0


def test_an_occurrence_is_stood_down_by_a_marker_carrying_a_reason() -> None:
    """The stand-down, for a test whose subject genuinely IS real time."""
    check = _load_check()
    source = (
        "import time\n"
        "\n"
        "\n"
        "def test_x() -> None:\n"
        "    time.sleep(0.25)  # real-time-required: the host clock is the subject\n"
    )

    assert check.file_findings(source=source, label="tests/test_x.py") == []


def test_a_marker_on_the_line_above_binds_to_the_occurrence() -> None:
    """One line of lead-in, because a reason worth reading rarely fits after.

    The alternative authors reach for is a reason trimmed until it says
    nothing, which is the opposite of what a written reason is for.
    """
    check = _load_check()
    source = (
        "import time\n"
        "\n"
        "\n"
        "def test_x() -> None:\n"
        "    # real-time-required: a real subprocess exits on an absolute epoch\n"
        "    time.sleep(0.25)\n"
    )

    assert check.file_findings(source=source, label="tests/test_x.py") == []


def test_a_reasoned_marker_does_not_stand_down_a_second_offence_in_its_function() -> None:
    """An exemption belongs to its occurrence, never to the containing function."""
    check = _load_check()
    source = (
        "import time\n"
        "\n"
        "\n"
        "def test_x() -> None:\n"
        "    time.sleep(0.25)  # real-time-required: the host clock is the subject\n"
        "    _ = None\n"
        "    time.sleep(0.25)\n"
    )

    found = check.file_findings(source=source, label="tests/test_x.py")

    assert found == ["tests/test_x.py:7: waits in real time through time.sleep"]


def test_a_marker_further_above_does_not_reach_the_occurrence() -> None:
    """The binding region is bounded, so a marker cannot cover a whole block.

    Without this the lead-in line would degrade into a file-level pragma by
    accident: one marker near the top would quietly stand down everything
    under it, which is precisely what a per-occurrence exemption is not.
    """
    check = _load_check()
    source = (
        "import time\n"
        "\n"
        "\n"
        "def test_x() -> None:\n"
        "    # real-time-required: too far above to bind\n"
        "    _ = len('one line of lead-in, and no more')\n"
        "    time.sleep(0.25)\n"
    )

    found = check.file_findings(source=source, label="tests/test_x.py")

    assert found == ["tests/test_x.py:7: waits in real time through time.sleep"]


def test_a_marker_with_no_reason_is_itself_the_finding() -> None:
    """An exemption nobody justified is the shape this gate exists to stop.

    Accepting a bare marker would make the written reason advisory, and an
    advisory reason is one that stops being written. The finding is DISTINCT
    from the offence's own, so the remedy it asks for is the right one.
    """
    check = _load_check()
    source = (
        "import time\n"
        "\n"
        "\n"
        "def test_x() -> None:\n"
        "    time.sleep(0.25)  # real-time-required:\n"
    )

    found = check.file_findings(source=source, label="tests/test_x.py")

    assert found == ["tests/test_x.py:5: carries an exemption marker with no written reason"]


def test_a_wrapped_assertion_takes_the_marker_on_any_of_its_own_lines() -> None:
    """A multi-line assertion is ONE occurrence, so its whole span binds.

    Its finding is reported at the `assert` line, and a marker is accepted
    anywhere the expression reaches — otherwise an assertion whose first line
    is already full could never be stood down at all.
    """
    check = _load_check()
    source = (
        "import time\n"
        "\n"
        "\n"
        "def test_x() -> None:\n"
        "    started = time.monotonic()\n"
        "    elapsed = time.monotonic() - started\n"
        "    assert (\n"
        "        elapsed < 5.0\n"
        "        # real-time-required: a real socket timeout is the discriminator\n"
        "    ), f'took {elapsed}s'\n"
    )

    assert check.file_findings(source=source, label="tests/test_x.py") == []


def test_the_repositorys_own_tests_tree_is_clean() -> None:
    """The gate's own contract, read against the tree it governs.

    Nothing short of reading the real tree establishes this: a seeded clean
    file would pass against a matcher pointed at nothing at all. It is also
    where both positive controls run against the committed fixture.
    """
    check = _load_check()

    assert check.findings(repo_root=_REPO_ROOT) == []


def test_the_gate_runs_in_the_check_aggregate() -> None:
    """The slug is a literal member of the aggregate's own declaration.

    The justfile `check:` array is the aggregate's ONE declaration — the shared
    completeness gate certifies that set and `just-check.sh` executes exactly
    what parsing it yields — so a gate absent from it never runs, whatever else
    is wired. A hardcoded second list diverged by ten slugs for eight weeks
    here, which is why the declaration itself is what gets read.
    """
    justfile = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")
    declaration = justfile.split("targets=(", 1)[1].split("\n)", 1)[0]

    assert "check-tests-no-real-time" in declaration.split()
    assert "\ncheck-tests-no-real-time:\n" in justfile
