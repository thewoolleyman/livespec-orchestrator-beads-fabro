"""Contracts for the production orchestrator image Dockerfile."""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DOCKERFILE = _REPO_ROOT / "orchestrator-image" / "Dockerfile"
_BUILD_AND_VERIFY = _REPO_ROOT / "orchestrator-image" / "build-and-verify.sh"
_DOCKERIGNORE = _REPO_ROOT / "orchestrator-image" / ".dockerignore"


def _tier_one_embedded_bd_body(*, script: str) -> str:
    marker = 'log "T1.d.ii bd embedded-mode round-trip (init + create + list)"'
    section = script.split(marker, maxsplit=1)[1]
    before_completion = section.split('log "tier-1 verification complete"', maxsplit=1)[0]
    heredoc_start = 'docker exec "$CONTAINER" bash -lc "$(cat <<\'TIER1_BD\'\n'
    heredoc_end = '\nTIER1_BD\n)" 2>&1'

    assert before_completion.count(heredoc_start) == 1
    assert before_completion.count(heredoc_end) == 1
    return before_completion.split(heredoc_start, maxsplit=1)[1].split(heredoc_end, maxsplit=1)[0]


def _instructions(*, dockerfile: str) -> str:
    """Return the Dockerfile with whole-line `#` comments dropped.

    The rationale comments deliberately QUOTE the rotting install routes they
    replaced, so a regression assertion has to read the instructions rather
    than the prose that documents them.
    """
    return "\n".join(line for line in dockerfile.splitlines() if not line.lstrip().startswith("#"))


def _sole_version_pin(*, dockerfile: str, variable: str) -> str:
    """Return the single fully-qualified version literal declared for `variable`."""
    pins = re.findall(rf"^ENV {variable}=(\S+) \\$", dockerfile, flags=re.MULTILINE)
    assert len(pins) == 1, pins
    assert re.fullmatch(r"\d+\.\d+\.\d+", pins[0]), pins[0]
    return pins[0]


def _sole_recorded_sha256(*, dockerfile: str, variable: str) -> str:
    """Return the single recorded sha256 literal declared for `variable`."""
    checksums = re.findall(rf"^    {variable}=([0-9a-f]{{64}})$", dockerfile, flags=re.MULTILINE)
    assert len(checksums) == 1, checksums
    return checksums[0]


def test_github_cli_install_is_version_pinned_and_sha256_verified() -> None:
    dockerfile = _DOCKERFILE.read_text(encoding="utf-8")

    # The pin itself lives ONLY in the Dockerfile: asserting the exact version
    # and checksum literals here too would mean every gh roll edits two files.
    # Assert the SHAPE — one fully-qualified version, one recorded sha256
    # beside it, and a download whose bytes are proven before it is installed,
    # in the same shape the bd and dolt installs already use.
    _sole_version_pin(dockerfile=dockerfile, variable="GH_VERSION")
    _sole_recorded_sha256(dockerfile=dockerfile, variable="GH_DEB_SHA256")

    assert (
        '"https://github.com/cli/cli/releases/download/v${GH_VERSION}'
        '/gh_${GH_VERSION}_linux_amd64.deb"' in dockerfile
    )
    assert 'echo "${GH_DEB_SHA256}  /tmp/gh.deb" | sha256sum -c -' in dockerfile
    assert "dpkg -i /tmp/gh.deb" in dockerfile
    assert 'test "$(gh --version | awk \'NR == 1 {print $3}\')" = "${GH_VERSION}"' in dockerfile

    # The exact-version apt pin this replaced rotted by construction: the
    # cli.github.com stable suite indexes only the newest gh, so the pinned
    # version vanished on the next upstream release and broke every rebuild.
    assert "cli.github.com" not in _instructions(dockerfile=dockerfile)


