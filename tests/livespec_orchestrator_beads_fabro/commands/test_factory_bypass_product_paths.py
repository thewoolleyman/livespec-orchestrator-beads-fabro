"""Hermetic tests for the factory-bypass audit's per-repository product-path classifier.

The classifier answers "is this changed path product `.py`?" from the AUDITED
repository's own `[tool.livespec_dev_tooling]` declaration rather than from one
hardcoded orchestrator-only tuple. The cases below are anchored on the real
declared layouts of three fleet repositories, because the defect this module
retires (bd-ib-jtr22v) was precisely that a classifier which could only see
this repo's layout reported "no bypasses" for every other one.

The module is imported through `importlib` behind a file-existence assertion so
the red half of the ritual fails on a genuine assertion rather than on an
unimportable module.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._factory_bypass_product_paths"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_factory_bypass_product_paths.py"
)

# The three fleet layouts the audit must be able to tell apart, verbatim from
# each repository's own declaration.
_ORCHESTRATOR_PYPROJECT = """
[project]
name = "x"

[tool.livespec_dev_tooling]
source_trees = [".claude-plugin/scripts/livespec_orchestrator_beads_fabro"]
io_trees = [".claude-plugin/scripts/livespec_orchestrator_beads_fabro/io"]
source_tree_prefixes = [
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/",
    ".claude-plugin/scripts/bin/",
    # A comment inside the array must not become a value.
    "dev-tooling/checks/",
]

[[tool.livespec_dev_tooling.mirror_pairings]]
source = "x"
"""

_DEV_TOOLING_PYPROJECT = """
[tool.livespec_dev_tooling]
source_trees = ["livespec_dev_tooling"]
source_tree_prefixes = ["livespec_dev_tooling/"]
"""

_CORE_PYPROJECT = """
[tool.livespec_dev_tooling]
source_trees = [".claude-plugin/scripts/livespec"]
source_tree_prefixes = [
    ".claude-plugin/scripts/livespec/",
    ".claude-plugin/scripts/bin/",
    "dev-tooling/",
]
"""


def _paths_module() -> Any:
    """Import the product-path classifier, proving the file exists first."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


# --------------------------------------------------------------------------
# derive_product_prefixes — the per-repository union
# --------------------------------------------------------------------------


def test_derive_unions_source_trees_and_prefixes_in_first_seen_order() -> None:
    module = _paths_module()
    assert module.derive_product_prefixes(pyproject_text=_ORCHESTRATOR_PYPROJECT) == (
        ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/",
        ".claude-plugin/scripts/bin/",
        "dev-tooling/checks/",
    )


def test_derive_reads_a_flat_layout_library() -> None:
    """`livespec-dev-tooling` roots at a bare package dir, not under .claude-plugin."""
    module = _paths_module()
    assert module.derive_product_prefixes(pyproject_text=_DEV_TOOLING_PYPROJECT) == (
        "livespec_dev_tooling/",
    )


def test_derive_reads_core_layout() -> None:
    module = _paths_module()
    assert module.derive_product_prefixes(pyproject_text=_CORE_PYPROJECT) == (
        ".claude-plugin/scripts/livespec/",
        ".claude-plugin/scripts/bin/",
        "dev-tooling/",
    )


def test_derive_ignores_keys_outside_the_declaration_table() -> None:
    """A `source_trees` key in another table is another tool's, not ours."""
    module = _paths_module()
    text = '[tool.other]\nsource_trees = ["nope"]\n\n[tool.livespec_dev_tooling]\nx = 1\n'
    assert module.derive_product_prefixes(pyproject_text=text) == ()


def test_derive_returns_empty_when_the_table_is_absent() -> None:
    module = _paths_module()
    assert module.derive_product_prefixes(pyproject_text='[project]\nname = "x"\n') == ()


# --------------------------------------------------------------------------
# product_policy — resolution, and the empty-set fail-open it refuses to have
# --------------------------------------------------------------------------


def test_policy_reports_a_declared_layout_as_declared() -> None:
    module = _paths_module()
    policy = module.product_policy(pyproject_text=_DEV_TOOLING_PYPROJECT)
    assert policy.origin == "declared"
    assert policy.prefixes == ("livespec_dev_tooling/",)


def test_policy_falls_back_rather_than_returning_an_empty_prefix_set() -> None:
    """An empty set would make `startswith` False for every path — a silent pass."""
    module = _paths_module()
    policy = module.product_policy(pyproject_text='[project]\nname = "x"\n')
    assert policy.origin == "fleet-fallback"
    assert policy.prefixes == module.FLEET_FALLBACK_PRODUCT_PREFIXES
    assert policy.prefixes != ()


def test_policy_falls_back_when_the_declaration_could_not_be_read() -> None:
    module = _paths_module()
    policy = module.product_policy(pyproject_text=None)
    assert policy.origin == "fleet-fallback"
    assert policy.prefixes == module.FLEET_FALLBACK_PRODUCT_PREFIXES


def test_policy_honors_an_operator_override_and_normalises_slashes() -> None:
    module = _paths_module()
    policy = module.product_policy(pyproject_text=_CORE_PYPROJECT, overrides=("src", "lib/"))
    assert policy.origin == "operator-override"
    assert policy.prefixes == ("src/", "lib/")


# --------------------------------------------------------------------------
# is_product_py — classification under a resolved policy
# --------------------------------------------------------------------------


def test_dev_tooling_product_path_classifies_under_its_own_policy_only() -> None:
    """The fleet-blindness regression, stated as one assertion pair."""
    module = _paths_module()
    path = "livespec_dev_tooling/checks/red_green_replay.py"
    own = module.product_policy(pyproject_text=_DEV_TOOLING_PYPROJECT)
    orchestrator = module.product_policy(pyproject_text=_ORCHESTRATOR_PYPROJECT)
    assert module.is_product_py(path=path, policy=own) is True
    assert module.is_product_py(path=path, policy=orchestrator) is False


def test_non_python_test_vendored_and_pycache_paths_are_never_product() -> None:
    module = _paths_module()
    policy = module.product_policy(pyproject_text=_ORCHESTRATOR_PYPROJECT)
    for path in (
        "README.md",
        ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/foo.txt",
        "tests/livespec_orchestrator_beads_fabro/commands/test_foo.py",
        ".claude-plugin/scripts/_vendor/structlog/foo.py",
        ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/__pycache__/foo.py",
        "plan/force-factory/findings.py",
    ):
        assert module.is_product_py(path=path, policy=policy) is False


def test_product_path_under_a_declared_prefix_classifies() -> None:
    module = _paths_module()
    policy = module.product_policy(pyproject_text=_ORCHESTRATOR_PYPROJECT)
    assert (
        module.is_product_py(
            path=".claude-plugin/scripts/bin/factory_bypass_audit.py", policy=policy
        )
        is True
    )
