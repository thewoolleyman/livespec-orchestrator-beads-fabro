#!/usr/bin/env bash
# install-ci-fabro.sh — put a pinned, checksum-verified `fabro` where CI's
# factory-graph gate (`check-fabro-graph-validity`) resolves it.
#
# WHY THE UPSTREAM RELEASE, NOT THE FACTORY'S FORK BUILD. The factory runs a fork
# build (branch factory-integration on thewoolleyman/fabro) that exists only as a
# host binary; nothing publishes it. The upstream fabro-sh/fabro v0.254.0 release
# is the fork's own base commit, publishes a static musl asset with a sha256, and
# validates graphs by identical rules (the fork carries no change to
# lib/crates/fabro-validate). Its one disagreement is that it cannot parse the
# fork-only `run.checkpoint.commit_timeout` settings key; the gate validates a
# scratch copy with exactly that key removed (dev-tooling/checks/_fork_only_settings.py),
# which gives verdicts identical to the fork build on the real graphs and on the
# broken release-0.146.0 graph.
#
# Fail-closed by construction: `set -e`, `curl --fail`, and a checksum mismatch
# all exit non-zero, and the gate itself runs with
# LIVESPEC_FABRO_GRAPH_VALIDATION=fail_when_fabro_absent, so a missing or wrong
# binary reddens CI rather than skipping the validation.
#
# Usage: install-ci-fabro.sh [target-path]   (default /usr/local/bin/fabro)
# INSTALL_CI_FABRO_WARM_DIR overrides the warm-seed directory (default
# /__w/_warm/release-assets) so tests never touch the shared runner cache.

set -euo pipefail

readonly version="v0.254.0"

# Each architecture pins its own musl asset, sha256 (the release's published
# .sha256 asset), and release asset id. Any other `uname -m` fails closed.
architecture="$(uname -m)"
case "$architecture" in
    x86_64)
        readonly asset_dir="fabro-x86_64-unknown-linux-musl"
        readonly sha256="27ff7a930950a322fcd5debdba7e35f63e999179169ccbaadbe502090094d7b0"
        readonly asset_id="438318077"
        ;;
    aarch64)
        readonly asset_dir="fabro-aarch64-unknown-linux-musl"
        readonly sha256="1c3e7f25410f14d2407782b1effebc450138a65e3b5e844937c5edb6474c8731"
        readonly asset_id="438318044"
        ;;
    *)
        printf 'install-ci-fabro: unsupported architecture %s (supported: x86_64, aarch64); nothing installed\n' "$architecture" >&2
        exit 1
        ;;
esac
readonly asset="${asset_dir}.tar.gz"
readonly warm_dir="${INSTALL_CI_FABRO_WARM_DIR:-/__w/_warm/release-assets}"
readonly warm_asset="${warm_dir}/${sha256}"
readonly api_url="https://api.github.com/repos/fabro-sh/fabro/releases/assets/${asset_id}"
readonly fallback_url="https://github.com/fabro-sh/fabro/releases/download/${version}/${asset}"
readonly target="${1:-/usr/local/bin/fabro}"

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

verify_asset() {
    printf '%s  %s\n' "$sha256" "$1" | sha256sum --check --status
}

if [[ -f "$warm_asset" ]]; then
    if verify_asset "$warm_asset"; then
        tar -xzf "$warm_asset" -C "$scratch"
        install -m 0755 "${scratch}/${asset_dir}/fabro" "$target"
        "$target" --version
        exit 0
    fi
    printf 'install-ci-fabro: warm seed %s had a sha256 mismatch; trying GitHub releases API asset route\n' "$warm_asset" >&2
else
    printf 'install-ci-fabro: warm seed %s was absent; trying GitHub releases API asset route\n' "$warm_asset" >&2
fi

api_headers=(-H 'Accept: application/octet-stream')
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    api_headers+=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
fi

if curl --fail --silent --show-error --location --retry 5 --output "${scratch}/${asset}" "${api_headers[@]}" "$api_url"; then
    if ! verify_asset "${scratch}/${asset}"; then
        echo "install-ci-fabro: sha256 mismatch for GitHub releases API asset (expected ${sha256})" >&2
        exit 1
    fi

    tar -xzf "${scratch}/${asset}" -C "$scratch"
    install -m 0755 "${scratch}/${asset_dir}/fabro" "$target"
    "$target" --version
    exit 0
else
    api_status=$?
    printf 'install-ci-fabro: GitHub releases API asset route failed with curl exit status %s; trying GitHub release download URL\n' "$api_status" >&2
fi

if curl --fail --silent --show-error --location --retry 5 --output "${scratch}/${asset}" "$fallback_url"; then
    :
else
    fallback_status=$?
    printf 'install-ci-fabro: GitHub release download URL failed with curl exit status %s\n' "$fallback_status" >&2
    exit 1
fi

if ! verify_asset "${scratch}/${asset}"; then
    echo "install-ci-fabro: sha256 mismatch for GitHub release download (expected ${sha256})" >&2
    exit 1
fi

tar -xzf "${scratch}/${asset}" -C "$scratch"
install -m 0755 "${scratch}/${asset_dir}/fabro" "$target"
"$target" --version
