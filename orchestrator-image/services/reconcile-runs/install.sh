#!/usr/bin/env bash
# Install the `reconcile-runs` systemd service + timer on a dispatching host.
#
# The refusal below is the whole point of having an installer rather than a
# `cp`. `bd` reads the tenant password from a bare `BEADS_DOLT_PASSWORD` that
# only the project env wrapper injects; a unit installed without a resolvable
# wrapper does not fail loudly, it fails as "Access denied" / "no beads database
# found" every ten minutes forever, which reads as a missing tenant rather than
# as a missing credential. Refusing at install time is the one moment an
# operator is present to read the reason.
#
# Usage:
#   sudo ./install.sh --repo <primary-checkout> [--plugin-root <dir>] [--user <name>]
#
# Environment overrides (all optional, all for testing or a non-standard host):
#   LIVESPEC_ENV_WRAPPER  wrapper path to require AND to write into ExecStart
#                         (default: the path the committed unit already names)
#   UNIT_DIR              where the units are written (default /etc/systemd/system)
#   DRY_RUN=1             render and write the units, but run no systemctl

set -euo pipefail

readonly EX_CONFIG=78
readonly EX_USAGE=64

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly HERE
readonly SERVICE_TEMPLATE="${HERE}/reconcile-runs.service"
readonly TIMER_TEMPLATE="${HERE}/reconcile-runs.timer"

# The wrapper the committed unit names, read OUT of that unit rather than
# repeated here: a second copy of the path is a second thing to keep in sync,
# and the one that drifts is always the one nobody reads.
default_env_wrapper() {
  sed -n 's|^ExecStart=\([^ ]*\) --.*|\1|p' "${SERVICE_TEMPLATE}" | sed -n '1p'
}

usage() {
  printf 'usage: %s --repo <primary-checkout> [--plugin-root <dir>] [--user <name>]\n' \
    "${BASH_SOURCE[0]}" >&2
}

main() {
  local repo='' plugin_root='' run_as_user=''
  while (($#)); do
    case "$1" in
      --repo) shift; repo="${1:-}" ;;
      --plugin-root) shift; plugin_root="${1:-}" ;;
      --user) shift; run_as_user="${1:-}" ;;
      -h|--help) usage; return 0 ;;
      *) printf 'unknown argument: %s\n' "$1" >&2; usage; return "${EX_USAGE}" ;;
    esac
    shift || true
  done

  if [[ -z "${repo}" ]]; then
    printf 'ERROR: --repo <primary-checkout> is required\n' >&2
    usage
    return "${EX_USAGE}"
  fi
  if [[ ! -d "${repo}" ]]; then
    printf 'ERROR: --repo %s is not a directory\n' "${repo}" >&2
    return "${EX_CONFIG}"
  fi

  local template_wrapper env_wrapper
  template_wrapper="$(default_env_wrapper)"
  env_wrapper="${LIVESPEC_ENV_WRAPPER:-${template_wrapper}}"
  if [[ ! -x "${env_wrapper}" ]]; then
    printf 'ERROR: project env wrapper not executable: %s\n' "${env_wrapper}" >&2
    printf 'The timer would run `bd` without BEADS_DOLT_PASSWORD and fail every pass as\n' >&2
    printf 'an absent tenant rather than an absent credential. Install the wrapper (or set\n' >&2
    printf 'LIVESPEC_ENV_WRAPPER to where this host keeps it) and re-run.\n' >&2
    return "${EX_CONFIG}"
  fi

  : "${plugin_root:=${HERE%/orchestrator-image/services/reconcile-runs}/.claude-plugin}"
  : "${run_as_user:=$(id -un)}"
  local unit_dir="${UNIT_DIR:-/etc/systemd/system}"
  mkdir -p "${unit_dir}"

  sed \
    -e "s|@PLUGIN_ROOT@|${plugin_root}|g" \
    -e "s|@PRIMARY_REPO@|${repo}|g" \
    -e "s|@RUN_AS_USER@|${run_as_user}|g" \
    -e "s|${template_wrapper}|${env_wrapper}|g" \
    "${SERVICE_TEMPLATE}" >"${unit_dir}/reconcile-runs.service"
  cp "${TIMER_TEMPLATE}" "${unit_dir}/reconcile-runs.timer"
  printf 'installed %s/reconcile-runs.{service,timer}\n' "${unit_dir}"

  if [[ "${DRY_RUN:-}" == "1" ]]; then
    printf 'DRY_RUN=1: skipping systemctl daemon-reload / enable --now\n'
    return 0
  fi
  systemctl daemon-reload
  systemctl enable --now reconcile-runs.timer
  systemctl list-timers reconcile-runs.timer --no-pager
}

main "$@"
