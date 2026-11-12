"""Imported-code release-component refusals for the plan proof leg."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    BuildIdentity,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_leg import (
    _imported_component_rejection,
)
from livespec_orchestrator_beads_fabro.commands._plan_release_repository import (
    ReleaseComponent,
    ReleaseReading,
    ReleaseTags,
)

_COMPONENT = ReleaseComponent(
    name="shared-credentials",
    tag_prefix="shared-v",
    paths=("tools/shared_credentials/",),
)
_READING = ReleaseTags(
    repository="example/governed",
    tags=frozenset({"shared-v1.0.0"}),
    components=(_COMPONENT,),
)


@dataclass(frozen=True, kw_only=True)
class _Reader:
    """The proof leg's two-method seam, with a controlled tree result."""

    difference: str | None = None

    def reading(self, *, body: str) -> ReleaseReading:
        del body
        return _READING

    def component_tree_difference(
        self, *, commit: str, tag: str, component: ReleaseComponent
    ) -> str | None:
        assert (commit, tag, component) == ("c0ffee1", "shared-v1.0.0", _COMPONENT)
        return self.difference


@pytest.mark.parametrize(
    ("imported", "named", "build", "difference", "expected"),
    [
        (
            ("missing",),
            "shared-v1.0.0",
            BuildIdentity(release_tag=None, installed_build=None, commit="c0ffee1"),
            None,
            "names undeclared imported component missing",
        ),
        (
            ("shared-credentials",),
            "other-v1.0.0",
            BuildIdentity(release_tag=None, installed_build=None, commit="c0ffee1"),
            None,
            "names no release tag owned by imported component shared-credentials",
        ),
        (
            ("shared-credentials",),
            "shared-v1.0.0",
            BuildIdentity(release_tag=None, installed_build=None, commit=None),
            None,
            "names no default-branch commit for imported component shared-credentials",
        ),
        (
            ("shared-credentials",),
            "shared-v1.0.0",
            BuildIdentity(release_tag=None, installed_build=None, commit="c0ffee1"),
            "tools/shared_credentials/only-on-commit.py",
            "imported component shared-credentials differs at tools/shared_credentials/only-on-commit.py",
        ),
    ],
)
def test_imported_component_refusals_name_the_component_and_first_difference(
    *,
    imported: tuple[str, ...],
    named: str,
    build: BuildIdentity,
    difference: str | None,
    expected: str,
) -> None:
    """All invalid imported-code claims refuse before they can become evidence."""
    assert (
        _imported_component_rejection(
            imported=imported,
            components=(_COMPONENT,),
            named=named,
            reading=_READING,
            build=build,
            reader=_Reader(difference=difference),
        )
        == expected
    )
