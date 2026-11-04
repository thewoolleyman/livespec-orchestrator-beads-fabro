"""Mapping a carrier id to the repository whose tenant minted it.

Every case here is about an answer that is WRONG RATHER THAN ABSENT, which is
why the module exists at the unit tier: a carrier attributed to the wrong
repository produces a perfectly well-formed obligation, the resume waits on it,
and the read comes back `unsatisfied` from a tenant that has never held the item
— a confident negative taken on the wrong population. An unattributable carrier,
by contrast, announces itself.

The fixtures are filesystem-only. The tenancy answers two questions — does this
name resolve to a clone on this host, and what prefix does that clone's own
configuration create — and both are read off disk, so a tenant connection is
never opened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._plan_carrier_tenancy import (
    carrier_tenancy,
    repository_for_carrier,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_OWN = "repo"
_OWN_PREFIX = "bd-ib"


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix=_OWN_PREFIX,
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        repo_root=repo,
        fake=True,
    )


def _connection(*, prefix: str) -> dict[str, object]:
    return {"livespec-orchestrator-beads-fabro": {"connection": {"prefix": prefix}}}


def _project(
    *, tmp_path: Path, siblings: dict[str, str | None], uncloned: tuple[str, ...] = ()
) -> Path:
    """This checkout, beside each named sibling.

    A sibling mapped to a prefix gets a clone carrying that connection; one
    mapped to `None` gets a clone carrying no configuration at all, which is the
    shape of a repository the result reader resolves to a directory and cannot
    read a tenant from. An `uncloned` name is CONFIGURED and has no directory —
    the shape of a sibling nobody has cloned on this host — which is the other,
    earlier way a configured name answers nothing.
    """
    repo = tmp_path / _OWN
    repo.mkdir()
    configured: dict[str, object] = dict(_connection(prefix=_OWN_PREFIX))
    configured["cross_repo_targets"] = {
        name: {"github_url": f"https://github.com/thewoolleyman/{name}"}
        for name in (*siblings, *uncloned)
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(configured), encoding="utf-8")
    for name, prefix in siblings.items():
        clone = tmp_path / name
        clone.mkdir()
        if prefix is not None:
            _ = (clone / ".livespec.jsonc").write_text(
                json.dumps(_connection(prefix=prefix)), encoding="utf-8"
            )
    return repo


def test_each_carrier_resolves_to_the_tenant_whose_prefix_minted_it(tmp_path: Path) -> None:
    """The project's own carriers and each sibling's are told apart by prefix."""
    repo = _project(tmp_path=tmp_path, siblings={"codex": "cx", "console": "cs"})
    tenancy = carrier_tenancy(config=_config(repo=repo))

    resolved = {
        carrier: repository_for_carrier(tenancy=tenancy, carrier_id=carrier)
        for carrier in ("bd-ib-evrynu", "cx-extptf", "cs-wzvd2s")
    }

    assert [one is not None and one.name for one in resolved.values()] == [_OWN, "codex", "console"]


def test_the_longest_prefix_claims_a_carrier_whose_id_matches_two(tmp_path: Path) -> None:
    """A prefix that is a prefix of another must not claim the other's ids.

    The MEASURED shape rather than an invented one: this family's siblings are
    named `livespec-driver-codex`, `livespec-driver-pi` and the like, so one
    tenant's prefix being an initial segment of another's is the normal case. A
    first-match scan over the manifest's own order would hand every
    `livespec-driver-codex-*` carrier to whichever of the two was listed first.
    """
    repo = _project(tmp_path=tmp_path, siblings={"short": "li", "long": "livespec"})
    tenancy = carrier_tenancy(config=_config(repo=repo))

    claimed = repository_for_carrier(tenancy=tenancy, carrier_id="livespec-4dhfyu")

    assert claimed is not None
    assert claimed.name == "long"


def test_a_prefix_that_is_not_followed_by_the_separator_does_not_match(tmp_path: Path) -> None:
    """`li` does not claim `livespec-...`: only `li-...` opens with `li-`.

    The separator is what makes the prefix a prefix of an ID rather than of a
    STRING, and it is the arm that keeps the longest-prefix rule from being the
    only thing standing between two overlapping tenants.
    """
    repo = _project(tmp_path=tmp_path, siblings={"short": "li"})
    tenancy = carrier_tenancy(config=_config(repo=repo))

    assert repository_for_carrier(tenancy=tenancy, carrier_id="livespec-4dhfyu") is None


@pytest.mark.parametrize(
    ("label", "siblings", "uncloned"),
    [
        ("a sibling whose clone declares no tenant connection", {"stranger": None}, ()),
        ("a sibling configured but never cloned on this host", {}, ("absent",)),
        ("no sibling configured at all", {}, ()),
    ],
)
def test_a_carrier_no_configured_tenant_could_have_minted_names_no_repository(
    tmp_path: Path, label: str, siblings: dict[str, str | None], uncloned: tuple[str, ...]
) -> None:
    """An unplaceable carrier is reported as unplaceable, never guessed at.

    A repository the result reader cannot read a tenant from is absent from the
    tenancy rather than present with an empty prefix: an empty prefix matches
    every id that opens with `-`, and more to the point it would make this
    repository answer for a carrier it has no record of.

    The two negative shapes are kept side by side because they fail at DIFFERENT
    steps — one at the resolution, one at the connection — and a tenancy that
    had stopped resolving at all would satisfy the second alone.
    """
    repo = _project(tmp_path=tmp_path, siblings=siblings, uncloned=uncloned)
    tenancy = carrier_tenancy(config=_config(repo=repo))

    assert repository_for_carrier(tenancy=tenancy, carrier_id="ob-5qlusq") is None, label


def test_a_sibling_declaring_this_projects_own_prefix_does_not_claim_its_ids(
    tmp_path: Path,
) -> None:
    """The first name claiming a prefix keeps it, and the project is named first.

    Two tenants declaring one create-prefix is a misconfiguration rather than a
    shape to support, and the question is which way it fails: a carrier id this
    project could have minted must be read from the tenant that mints them, not
    from whichever sibling shares the spelling.
    """
    repo = _project(tmp_path=tmp_path, siblings={"twin": _OWN_PREFIX})
    tenancy = carrier_tenancy(config=_config(repo=repo))

    claimed = repository_for_carrier(tenancy=tenancy, carrier_id="bd-ib-evrynu")

    assert claimed is not None
    assert claimed.name == _OWN


def test_an_unconfigured_repository_root_resolves_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A config carrying no `repo_root` resolves this process's own directory.

    The same fallback every other plan-level reader of a project root takes. It
    is exercised because the alternative — raising — would turn a resolvable
    carrier into an unhandled error on the resume path.
    """
    repo = _project(tmp_path=tmp_path, siblings={})
    monkeypatch.chdir(repo)
    rootless = StoreConfig(
        tenant="livespec-impl-beads",
        prefix=_OWN_PREFIX,
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )

    tenancy = carrier_tenancy(config=rootless)

    assert tenancy.project_root == repo
    claimed = repository_for_carrier(tenancy=tenancy, carrier_id="bd-ib-evrynu")
    assert claimed is not None
    assert claimed.name == _OWN
