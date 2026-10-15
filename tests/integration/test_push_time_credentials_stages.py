"""Real Git HTTP proofs of all script pushes, bounded remint, and secret hygiene."""

import base64
import subprocess

import pytest

from tests.integration import test_push_time_credentials as fixtures
from tests.integration.test_push_time_credentials import (
    BRANCH,
    EXPIRED,
    FRESH,
    PushSandbox,
    executable,
    git,
)

push_sandbox = fixtures.push_sandbox


@pytest.fixture(autouse=True)
def isolate_push_mints(push_sandbox: PushSandbox) -> None:
    """The PR API double must not add gh mints to the push-attempt count.

    It answers `null` because `pr_refresh` reads the pull request's auto-merge
    request before it rebases (v145) and fails closed on an empty answer, so a
    stub printing nothing refuses the stage before any push — and the subject of
    every case here is the PUSH. `null` reports the arming absent, which is the
    state that reaches the push with no forge write in between.
    """
    executable(
        path=push_sandbox.root / "bin/gh",
        source="#!/bin/sh\nprintf 'null\\n'\nexit 0\n",
    )


def prepare_stage(*, box: PushSandbox, node: str) -> str:
    if node != "pr_refresh":
        return (
            "refs/heads/needs-human/AUTHRUN123" if node == "needs_human" else f"refs/heads/{BRANCH}"
        )
    # Seed this run's previous publication, then advance master independently.
    head = git("rev-parse", "HEAD", cwd=box.clone, env=box.env)
    git("push", str(box.origin), f"HEAD:{BRANCH}", cwd=box.clone, env=box.env)
    state = box.clone / ".git/livespec-publication"
    state.mkdir()
    (state / "livespec-publish-head").write_text(head)
    base = git("rev-parse", "master", cwd=box.origin, env=box.env)
    tree = git("rev-parse", "master^{tree}", cwd=box.origin, env=box.env)
    advanced = git("commit-tree", tree, "-p", base, "-m", "advance", cwd=box.origin, env=box.env)
    git("update-ref", "refs/heads/master", advanced, cwd=box.origin, env=box.env)
    return f"refs/heads/{BRANCH}"


@pytest.mark.parametrize("node", ["publish_draft", "pr_refresh", "needs_human"])
@pytest.mark.parametrize("refusals", [0, 1, 3])
def test_every_script_push_remints_and_retries_http_401_only_once(
    push_sandbox: PushSandbox, node: str, refusals: int
) -> None:
    box = push_sandbox
    ref = prepare_stage(box=box, node=node)
    old_head = git("rev-parse", "HEAD", cwd=box.clone, env=box.env)
    old_url = git("remote", "get-url", "origin", cwd=box.clone, env=box.env)
    box.refusals = refusals
    result = box.run(node=node)
    attempts = min(refusals + 1, 2)
    expected_auth = "Basic " + base64.b64encode(f"x-access-token:{FRESH}".encode()).decode()
    assert box.mint_count() == attempts, result.stderr
    assert box.writes == [expected_auth] * attempts, result.stderr
    success = refusals < 2
    if node == "needs_human":
        assert result.returncode == 1
        assert ("LIVESPEC_NEEDS_HUMAN_PRESERVED:" in result.stderr) == success
    else:
        assert (result.returncode == 0) == success, result.stderr
    if success:
        assert box.head(ref=ref) == git("rev-parse", "HEAD", cwd=box.clone, env=box.env)
        if node == "pr_refresh":
            assert box.head(ref=ref) != old_head
    elif node == "pr_refresh":
        assert box.head(ref=ref) == old_head
    else:
        assert not git("for-each-ref", "--format=%(refname)", ref, cwd=box.origin, env=box.env)
    assert git("remote", "get-url", "origin", cwd=box.clone, env=box.env) == old_url
    assert_secret_hygiene(box=box, result=result, expected_auth=expected_auth)


def assert_secret_hygiene(
    *, box: PushSandbox, result: subprocess.CompletedProcess[str], expected_auth: str
) -> None:
    output = result.stdout + result.stderr
    for secret in (FRESH, EXPIRED, expected_auth):
        assert secret not in output
        assert secret not in box.prepare
    assert FRESH not in (box.clone / ".git/config").read_text()
    for path in box.bundle.rglob("*"):
        if path.is_file() and path.name != "mint_app_token.py":
            assert FRESH.encode() not in path.read_bytes()


@pytest.mark.parametrize("node", ["publish_draft", "pr_refresh"])
def test_non_authentication_hook_failure_is_not_retried(
    push_sandbox: PushSandbox, node: str
) -> None:
    box = push_sandbox
    prepare_stage(box=box, node=node)
    marker = box.root / "hook-count"
    executable(
        path=box.clone / ".git/hooks/pre-push",
        source=f"#!/bin/sh\necho invoked >> '{marker}'\necho hook-refusal >&2\nexit 1\n",
    )
    result = box.run(node=node)
    assert result.returncode != 0
    assert marker.read_text().splitlines() == ["invoked"]
    assert box.mint_count() == 1
    assert box.writes == []


def test_preservation_keeps_its_hook_policy(push_sandbox: PushSandbox) -> None:
    box = push_sandbox
    marker = box.root / "hook-count"
    executable(
        path=box.clone / ".git/hooks/pre-push",
        source=f"#!/bin/sh\necho invoked >> '{marker}'\nexit 1\n",
    )
    result = box.run(node="needs_human")
    assert "LIVESPEC_NEEDS_HUMAN_PRESERVED:" in result.stderr
    assert not marker.exists()
    assert box.mint_count() == 1


def test_failed_retry_mint_stops_before_a_second_push(push_sandbox: PushSandbox) -> None:
    box = push_sandbox
    mint = box.bundle / "bin/mint_app_token.py"
    mint.write_text(
        "from pathlib import Path\n"
        f"p = Path({str(box.minted)!r})\n"
        "if p.exists(): raise SystemExit(3)\n"
        "p.write_text('mint\\n')\n"
        f"print({FRESH!r})\n"
    )
    box.refusals = 1
    result = box.run(node="publish_draft")
    assert result.returncode != 0
    assert "LIVESPEC_PUSH_AUTH_MINT" in result.stderr
    assert len(box.writes) == 1


def test_push_diagnostics_redact_credentials(push_sandbox: PushSandbox) -> None:
    box = push_sandbox
    echoer = box.root / "echo-credentials"
    encoded = base64.b64encode(f"x-access-token:{FRESH}".encode()).decode()
    executable(
        path=echoer,
        source=(
            "#!/bin/sh\n"
            'printf "%s\\n" "$LIVESPEC_PUSH_TOKEN" >&2\n'
            f"echo 'Authorization: Basic {encoded}' >&2\n"
            f"echo 'https://x-access-token:{EXPIRED}@github.com/owner/repo' >&2\n"
            "exit 1\n"
        ),
    )
    result = subprocess.run(
        [str(box.bundle / "bin/push_origin"), str(echoer)],
        cwd=box.clone,
        env=box.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert box.mint_count() == 1
    for secret in (FRESH, EXPIRED, encoded):
        assert secret not in result.stdout + result.stderr
