#!/usr/bin/env bash
# Start ONE unattended drain pass for one tenant, through the plugin build that
# tenant's runtime has registered AT THIS MOMENT.
#
# This script is what `work-supply@.service` runs on every firing. It exists
# because of two things the unit file cannot do.
#
# 1. RESOLVE THE BUILD LATE. The `reconcile-runs` sibling substitutes a plugin
#    root at INSTALL time, which pins that unit to one cache build for ever:
#    after a release the unit keeps executing a build the operator has already
#    replaced. This resolver reads the tenant's registered project-scoped
#    install out of the Claude Code plugin registry on each firing, so the next
#    pass after a release runs the released build with nothing reinstalled. It
#    REFUSES, naming the tenant, when no registered install exists — it never
#    falls back to a build pinned earlier or to a guessed path, because a
#    guessed path is how a host silently keeps running a retired build.
#
#    The registry read is a small duplicate of the package's own
#    `_dispatcher_registered_install_currency._registered_install_path`, and the
#    duplication is structural rather than careless: the resolver decides WHICH
#    build to execute, so it cannot itself live inside the build it resolves.
#
# 2. DETACH THE PASS. `dispatcher.py loop` blocks until its wave's post-verdict
#    stages finish, which is hours for one wave, and systemd never starts a
#    `Type=oneshot` service that is still active. A unit whose ExecStart ran the
#    drain would therefore skip every firing for the length of the pass. Each
#    pass is handed to its OWN transient unit instead, with no `--wait`, so the
#    launcher returns in under a second and capacity that frees during a long
#    pass is offered to ready work within one interval. Overlapping passes are
#    ordinary concurrent unattended drains: each is bounded by `wip_cap`, and
#    this script adds NO host-scoped lock between them (a host-scoped fence is
#    invalid here — ledger writers are multi-host; see
#    `.ai/ledger-writers-are-multi-host.md`).
#
# 3. DROP TO THE OPERATOR. Detaching the pass is what FORCES this script to own
#    identity too, which is why the two are settled in one place. A system-scope
#    `systemd-run --unit` from a non-root caller needs polkit authorization no
#    timer can obtain, so the firing runs as root; but a pass running as root
#    resolves root's `$HOME`, and both things it reaches for there belong to the
#    operator — the Claude Code plugin registry, and `~/.fabro/bin/fabro`. The
#    pass is therefore started with the operator identity and home the instance
#    environment file names, and this script never infers either.
#
# NOTHING HERE READS AN AMBIENT `$HOME` AND HOPES. systemd sets `$HOME` only for
# a unit declaring `User=` (systemd.exec(5)), and the service deliberately
# declares none, so under the timer there is no `$HOME` at all. A default
# composed from an unset one is `/.claude/plugins/installed_plugins.json`: it
# cannot exist, so every firing of every instance refuses — and refuses with
# "no registered install for this tenant", which reads as an unregistered tenant
# rather than as an unresolvable home. `$HOME` is consulted only as the fallback
# for a hand-run launcher, where it IS the operator's; when neither source
# resolves, this script refuses NAMING BOTH.
#
# The credential wrapper is invoked by the DETACHED pass and not by this
# script. `bd` reads the tenant password from a bare `BEADS_DOLT_PASSWORD` that
# only the wrapper injects, and a transient unit does not inherit this process's
# environment — so wrapping the launcher would both lose the credential and
# make the pass's own wrapper call a NESTED one, which poisons the wrapper's
# 300-second cache for every other caller on the host.
#
# No wall-clock ceiling is imposed on a pass. The pass is bounded by its
# `--budget` and by its own terminal disposition; a timing bound that killed it
# mid-flight could interrupt protected work (an active commit or an open
# Red-Green pair), which constraints.md §"Process boundaries" forbids a timing
# bound from doing. A pass that dies anyway leaves its claims to the ratified
# stranded-claim release.
#
# Usage (systemd supplies the instance; everything else arrives in the
# per-instance EnvironmentFile `install.sh` wrote):
#   work-supply-pass.sh --instance <name>
#
# Environment (the first five are the per-instance settings `install.sh`
# writes; the last two are for this repository's tests and for a non-standard
# host):
#   LIVESPEC_WORK_SUPPLY_REPO             tenant checkout to drain
#   LIVESPEC_WORK_SUPPLY_BUDGET           per-pass dispatch ceiling
#   LIVESPEC_WORK_SUPPLY_ENV_WRAPPER      credential wrapper the pass runs under
#   LIVESPEC_WORK_SUPPLY_USER             operator identity the pass runs as
#   LIVESPEC_WORK_SUPPLY_HOME             that operator's home; the registry and
#                                         the pass's own $HOME come from it
#                                         (falls back to $HOME when hand-run)
#   LIVESPEC_WORK_SUPPLY_PLUGIN_REGISTRY  registry path (default: the Claude
#                                         Code registry under that home)
#   LIVESPEC_WORK_SUPPLY_RUNNER           program that starts the transient unit
#                                         (default: systemd-run)