def test_mise_install_is_version_pinned_and_sha256_verified() -> None:
    dockerfile = _DOCKERFILE.read_text(encoding="utf-8")

    _sole_version_pin(dockerfile=dockerfile, variable="MISE_VERSION")
    _sole_recorded_sha256(dockerfile=dockerfile, variable="MISE_BINARY_SHA256")

    assert (
        '"https://github.com/jdx/mise/releases/download/v${MISE_VERSION}'
        '/mise-v${MISE_VERSION}-linux-x64"' in dockerfile
    )
    assert 'echo "${MISE_BINARY_SHA256}  /tmp/mise" | sha256sum -c -' in dockerfile
    assert "install -m 0755 /tmp/mise /usr/local/bin/mise" in dockerfile
    assert '/usr/local/bin/mise --version | grep -q "${MISE_VERSION}"' in dockerfile

    # mise previously carried no version at all, so each rebuild silently took
    # whatever the mise apt repo served — drift in the tool that pins the rest.
    assert "apt-get install -y --no-install-recommends mise" not in _instructions(
        dockerfile=dockerfile
    )


def test_uv_install_is_version_pinned_and_sha256_verified() -> None:
    dockerfile = _DOCKERFILE.read_text(encoding="utf-8")

    _sole_version_pin(dockerfile=dockerfile, variable="UV_VERSION")
    _sole_recorded_sha256(dockerfile=dockerfile, variable="UV_TARBALL_SHA256")

    assert (
        '"https://github.com/astral-sh/uv/releases/download/${UV_VERSION}'
        '/uv-x86_64-unknown-linux-gnu.tar.gz"' in dockerfile
    )
    assert 'echo "${UV_TARBALL_SHA256}  /tmp/uv.tar.gz" | sha256sum -c -' in dockerfile
    assert "install -m 0755 /tmp/uv-x86_64-unknown-linux-gnu/uv /usr/local/bin/uv" in dockerfile
    assert "/usr/local/bin/uv --version" in dockerfile

    # The installer pipe this replaced pinned the version but not the content:
    # it ran with no integrity check and logged "no checksums to verify".
    assert "astral.sh/uv" not in _instructions(dockerfile=dockerfile)


def test_dockerfile_adds_no_apt_source_of_its_own() -> None:
    dockerfile = _DOCKERFILE.read_text(encoding="utf-8")
    instructions = _instructions(dockerfile=dockerfile)

    # The three assertions above each close ONE rotted route by name, so a
    # FOURTH tool added tomorrow through a third-party apt source would pass
    # every one of them and reopen the class. The rot is a property of
    # THIRD-PARTY LATEST-ONLY APT SOURCES: the cli.github.com stable suite
    # indexed only the newest gh, so the pinned 2.96.0 vanished from the index
    # and broke every rebuild. The SANCTIONED ALTERNATIVE is the shape gh,
    # mise, uv, bd and dolt now all use — a version-pinned, SHA256-VERIFIED
    # download of a GitHub release asset, which upstream keeps forever and
    # whose bytes are proven before installation.
    #
    # So the invariant that closes the class structurally is: the Dockerfile
    # adds NO apt source of its own. The only apt traffic left is the
    # base-package block against the Ubuntu archive, which keeps every version
    # for a release and does not rot — which is why the rule here is "no
    # third-party source" and NOT "pin every apt-get install": a blanket pin
    # would flag that legitimate block and still not stop a new source.
    #
    # Read the INSTRUCTIONS, not the raw file: the rationale comments above
    # deliberately quote the removed apt routes.
    assert "sources.list.d" not in instructions
    assert "keyring" not in instructions
    assert "apt-key" not in instructions
    assert "add-apt-repository" not in instructions


def test_build_and_verify_asserts_the_container_github_cli_version() -> None:
    script = _BUILD_AND_VERIFY.read_text(encoding="utf-8")

    assert 'log "T1.0 gh version"' in script
    assert 'version="$(gh --version | awk "NR == 1 {print \\$3}")"' in script
    assert 'test "$version" = "$GH_VERSION"' in script


