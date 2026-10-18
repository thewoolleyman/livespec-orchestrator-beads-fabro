"""The adopter dispatch setup document, graded as the adopter-facing surface it is.

Each test here grades ONE assertion of `bd-ib-knnhbn`'s Definition of Done against
`ADOPTER-DISPATCH-SETUP.md`, the document `SPECIFICATION/contracts.md` means by
"the adopter docs" — the surface that file obliges to carry the full dispatch
credential set up front and to surface the withheld `workflows` grant, rather
than letting an adopter discover either one failure at a time.

Two things have to hold and only one of them is about contents: the document must
SAY the thing, and README.md must ROUTE an adopter to it. An adopter reads the
README, never this repo's `.ai/` agent-orientation tree, so a setup document the
README does not link is unreachable by its own audience. That is the
orphaned-guidance failure the `.ai/` convention's resolve check structurally
cannot catch either — it verifies that references RESOLVE, so a repo making no
reference to a file passes with that file unreachable. Hence the routing
assertion in the first test rather than a note saying someone should check.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RELPATH = "ADOPTER-DISPATCH-SETUP.md"
_README = (_REPO_ROOT / "README.md").read_text()
_DOC_PATH = _REPO_ROOT / _RELPATH


def _doc() -> str:
    """Read the document, failing as a missing-file assertion rather than OSError."""
    assert _DOC_PATH.is_file(), f"{_RELPATH} does not exist"
    return _DOC_PATH.read_text()


def test_document_states_the_per_tenant_fabro_server_recipe() -> None:
    doc = _doc()

    # Routed from README.md: nothing proves a reference was MADE, so the
    # reachability of this file by its own audience is asserted here or nowhere.
    assert _RELPATH in _README

    # The structural fact the whole recipe follows from — one server instance
    # holds exactly ONE App integration. Without it the recipe reads as
    # optional fleet ceremony rather than as the only thing that can work.
    assert "exactly ONE" in doc
    assert "GitHub App integration" in doc

    # The four recipe elements the Definition of Done enumerates, each asserted
    # on the token an adopter actually types rather than on prose about it.
    #
    # 1. The settings strategy, and the adopter's OWN app_id. The `app_id` key
    #    is asserted together with "your own" so a document naming the fleet's
    #    id as the value cannot pass.
    assert 'strategy = "app"' in doc
    assert "app_id" in doc
    assert "your own" in doc
    # The key material MUST NOT go here, which is the half of the settings rule
    # an adopter gets wrong; asserted so the warning cannot be dropped.
    assert "never key material" in doc

    # 2. The App PEM in the server PROCESS ENVIRONMENT — env only.
    assert "GITHUB_APP_PRIVATE_KEY" in doc
    assert "server process environment" in doc
    assert "never a settings key" in doc

    # 3. Its own port, with dev-token auth. Both halves of the dev-token
    #    requirement are asserted, because the server refuses to start on
    #    either one alone and says nothing about the other.
    assert "[server.listen]" in doc
    assert 'methods = ["dev-token"]' in doc
    assert "FABRO_DEV_TOKEN" in doc
    assert "SESSION_SECRET" in doc
    # The server does not generate the dev token and refuses a malformed one,
    # which is the start-up refusal that is silent until the format is right.
    assert "does not generate" in doc
    assert "fabro_dev_" in doc
    assert "64 lowercase hex" in doc

    # 4. The named environment file and the id it answers to. What that file
    #    IS depends on the engine, and the document has to say which: on the
    #    pinned 0.254 engine `workflow.toml` declares the environment inline
    #    and the host-local file is an optional IMAGE OVERRIDE, so a document
    #    calling it a hard prerequisite sends an adopter after a file this
    #    repository does not ship. The id is asserted beside the path so the
    #    step cannot survive while the reason for it is lost.
    assert "environments/livespec-ci.toml" in doc
    assert 'id = "livespec-ci"' in doc
    assert "image override" in doc

    #    And the one constraint whose violation is silent: the Dispatcher
    #    appends the `[env]` table at dispatch time and TOML forbids declaring
    #    a table twice, so a host-local file carrying its own `[env]` block
    #    collides and takes down every dispatch that reads it. Asserted
    #    because an adopter told to copy a working file verbatim reproduces
    #    exactly that block.
    assert "`[env]` table" in doc


def test_document_states_that_a_target_local_workflow_is_resolved_automatically() -> None:
    doc = _doc()

    # The path an adopter commits, and the claim that committing it is enough.
    assert ".fabro/workflows/implement-work-item/workflow.toml" in doc
    assert "resolved automatically" in doc

    # The point of the assertion: no hand-carried flag. Asserted on the
    # obligation ("no `--workflow` flag") AND on the escape-hatch framing, so a
    # document that merely mentions the flag among the options cannot pass as
    # one that tells an adopter not to carry it.
    assert "no `--workflow` flag" in doc
    assert "escape hatch" in doc

    # Why the target-local file wins, which is the fact that makes the
    # automatic resolution useful rather than incidental: the workflow config
    # carries the sandbox image pin, so a differing toolchain governs its own
    # execution substrate instead of inheriting one that cannot build it.
    assert "sandbox image pin" in doc


def test_document_states_the_workflows_grant_is_withheld_and_names_the_host_route() -> None:
    doc = _doc()

    # The grant, and its posture. "by design" is asserted separately from
    # "withheld" because a document calling it withheld without saying it is
    # deliberate reads as a gap an adopter should close by granting it — the
    # exact misreading `contracts.md` forbids.
    assert "`workflows` read-write" in doc
    assert "withheld" in doc
    assert "by design" in doc

    # The spec's own framing: REJECTED rather than deferred, so no adopter
    # treats it as a limitation awaiting a future grant.
    assert "not deferred" in doc

    # Why, in the terms that make it non-negotiable rather than cautious: the
    # gates are defined in the files the grant would make writable, so the
    # agent could disable its own examiner in the same pull request.
    assert "disable its own examiner" in doc
    # And the reason a narrower grant is not the answer.
    assert "all-or-nothing" in doc

    # The route the Definition of Done requires the document to NAME, and the
    # framing that keeps it a routing decision rather than a privilege one.
    assert "attended host session" in doc
    assert "ROUTING, not privilege" in doc

    # The resolution must never be surfaced as manual work: `constraints.md`
    # rules that requiring a hand-edit is NOT an acceptable resolution, so a
    # document offering one would contradict the constraint it is explaining.
    assert "never manual work" in doc

    # The asymmetry, so an adopter cannot infer the sandbox credential's
    # posture from a fan-out credential that legitimately holds the grant.
    assert "fan-out credential" in doc