set -euo pipefail

readonly EX_CONFIG=78
readonly EX_USAGE=64

# The orchestrator plugin whose registered install is resolved — this one,
# wherever the timer happens to run. Never read from the tenant's own manifest,
# which names the tenant rather than this plugin.
readonly PLUGIN_NAME='livespec-orchestrator-beads-fabro'
readonly INVOKER='timer:work-supply'

refuse() {
  printf 'ERROR: work-supply pass refused: %s\n' "$1" >&2
}

require_value() {
  local name="$1" value="$2"
  if [[ -z "${value}" ]]; then
    refuse "${name} is empty, so the instance's EnvironmentFile did not supply it"
    return "${EX_CONFIG}"
  fi
}

# The install path the registry records for this tenant, on stdout. Exits
# non-zero with a reason on stderr when the registry cannot be read or records
# no project-scoped install for the tenant.
registered_install() {
  local registry="$1" repo="$2"
  python3 - "$registry" "$repo" "${PLUGIN_NAME}" <<'PY'
import json
import os
import sys

registry, repo, plugin = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with open(registry, encoding="utf-8") as handle:
        document = json.load(handle)
except (OSError, ValueError) as error:
    sys.stderr.write(f"the plugin registry {registry} could not be read ({error})\n")
    raise SystemExit(1) from None
plugins = document.get("plugins") if isinstance(document, dict) else None
if not isinstance(plugins, dict):
    sys.stderr.write(f"the plugin registry {registry} records no plugins object\n")
    raise SystemExit(1)
target = os.path.realpath(repo)
for key, entries in plugins.items():
    if key.split("@", 1)[0] != plugin or not isinstance(entries, list):
        continue
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        project = entry.get("projectPath")
        install = entry.get("installPath")
        if not isinstance(project, str) or not isinstance(install, str) or not project:
            continue
        if os.path.realpath(project) == target:
            sys.stdout.write(install)
            raise SystemExit(0)
sys.stderr.write(
    f"the plugin registry {registry} records no registered install of {plugin} "
    f"whose project path is {repo}\n"
)
raise SystemExit(1)
PY
}

