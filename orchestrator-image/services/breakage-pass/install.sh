#!/usr/bin/env bash
# Install the scheduled-workflow breakage-pass service and timer for one repo.

set -euo pipefail

readonly EX_CONFIG=78
readonly EX_USAGE=64
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SERVICE_TEMPLATE="${HERE}/breakage-pass.service"
readonly TIMER_TEMPLATE="${HERE}/breakage-pass.timer"

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
    return "${EX_USAGE}"
  fi
  if [[ ! -d "${repo}" ]]; then
    printf 'ERROR: --repo %s is not a directory\n' "${repo}" >&2
    return "${EX_CONFIG}"
  fi
  local env_wrapper="${LIVESPEC_ENV_WRAPPER:-/usr/local/bin/with-livespec-env.sh}"
  if [[ ! -x "${env_wrapper}" ]]; then
    printf 'ERROR: project env wrapper not executable: %s\n' "${env_wrapper}" >&2
    printf 'The timer needs BEADS_DOLT_PASSWORD to reach the tenant ledger.\n' >&2
    return "${EX_CONFIG}"
  fi
  : "${plugin_root:=${HERE%/orchestrator-image/services/breakage-pass}/.claude-plugin}"
  : "${run_as_user:=$(id -un)}"
  local unit_dir="${UNIT_DIR:-/etc/systemd/system}"
  mkdir -p "${unit_dir}"
  sed \
    -e "s|@PLUGIN_ROOT@|${plugin_root}|g" \
    -e "s|@PRIMARY_REPO@|${repo}|g" \
    -e "s|@RUN_AS_USER@|${run_as_user}|g" \
    -e "s|/usr/local/bin/with-livespec-env.sh|${env_wrapper}|g" \
    "${SERVICE_TEMPLATE}" >"${unit_dir}/breakage-pass.service"
  cp "${TIMER_TEMPLATE}" "${unit_dir}/breakage-pass.timer"
  if [[ "${DRY_RUN:-}" == '1' ]]; then
    return 0
  fi
  systemctl daemon-reload
  systemctl enable --now breakage-pass.timer
  systemctl list-timers breakage-pass.timer --no-pager
}

main "$@"
