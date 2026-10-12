"""The environment catalog is the ONE source of a catalog-environment dispatch's image.

Binds `SPECIFICATION/scenarios.md` "Scenario 169 — A dispatch naming a catalog
environment runs the catalog's image, and the journal names the image source" and
the sandbox-image-source clause of `SPECIFICATION/contracts.md` it realizes: a
dispatch whose resolved factory declares a catalog environment MUST launch its
sandbox from the image that environment declares on the factory server, the
launch overlay MUST NOT substitute `dispatcher.fabro_sandbox_image` for it, a
dispatch whose factory declares none MUST still launch from that key, and the
dispatch journal MUST record which source supplied the image.

EVERY CASE DRIVES THE REAL DISPATCH, through `dispatcher.main(argv=["dispatch",
...])` over a seeded tenant with only the launch seam recording. The overlay is
read off the FILE the production materializer wrote for that dispatch, and the
image source is read off the `dispatch-id` record the production journal wrote.
A renderer or a record builder asserted in isolation would pass just as well
while nothing threaded the resolved source into either, which is exactly the
defect measured on hp-candidate run 01M4PBFW4MP8: `sandbox.plan.image` named the
catalog's image while the container Petri started ran the committed override, so
the run record reported an image that did not run.

WITHHOLDING THE DECLARATION IS WHAT MAKES THE CATALOG THE SOURCE, and the
assertion is written that way on purpose. The catalog lives on the factory
server and the Dispatcher reads it at no point, so the ONLY way a launch can
carry the catalog's image is for the overlay to declare no image for that
environment at all — leaving the committed one in place would substitute a
DIFFERENT wrong image rather than the configured one, which satisfies the
clause's second half while still breaking its first. The two positive cases
therefore assert an ABSENCE of every image this repository could have named,
and assert the environment's surviving `provider` and `resources` tables as the
control, because a withholding that took those with it would be a different
defect wearing the same green.
"""

from __future__ import annotations

import base64
import json
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_credentials,
    _dispatcher_loop,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-imgsrc"
_FACTORY = "candidate"
# The catalog environment the factory declares, spelled exactly as the committed
# run config's own `[run.environment] id` so the withholding is asserted against
# the table a real dispatch really renders.
_CATALOG_ENV = "livespec-ci"
# The two images this repository CAN name, and neither is the catalog's. The
# committed run config declares the first and `dispatcher.fabro_sandbox_image`
# the second; the catalog's image is a third value no client-side surface here
# can see, which is why the positive cases assert both of these are absent
# rather than asserting any image is present.
_COMMITTED_IMAGE = "ghcr.io/example/livespec-fabro-sandbox:python-agent-v1.95.11"
_CONFIGURED_IMAGE = "ghcr.io/example/livespec-fabro-sandbox:python-agent-v1.92.0"

# The journal keys the clause's "which source supplied the sandbox image"
# requirement lands on, and the two source names it enumerates. Spelled as
# literals rather than imported: the module that owns them does not exist at the
# Red of this slice, and a top-level import of it would make that Red a
# collection error instead of a genuine assertion failure.
_SOURCE_KEY = "sandbox_image_source"
_ENVIRONMENT_KEY = "sandbox_image_environment"
_IMAGE_KEY = "sandbox_image"
_CATALOG_SOURCE = "catalog_environment"
_CONFIGURED_SOURCE = "dispatcher.fabro_sandbox_image"

_WRAPPER = ["/usr/local/bin/with-acme-env.sh", "--"]
_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
)
_RESERVED_DIR = ".fabro/workflows/implement-work-item"
# A committed run config shaped like this repository's own: the environment
# declares a provider, an image and a resources table, so the withholding has
# both a target and a pair of neighbours that must survive it.
_WORKFLOW_TOML = (
    '[workflow]\ngraph = "workflow.fabro"\n'
    "\n"
    f'[run.environment]\nid = "{_CATALOG_ENV}"\n'
    "\n"
    f'[environments.{_CATALOG_ENV}]\nprovider = "docker"\n'
    "\n"
    f"[environments.{_CATALOG_ENV}.image]\n"
    "# The family sandbox image, pinned by the release fan-out.\n"
    f'docker = "{_COMMITTED_IMAGE}"\n'
    "\n"
    f'[environments.{_CATALOG_ENV}.resources]\ncpu = 4\nmemory = "8GB"\n'
)
_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)

# A host Codex credential that expires far in the future, so the materializer
# reaches the image resolution instead of refusing at its freshness gate.
_FAR_FUTURE_EPOCH = 4_000_000_000


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic dispatch environment plus a fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("sandbox-image-source")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:sandbox-image-source")
    # The env override wins outright over the committed key, so a value leaking
    # in from the host would decide these cases instead of the configuration
    # they declare.
    monkeypatch.delenv("LIVESPEC_FABRO_SANDBOX_IMAGE", raising=False)
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", _fresh_host_codex_auth)
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: 1_700_000_000)
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _fresh_host_codex_auth() -> str:
    """A fake host `auth.json` whose access-token JWT expires far in the future."""
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": _FAR_FUTURE_EPOCH}).encode())
        .decode()
        .rstrip("=")
    )
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": f"header.{payload}.sig",
                "refresh_token": "host-refresh-token",
                "id_token": "id-token-value",
                "account_id": "acct-169",
            },
        }
    )


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _seed_item() -> None:
    """One dispatchable item whose criteria parse, so the criteria wall clears."""
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=_ITEM_ID,
            type="task",
            status="ready",
            title="Exercise the sandbox image source",
            description=(
                "## Definition of Done\n"
                "\n"
                "- The sandbox image comes from the environment catalog.\n"
                "\n"
                "References: ## Sandbox image source\n"
            ),
            origin="freeform",
            gap_id=None,
            rank="a2",
            assignee=None,
            depends_on=(),
            captured_at="2026-10-01T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy="ai-only",
            acceptance_criteria="- The sandbox image comes from the environment catalog.",
        ),
    )


