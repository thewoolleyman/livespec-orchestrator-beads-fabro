#!/usr/bin/env bash
# Install ONE work-supply timer instance for ONE tenant repository.
#
# Run it once per tenant the host should keep supplied. The template units are
# shared by every instance; what is per-instance is the environment file naming
# the tenant and its drain budget, and the timer drop-in carrying the firing
# interval the operator chose for it.
#
# TWO REFUSALS, and they are the whole reason this is an installer rather than a
# `cp`.
#
# The WRAPPER refusal. `bd` reads the tenant password from a bare
# `BEADS_DOLT_PASSWORD` that only the project env wrapper injects. An instance
# installed without a resolvable wrapper does not fail loudly: every pass dies
# with `Access denied` / `no beads database found`, which reads as a missing
# tenant rather than as a missing credential, on the interval, for ever.
# Install time is the one moment an operator is present to read the reason.
#
# The INTERVAL refusal. Two known concurrency defects live under this timer —
# `wip_cap` is not exclusive across engines admitting in the same instant
# (`bd-ib-2vda`), and a sibling engine's reconcile can cancel a just-launched
# re-dispatch (`bd-ib-m1av`), whose stamp window is roughly forty seconds. The
# ratified contract deliberately adds NO exclusion between concurrent passes
# and licenses no host-scoped lock, so the only thing standing between those
# defects and a tight interval is this refusal. A span below the documented
# minimum is refused, naming the instance, the span given and the minimum; so
# is a span this installer cannot measure, because an unreadable interval must
# not pass the minimum by being unreadable.
#
# Usage:
#   sudo ./install.sh --repo <tenant-checkout> [--interval <span>] \
#        [--budget <count>] [--instance <name>]
#
#   --interval  firing interval, default 30min, minimum 10min. A span is
#               `<positive integer><unit>` with unit one of
#               s/sec/m/min/h/hr/hour — a deliberately narrow subset of
#               systemd's time-span grammar, so that everything this installer
#               cannot measure is refused rather than guessed.
#   --budget    per-pass dispatch ceiling handed to `loop --budget`, default 3.
#   --instance  systemd instance name, default the basename of --repo.
#
# Environment overrides (all optional, all for testing or a non-standard host):
#   LIVESPEC_ENV_WRAPPER  wrapper path to require AND to write into the
#                         instance environment file (default:
#                         /usr/local/bin/with-livespec-env.sh)
#   UNIT_DIR              where the units are written (default
#                         /etc/systemd/system)
#   INSTANCE_ENV_DIR      where the per-instance environment files are written
#                         (default /etc/livespec/work-supply)
#   DRY_RUN=1             render and write everything, but run no systemctl

set -euo pipefail

readonly EX_CONFIG=78
readonly EX_USAGE=64

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly HERE
readonly SERVICE_TEMPLATE="${HERE}/work-supply@.service"
readonly TIMER_TEMPLATE="${HERE}/work-supply@.timer"
readonly LAUNCHER="${HERE}/work-supply-pass.sh"

# The wrapper this family's tenants share. Declared once, here, because the
# work-supply service deliberately does NOT name it (the detached pass does),
# so there is no unit text to read it back out of as `reconcile-runs` does.
readonly DEFAULT_ENV_WRAPPER='/usr/local/bin/with-livespec-env.sh'
readonly DEFAULT_INTERVAL='30min'
readonly MINIMUM_INTERVAL='10min'
readonly MINIMUM_INTERVAL_SECONDS=600
readonly DEFAULT_BUDGET='3'
# The initial trigger. `OnUnitActiveSec` alone never fires on a unit that has
# never been active, so without this an instance installed and enabled would
# sit silent until the next reboot.
readonly ON_BOOT_SEC='2min'

usage() {
  sed -n '/^# Usage:/,/^#   DRY_RUN=1/p' "${BASH_SOURCE[0]}" >&2
}

# The span in seconds on stdout, or a non-zero exit when it is outside the
# grammar this installer can measure.
interval_seconds() {
  local span="$1"
  if [[ ! "${span}" =~ ^([1-9][0-9]*)(s|sec|m|min|h|hr|hour)$ ]]; then
    return 1
  fi
  local number="${BASH_REMATCH[1]}" unit="${BASH_REMATCH[2]}"
  case "${unit}" in
    s|sec) printf '%s' "${number}" ;;
    m|min) printf '%s' "$((number * 60))" ;;
    *) printf '%s' "$((number * 3600))" ;;
  esac
}

