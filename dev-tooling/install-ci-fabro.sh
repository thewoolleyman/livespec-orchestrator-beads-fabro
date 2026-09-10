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

set -euo pipefail

readonly version="v0.254.0"
readonly asset="fabro-x86_64-unknown-linux-musl.tar.gz"
readonly sha256="27ff7a930950a322fcd5debdba7e35f63e999179169ccbaadbe502090094d7b0"
readonly url="https://github.com/fabro-sh/fabro/releases/download/${version}/${asset}"
readonly target="${1:-/usr/local/bin/fabro}"

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

curl --fail --silent --show-error --location --retry 5 --output "${scratch}/${asset}" "$url"

if ! printf '%s  %s\n' "$sha256" "${scratch}/${asset}" | sha256sum --check --status; then
    echo "install-ci-fabro: sha256 mismatch for ${asset} (expected ${sha256})" >&2
    exit 1
fi

tar -xzf "${scratch}/${asset}" -C "$scratch"
install -m 0755 "${scratch}/fabro-x86_64-unknown-linux-musl/fabro" "$target"
"$target" --version