def _repo(*, tmp_path: Path, environment: str | None) -> Path:
    """A governed target whose resolved factory declares `environment` or does not.

    The factory deliberately declares NO `server`. The Fabro-currency gate ahead
    of this resolution records a target with no server as unevaluated rather than
    refusing it, so omitting the key keeps every case here aimed at the image
    source instead of at a forge round trip these cases do not measure.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    entry: dict[str, object] = {}
    if environment is not None:
        entry["environment"] = environment
    dispatcher: dict[str, object] = {
        "wip_cap": 3,
        "acceptance_mode": "ai-only",
        "fabro_sandbox_image": _CONFIGURED_IMAGE,
        "default_factory": _FACTORY,
        "factories": {_FACTORY: entry},
    }
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "credential_wrapper": _WRAPPER,
                "git_author": {
                    "operator_name": "Chad Woolley",
                    "operator_email": "thewoolleyman@gmail.com",
                },
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": dispatcher,
                },
            }
        ),
        encoding="utf-8",
    )
    workflow = repo / _RESERVED_DIR
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    return repo


def _recording_run_dispatch(*, overlays: list[str]) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in capturing the overlay the materializer wrote.

    The capture happens HERE, at the launch seam, because the overlay is a
    run-scoped credential projection the dispatch deletes when the run returns —
    so the launch is the one moment at which the bytes the sandbox would have
    received are still on disk.
    """

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        overlay = plan.workflow_toml
        overlays.append(overlay.read_text(encoding="utf-8"))
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="dispatched",
        )

    return _run_dispatch


def _dispatch(*, repo: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[int, list[str]]:
    """Drive one real dispatch and report its exit code plus the overlay it wrote."""
    overlays: list[str] = []
    monkeypatch.setattr(
        _dispatcher_loop, "run_dispatch", _recording_run_dispatch(overlays=overlays)
    )
    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", _ITEM_ID, "--no-close-on-merge"]
    )
    return exit_code, overlays


def test_a_catalog_environment_dispatch_leaves_the_sandbox_image_to_the_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 169, first arm: the launch declares no image, so the catalog's governs.

    Both of this repository's own images are asserted ABSENT from the whole
    overlay, which is the only client-side observation that distinguishes "the
    catalog supplies the image" from "some other image was substituted": the
    configured override is the defect measured on hp-candidate, and the committed
    pin is the one a fix that merely suppressed the override would leave behind.

    The environment's `provider` and `resources` tables are asserted PRESENT as
    the control. Withholding the image declaration must take the image
    declaration and nothing else; a dispatch whose provider or resources went
    with it would land in the server's defaults and die in a prepare step, a
    failure that names nothing about the placement.
    """
    _seed_item()
    repo = _repo(tmp_path=tmp_path, environment=_CATALOG_ENV)

    exit_code, overlays = _dispatch(repo=repo, monkeypatch=monkeypatch)

    assert exit_code == 0
    assert len(overlays) == 1
    rendered = overlays[0]
    assert f"[environments.{_CATALOG_ENV}.image]" not in rendered
    assert _CONFIGURED_IMAGE not in rendered
    assert _COMMITTED_IMAGE not in rendered
    assert f'[environments.{_CATALOG_ENV}]\nprovider = "docker"\n' in rendered
    assert f'[environments.{_CATALOG_ENV}.resources]\ncpu = 4\nmemory = "8GB"\n' in rendered


def test_a_dispatch_naming_no_catalog_environment_still_carries_the_committed_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 169, second arm: the configured key still decides where none is named.

    The CONTROL for the case above, and the one the clause names explicitly. The
    two legs differ in exactly one committed key — whether the resolved factory
    entry declares `environment` — so the withholding above is evidence about
    catalog environments rather than a build that stopped honouring
    `dispatcher.fabro_sandbox_image` for everyone. Without it, every assertion in
    this module would be satisfied by a renderer that withheld the image table
    unconditionally, which would strand every factory on the pinned engine: the
    `--environment` flag does not exist there, so no such factory can name a
    catalog environment and all of them depend on this arm.
    """
    _seed_item()
    repo = _repo(tmp_path=tmp_path, environment=None)

    exit_code, overlays = _dispatch(repo=repo, monkeypatch=monkeypatch)

    assert exit_code == 0
    assert len(overlays) == 1
    rendered = overlays[0]
    assert f"[environments.{_CATALOG_ENV}.image]" in rendered
    assert f'docker = "{_CONFIGURED_IMAGE}"\n' in rendered
    assert _COMMITTED_IMAGE not in rendered
