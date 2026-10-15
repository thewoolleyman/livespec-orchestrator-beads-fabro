"""Run shipped script nodes against authenticated Git HTTP, with a fake mint.

Git, its credential precedence, receive-pack and the remote refs are real.
Only App issuance and the PR API are doubled. The server accepts an expired
credential for reads (a public repository), but never for a publication write.
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, cast
from wsgiref.simple_server import make_server

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    refreshing_gh_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    publication_push_program_source,
)

WORKFLOW = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
BRANCH = "feat/push-time-test"
EXPIRED = "expired-installation-token"
FRESH = "fresh-installation-token"


def git(*args: str, cwd: Path, env: dict[str, str]) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True
    ).stdout.strip()


def executable(*, path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o700)


@dataclass(kw_only=True)
class PushSandbox:
    root: Path
    clone: Path
    origin: Path
    bundle: Path
    env: dict[str, str]
    minted: Path
    writes: list[str]
    prepare: str
    refusals: int = 0

    def run(self, *, node: str) -> subprocess.CompletedProcess[str]:
        graph = parse_dot_graph(text=WORKFLOW.read_text(encoding="utf-8"))
        assert not isinstance(graph, str), graph
        script = graph.nodes[node]["script"].replace("{{ inputs.default_branch }}", "master")
        script = script.replace("{{ inputs.sandbox_check_suite }}", "true")
        return subprocess.run(
            ["bash", "-c", script],
            cwd=self.clone,
            env=self.env,
            input="AUTHRUN123\n",
            capture_output=True,
            text=True,
            check=False,
        )

    def head(self, *, ref: str) -> str:
        return git("rev-parse", ref, cwd=self.origin, env=self.env)

    def mint_count(self) -> int:
        return len(self.minted.read_text().splitlines()) if self.minted.exists() else 0


@dataclass(kw_only=True)
class GitHTTPApplication:
    """A real smart-HTTP Git endpoint with controlled installation-token expiry."""

    sandbox: PushSandbox

    def __call__(
        self,
        environ: dict[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], object],
    ) -> list[bytes]:
        box = self.sandbox
        path = str(environ["PATH_INFO"])
        if "git-receive-pack" in str(environ["QUERY_STRING"]) and not environ.get(
            "HTTP_AUTHORIZATION"
        ):
            start_response("401 Unauthorized", [("WWW-Authenticate", 'Basic realm="Git"')])
            return [b""]
        if path.endswith("git-receive-pack"):
            auth = str(environ.get("HTTP_AUTHORIZATION", ""))
            box.writes.append(auth)
            expected = base64.b64encode(f"x-access-token:{FRESH}".encode()).decode()
            if auth != f"Basic {expected}" or box.refusals:
                box.refusals = max(0, box.refusals - 1)
                start_response("401 Unauthorized", [("WWW-Authenticate", 'Basic realm="Git"')])
                return [b""]
        stream = cast("BinaryIO", environ["wsgi.input"])
        payload = stream.read(int(str(environ.get("CONTENT_LENGTH") or "0")))
        result = subprocess.run(
            ["git", "http-backend"],
            input=payload,
            capture_output=True,
            check=True,
            env={
                **box.env,
                "GIT_PROJECT_ROOT": str(box.root),
                "GIT_HTTP_EXPORT_ALL": "1",
                "PATH_INFO": path,
                "QUERY_STRING": str(environ["QUERY_STRING"]),
                "REQUEST_METHOD": str(environ["REQUEST_METHOD"]),
                "CONTENT_TYPE": str(environ.get("CONTENT_TYPE", "")),
                "CONTENT_LENGTH": str(len(payload)),
                "REMOTE_USER": "fixture",
            },
        )
        headers, body = result.stdout.split(b"\r\n\r\n", 1)
        response_headers = [tuple(line.split(": ", 1)) for line in headers.decode().splitlines()]
        start_response("200 OK", response_headers)
        return [body]


@pytest.fixture
def push_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[PushSandbox]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "GITHUB_", "GH_", "COVERAGE_", "LIVESPEC_"))
    }
    env.update(
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
    )
    origin, clone = tmp_path / "origin.git", tmp_path / "clone"
    git("init", "--bare", "-b", "master", str(origin), cwd=tmp_path, env=env)
    git("config", "http.receivepack", "true", cwd=origin, env=env)
    git("clone", str(origin), str(clone), cwd=tmp_path, env=env)
    git("commit", "--allow-empty", "-m", "base", cwd=clone, env=env)
    git("push", "origin", "HEAD:master", cwd=clone, env=env)
    git("switch", "-c", "fabro/run/auth", cwd=clone, env=env)
    (clone / "work.txt").write_text("completed work\n")
    git("add", "work.txt", cwd=clone, env=env)
    git("commit", "-m", "work", cwd=clone, env=env)
    bundle, minted, prepare = provision_auth(
        root=tmp_path, clone=clone, env=env, monkeypatch=monkeypatch
    )
    box = PushSandbox(
        root=tmp_path,
        clone=clone,
        origin=origin,
        bundle=bundle,
        env=env,
        minted=minted,
        writes=[],
        prepare=prepare,
    )

    with make_server("127.0.0.1", 0, GitHTTPApplication(sandbox=box)) as server:
        port = server.server_port
        env["GITHUB_API_URL"] = f"http://127.0.0.1:{port}"
        git(
            "remote",
            "set-url",
            "origin",
            f"http://x-access-token:{EXPIRED}@127.0.0.1:{port}/origin.git",
            cwd=clone,
            env=env,
        )
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield box
        finally:
            server.shutdown()
            thread.join()


def test_publish_draft_refreshes_an_expired_origin_at_push_time(push_sandbox: PushSandbox) -> None:
    box = push_sandbox
    before = box.mint_count()
    result = box.run(node="publish_draft")
    assert result.returncode == 0, result.stderr
    assert box.head(ref=f"refs/heads/{BRANCH}") == git(
        "rev-parse", "HEAD", cwd=box.clone, env=box.env
    )
    assert box.mint_count() > before
    expected = "Basic " + base64.b64encode(f"x-access-token:{FRESH}".encode()).decode()
    assert box.writes == [expected]


def provision_auth(
    *, root: Path, clone: Path, env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, str]:
    bin_dir, bundle, plugins = root / "bin", root / "bundle", root / "plugins"
    bin_dir.mkdir()
    plugins.mkdir()
    # The base `gh` the refreshing wrapper wraps. It answers `null` because
    # `pr_refresh` reads the pull request's auto-merge request before it rebases
    # (v145) and fails closed on an empty answer, so a stub printing nothing
    # would refuse every case here before any push — the subject of this module
    # is the push-time credential, and the arming is reported absent so the
    # refresh reaches it.
    executable(path=bin_dir / "gh", source="#!/bin/sh\nprintf 'null\\n'\nexit 0\n")
    executable(path=plugins / "livespec-push-exact-head", source=publication_push_program_source())
    (plugins / "livespec-run-plugin-gate.py").write_text("# fixture gate\n")
    env.update(
        PATH=f"{bin_dir}:{env['PATH']}",
        LIVESPEC_SANDBOX_GH_REFRESH_ROOT=str(bundle),
        LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT=str(plugins),
        LIVESPEC_PUBLISH_BRANCH=BRANCH,
        LIVESPEC_GIT_AUTHOR_NAME="fixture",
        LIVESPEC_GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GITHUB_APP_ID="42",
        GITHUB_PRIVATE_KEY="fixture-key",
    )
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "fixture-key")
    monkeypatch.setenv("LIVESPEC_SANDBOX_GH_REFRESH_ROOT", str(bundle))
    prepare = refreshing_gh_prepare_steps_block()
    for script in re.findall(r"script = '''\n(.*?)\n'''", prepare, re.DOTALL):
        subprocess.run(
            ["bash", "-c", script], cwd=clone, env=env, check=True, capture_output=True, text=True
        )
    minted = root / "minted"
    executable(
        path=bundle / "bin/mint_app_token.py",
        source=(
            "#!/usr/bin/env python3\nfrom pathlib import Path\n"
            f"with Path({str(minted)!r}).open('a') as stream: stream.write('mint\\n')\n"
            f"print({FRESH!r}, end='')\n"
        ),
    )
    return bundle, minted, prepare