main() {
  local repo='' interval="${DEFAULT_INTERVAL}" budget="${DEFAULT_BUDGET}" instance=''
  while (($#)); do
    case "$1" in
      --repo) shift; repo="${1:-}" ;;
      --interval) shift; interval="${1:-}" ;;
      --budget) shift; budget="${1:-}" ;;
      --instance) shift; instance="${1:-}" ;;
      -h|--help) usage; return 0 ;;
      *) printf 'unknown argument: %s\n' "$1" >&2; usage; return "${EX_USAGE}" ;;
    esac
    shift || true
  done

  if [[ -z "${repo}" ]]; then
    printf 'ERROR: --repo <tenant-checkout> is required\n' >&2
    usage
    return "${EX_USAGE}"
  fi
  if [[ ! -d "${repo}" ]]; then
    printf 'ERROR: --repo %s is not a directory\n' "${repo}" >&2
    return "${EX_CONFIG}"
  fi
  : "${instance:=$(basename "${repo}")}"
  if [[ ! "${budget}" =~ ^[1-9][0-9]*$ ]]; then
    printf 'ERROR: instance %s: --budget %s is not a positive integer\n' \
      "${instance}" "${budget}" >&2
    return "${EX_CONFIG}"
  fi

  local seconds
  if ! seconds="$(interval_seconds "${interval}")"; then
    printf 'ERROR: instance %s: --interval %s is not a span this installer can measure; the minimum is %s\n' \
      "${instance}" "${interval}" "${MINIMUM_INTERVAL}" >&2
    printf 'Write the interval as <positive integer><unit> with unit one of s/sec/m/min/h/hr/hour.\n' >&2
    return "${EX_CONFIG}"
  fi
  if ((seconds < MINIMUM_INTERVAL_SECONDS)); then
    printf 'ERROR: instance %s: --interval %s is shorter than the minimum %s\n' \
      "${instance}" "${interval}" "${MINIMUM_INTERVAL}" >&2
    printf 'Concurrent passes have no exclusion between them by contract, and a sibling\n' >&2
    printf 'engine can cancel a just-launched re-dispatch inside a ~40s stamp window, so\n' >&2
    printf 'firings are kept far apart rather than fenced.\n' >&2
    return "${EX_CONFIG}"
  fi

  local env_wrapper="${LIVESPEC_ENV_WRAPPER:-${DEFAULT_ENV_WRAPPER}}"
  if [[ ! -x "${env_wrapper}" ]]; then
    printf 'ERROR: instance %s: project env wrapper not executable: %s\n' \
      "${instance}" "${env_wrapper}" >&2
    printf 'Every pass would run bd without BEADS_DOLT_PASSWORD and fail as an absent\n' >&2
    printf 'tenant rather than an absent credential, on the interval, for ever. Install the\n' >&2
    printf 'wrapper (or set LIVESPEC_ENV_WRAPPER to where this host keeps it) and re-run.\n' >&2
    return "${EX_CONFIG}"
  fi

  local unit_dir="${UNIT_DIR:-/etc/systemd/system}"
  local instance_env_dir="${INSTANCE_ENV_DIR:-/etc/livespec/work-supply}"
  mkdir -p "${unit_dir}" "${instance_env_dir}" "${unit_dir}/work-supply@${instance}.timer.d"

  sed \
    -e "s|@LAUNCHER@|${LAUNCHER}|g" \
    -e "s|@INSTANCE_ENV_DIR@|${instance_env_dir}|g" \
    "${SERVICE_TEMPLATE}" >"${unit_dir}/work-supply@.service"
  cp "${TIMER_TEMPLATE}" "${unit_dir}/work-supply@.timer"

  local env_file="${instance_env_dir}/${instance}.env"
  cat >"${env_file}" <<EOF
# livespec work-supply instance ${instance} — written by install.sh.
# Read by work-supply@${instance}.service through EnvironmentFile.
LIVESPEC_WORK_SUPPLY_REPO=${repo}
LIVESPEC_WORK_SUPPLY_BUDGET=${budget}
LIVESPEC_WORK_SUPPLY_ENV_WRAPPER=${env_wrapper}
EOF
  chmod 0644 "${env_file}"

  cat >"${unit_dir}/work-supply@${instance}.timer.d/interval.conf" <<EOF
# Firing interval for instance ${instance} — written by install.sh from
# --interval. The template unit carries no interval of its own, so this
# drop-in is what makes work-supply@${instance}.timer loadable at all.
[Timer]
OnBootSec=${ON_BOOT_SEC}
OnUnitActiveSec=${interval}
EOF

  printf 'installed %s/work-supply@.{service,timer}\n' "${unit_dir}"
  printf 'installed %s\n' "${env_file}"
  printf 'instance work-supply@%s.timer fires every %s for %s with budget %s\n' \
    "${instance}" "${interval}" "${repo}" "${budget}"

  if [[ "${DRY_RUN:-}" == "1" ]]; then
    printf 'DRY_RUN=1: skipping systemctl daemon-reload / enable --now\n'
    return 0
  fi
  systemctl daemon-reload
  systemctl enable --now "work-supply@${instance}.timer"
  systemctl list-timers "work-supply@${instance}.timer" --no-pager
}

main "$@"