main() {
  local instance=''
  while (($#)); do
    case "$1" in
      --instance) shift; instance="${1:-}" ;;
      -h|--help)
        sed -n '/^# Usage/,/^$/p' "${BASH_SOURCE[0]}" >&2
        return 0
        ;;
      *) printf 'unknown argument: %s\n' "$1" >&2; return "${EX_USAGE}" ;;
    esac
    shift || true
  done
  if [[ -z "${instance}" ]]; then
    printf 'ERROR: --instance <name> is required\n' >&2
    return "${EX_USAGE}"
  fi

  local repo budget wrapper user home registry runner
  repo="${LIVESPEC_WORK_SUPPLY_REPO:-}"
  budget="${LIVESPEC_WORK_SUPPLY_BUDGET:-}"
  wrapper="${LIVESPEC_WORK_SUPPLY_ENV_WRAPPER:-}"
  user="${LIVESPEC_WORK_SUPPLY_USER:-}"
  # The instance file's home first, this process's own only as the hand-run
  # fallback: under the timer there is no `$HOME` at all (see the header), and
  # on a host where root happens to have one, root's is the WRONG home.
  home="${LIVESPEC_WORK_SUPPLY_HOME:-${HOME:-}}"
  runner="${LIVESPEC_WORK_SUPPLY_RUNNER:-systemd-run}"

  require_value LIVESPEC_WORK_SUPPLY_REPO "${repo}" || return "${EX_CONFIG}"
  require_value LIVESPEC_WORK_SUPPLY_BUDGET "${budget}" || return "${EX_CONFIG}"
  require_value LIVESPEC_WORK_SUPPLY_ENV_WRAPPER "${wrapper}" || return "${EX_CONFIG}"
  require_value LIVESPEC_WORK_SUPPLY_USER "${user}" || return "${EX_CONFIG}"
  if [[ -z "${home}" ]]; then
    refuse "neither LIVESPEC_WORK_SUPPLY_HOME nor HOME is set, so the operator home is unresolvable: the plugin registry cannot be located and the pass would resolve fabro under the wrong account"
    return "${EX_CONFIG}"
  fi
  registry="${LIVESPEC_WORK_SUPPLY_PLUGIN_REGISTRY:-${home}/.claude/plugins/installed_plugins.json}"
  if [[ ! "${budget}" =~ ^[1-9][0-9]*$ ]]; then
    refuse "LIVESPEC_WORK_SUPPLY_BUDGET is ${budget}, which is not a positive integer"
    return "${EX_CONFIG}"
  fi

  local install_path
  if ! install_path="$(registered_install "${registry}" "${repo}")" || [[ -z "${install_path}" ]]; then
    refuse "no registered plugin install resolves for tenant ${repo}; a firing MUST NOT guess a build path, so this pass starts nothing"
    return "${EX_CONFIG}"
  fi
  local dispatcher="${install_path}/scripts/bin/dispatcher.py"
  if [[ ! -f "${dispatcher}" ]]; then
    refuse "the registered install ${install_path} for tenant ${repo} carries no ${dispatcher}, so there is no build to execute"
    return "${EX_CONFIG}"
  fi

  local stamp
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  # The pass id is unique per firing — timestamp AND launcher pid — so a firing
  # that lands while an earlier pass is still alive gets its own unit rather
  # than colliding with it.
  local unit="work-supply-pass-${instance}-${stamp}-$$"

  printf 'work-supply: tenant %s, build %s, budget %s, user %s, home %s, unit %s\n' \
    "${repo}" "${install_path}" "${budget}" "${user}" "${home}" "${unit}"

  # NO `--item`: the pass drains the ranked queue, which is what makes it an
  # ordinary unattended drain under `wip_cap`, every admission condition and
  # the fail-closed unattended cost gate. NO `--wait`: see the header.
  #
  # `--uid` and `--setenv HOME=` are what make the pass the OPERATOR's even
  # though this firing is root's. Both are passed: `--uid` alone leaves the
  # home systemd derives for the transient unit implicit, and the one thing it
  # must agree with is the registry THIS process just read.
  "${runner}" \
    --collect \
    --unit "${unit}" \
    --description "livespec work-supply drain pass for ${repo}" \
    --uid "${user}" \
    --setenv "HOME=${home}" \
    -- "${wrapper}" -- /usr/bin/python3 "${dispatcher}" loop \
    --repo "${repo}" \
    --budget "${budget}" \
    --invoker "${INVOKER}" \
    --json
}

main "$@"