def test_beads_is_pinned_to_guarded_v1_2_2_layout() -> None:
    dockerfile = _DOCKERFILE.read_text(encoding="utf-8")

    assert "ENV BD_VERSION=1.2.2 \\" in dockerfile
    assert (
        "BD_TARBALL_SHA256=8140098a51d3b81d5548d1c5e6db1a2d9930e5d141efe2a4bff7d079c4d321e8 \\"
        in dockerfile
    )
    assert (
        "BD_BINARY_SHA256=54fc0e0581ce4c5487a5b242f0a4f34af1ef09cf056e164a1af63a6ec7aa1e0e"
        in dockerfile
    )
    assert "install -m 0755 /tmp/bd /usr/local/bin/bd-real" in dockerfile
    assert "COPY bd-guard /tmp/bd-guard" in dockerfile
    assert "install -m 0755 /tmp/bd-guard/bd-guard.sh /usr/local/bin/bd" in dockerfile
    assert (
        "install -m 0755 /tmp/bd-guard/bd-guard-emit.py /usr/local/bin/bd-guard-emit.py"
        in dockerfile
    )
    assert "bd-guard-wrapper-sentinel" in dockerfile
    assert "ENV LIVESPEC_BD_PATH=/usr/local/bin/bd" in dockerfile


def test_orchestrator_image_context_allows_and_cleans_bd_guard_payload() -> None:
    dockerignore = _DOCKERIGNORE.read_text(encoding="utf-8")
    script = _BUILD_AND_VERIFY.read_text(encoding="utf-8")

    assert "!bd-guard" in dockerignore
    assert "!bd-guard/**" in dockerignore
    assert 'rm -rf "$HERE/bd-guard" || true' in script
    assert 'cp -R "$HERE/../bd-guard" "$HERE/bd-guard"' in script
    assert 'find "$HERE/bd-guard" -type d -name __pycache__ -prune -exec rm -rf {} +' in script


def test_tier_one_verifies_guarded_beads_contract_without_host_mutation() -> None:
    script = _BUILD_AND_VERIFY.read_text(encoding="utf-8")

    assert 'log "T1.1 guarded bd layout"' in script
    assert 'test "$LIVESPEC_BD_PATH" = /usr/local/bin/bd' in script
    assert "grep -q" in script
    assert "bd-guard-wrapper-sentinel" in script
    assert "/usr/local/bin/bd" in script
    assert 'echo "$BD_BINARY_SHA256  /usr/local/bin/bd-real" | sha256sum -c -' in script
    assert 'grep -q "bd version $BD_VERSION" <<<"$(/usr/local/bin/bd-real version)"' in script
    assert 'grep -q "bd version $BD_VERSION" <<<"$(/usr/local/bin/bd version)"' in script


def test_tier_one_embedded_bd_proves_enforcement_and_normalization() -> None:
    script = _BUILD_AND_VERIFY.read_text(encoding="utf-8")
    body = _tier_one_embedded_bd_body(script=script)

    expected_steps = (
        "BD=/usr/local/bin/bd",
        'test "$BD" = "$LIVESPEC_BD_PATH"',
        "export LIVESPEC_BD_GUARD_OTLP=off",
        'BD_NON_INTERACTIVE=1 "$BD" init --prefix ephemeral --skip-agents --skip-hooks '
        "--setup-exclude --role maintainer --quiet",
        '"$BD" config set status.custom "backlog,pending-approval,ready,active,acceptance"',
        "ITEM_ID=ephemeral-tier1",
        '"$BD" create --id "$ITEM_ID" --type task --title "ephemeral round-trip probe" '
        '--description "tier-1 verification" --json >create.json',
        '"$BD" show "$ITEM_ID" --json >after-create.json',
        'jq -e --arg id "$ITEM_ID" \'(if type == "array" then .[0] else . end) '
        '| .id == $id and .status == "backlog"\' after-create.json >/dev/null',
        "set +e",
        'LIVESPEC_BD_GUARD_MODE=fail "$BD" update "$ITEM_ID" --status in_progress '
        "--json >blocked.json 2>blocked.err",
        "blocked_rc=$?",
        'test "$blocked_rc" -eq 3',
        "test ! -s blocked.json",
        'grep -qF "bd update --status in_progress\' is non-lifecycle; use --status active" '
        "blocked.err",
        '"$BD" show "$ITEM_ID" --json >after-block.json',
        'jq -e --arg id "$ITEM_ID" \'(if type == "array" then .[0] else . end) '
        '| .id == $id and .status == "backlog"\' after-block.json >/dev/null',
    )

    missing_steps = tuple(step for step in expected_steps if step not in body)
    assert not missing_steps, missing_steps
    positions = tuple(body.index(step) for step in expected_steps)
    assert positions == tuple(sorted(positions))
    assert "|| true" not in body
    assert "\n  bd " not in body
