#!/usr/bin/env bash
# Sandbox exec-environment parity read for a canary run (livespec-dev-tooling .ai/coordinator-duties.md,
# "A sandbox driver bump's canary checks environment parity"): umask, environment variable NAMES (never
# values) and resource limits of one factory sandbox pod, to compare against the previous driver's.
# READ-ONLY on every fleet host: kubectl get, sudo cat and sudo find over ssh.
#
# usage: parity_read.sh <dispatch-id> [<factory-url>]    resolve the run like preserve_dispatch.sh
#        parity_read.sh --pod <namespace> <pod>          read one pod directly
#   FABRO_BIN  the fabro client; default .livespec.jsonc
#              livespec-orchestrator-beads-fabro.dispatcher.factories.petri.bin.
#
# Refusals: RESOLVE_FAILED (exit 2), NO_POD (exit 3), NO_CLIENT (exit 5), as in preserve_dispatch.sh;
#   NODE_UNREACHABLE (exit 6) the pod's node name is not an ssh alias from here (factory nodes
#   poweredge-xubuntu and gmktec-xubuntu are).
#
# Baseline to compare against (sandbox-driver-kubernetes v0.8.2 canary, bd-ib-weawfe pod
# petri-01m6pvk9be2773455nq5nmk73d-l0, 2026-11-06 21:59Z): QoS Burstable, requests.cpu 3,
# limits.cpu 6; every exec'd command process at Umask 0022 (v0.8.1 ran them at 0077, the
# test_gap_closure [chmod -x] incident); only the driver's own supervisor shells keep 0077 by design.
# No environment-name list was recorded for that baseline: the first canary read becomes the record.
set -u
sshn() { local h=$1; shift; ssh -n -o BatchMode=yes "$h" "$@"; }
if [ "${1:-}" = --pod ]; then
  ns=${2:?usage: parity_read.sh --pod <namespace> <pod>}; pod=${3:?usage: parity_read.sh --pod <namespace> <pod>}
else
  did=${1:?usage: parity_read.sh <dispatch-id> [<factory-url>] | --pod <namespace> <pod>}
  url=${2:-https://gmktec-xubuntu.perch-rudd.ts.net:32276}
  repo=$(cd "$(dirname "$0")/../.." && pwd)
  fabro=${FABRO_BIN:-$(python3 -I - "$repo/.livespec.jsonc" <<'EOF'
import json, re, sys
text = re.sub(r"(?m)^\s*//.*$", "", open(sys.argv[1]).read())
print(json.loads(text)["livespec-orchestrator-beads-fabro"]["dispatcher"]["factories"]["petri"]["bin"])
EOF
)}
  [ -x "$fabro" ] || { echo "NO_CLIENT fabro client not executable: ${fabro:-unset} (set FABRO_BIN)"; exit 5; }
  rows=$(timeout 120 "$fabro" ps -a --server "$url" --label "livespec.dispatch.id=$did" --json | python3 -I -c '
import json, sys
d = json.load(sys.stdin); d = d if isinstance(d, list) else d.get("runs", [])
for r in d: print(r["run_id"], (r.get("status") or {}).get("kind", "?"))')
  n=$(printf '%s\n' "$rows" | grep -c . || true)
  [ "$n" = 1 ] || { echo "RESOLVE_FAILED dispatch=$did runs=$n"; exit 2; }
  run=${rows%% *}
  ns=factory
  pod=$(sshn poweredge-xubuntu "sudo -n k3s kubectl get pods -n factory -l petri.run=$run --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}'" 2>/dev/null)
  [ -n "$pod" ] || { echo "NO_POD run=$run: no Running sandbox pod"; exit 3; }
  echo "dispatch=$did run=$run"
fi

json=$(sshn poweredge-xubuntu "sudo -n k3s kubectl get pod -n $ns $pod -o json")
read -r node uid qos <<<"$(printf '%s' "$json" | python3 -I -c '
import json, sys; p = json.load(sys.stdin)
print(p["spec"]["nodeName"], p["metadata"]["uid"], p["status"].get("qosClass"))')"
echo "pod=$ns/$pod node=$node qos=$qos"
sshn "$node" true 2>/dev/null || { echo "NODE_UNREACHABLE node=$node: no ssh alias for it from here"; exit 6; }
printf '%s' "$json" | python3 -I -c '
import json, sys; p = json.load(sys.stdin)
for c in p["spec"]["containers"]:
    r = c.get("resources", {})
    print("container", c["name"], "requests", r.get("requests"), "limits", r.get("limits"), "image", c["image"].rsplit("/", 1)[-1])
    print("  spec env names:", " ".join(sorted(e["name"] for e in c.get("env", []))))'
q=$(printf '%s' "$qos" | tr 'A-Z' 'a-z'); u=$(printf '%s' "$uid" | tr - _)
case "$q" in
  guaranteed) base=/sys/fs/cgroup/kubepods.slice/kubepods-pod$u.slice ;;
  *) base=/sys/fs/cgroup/kubepods.slice/kubepods-$q.slice/kubepods-$q-pod$u.slice ;;
esac
for f in cpu.max memory.max memory.high pids.max; do echo "pod-cgroup $f = $(sshn "$node" "sudo -n cat $base/$f" 2>&1)"; done
for d in $(sshn "$node" "sudo -n find $base -mindepth 1 -maxdepth 1 -type d -name 'cri-containerd-*'"); do
  echo "container-cgroup $(basename "$d" | cut -c1-30) cpu.max=$(sshn "$node" "sudo -n cat $d/cpu.max") memory.max=$(sshn "$node" "sudo -n cat $d/memory.max")"
done
echo "--- processes: pid umask argv (exec'd commands should read 0022)"
envshown=0
for p in $(sshn "$node" "sudo -n cat $base/*/cgroup.procs" 2>/dev/null); do
  um=$(sshn "$node" "sudo -n cat /proc/$p/status 2>/dev/null" | awk '$1=="Umask:"{print $2}')
  [ -n "$um" ] || continue
  argv=$(sshn "$node" "sudo -n cat /proc/$p/cmdline 2>/dev/null" | tr '\0\n' '  ' | cut -c1-120)
  printf '%s %s %s\n' "$p" "$um" "$argv"
  if [ "$envshown" = 0 ] && [ "$um" = 0022 ] && [ "${argv#/pause}" = "$argv" ]; then
    # Split on NUL locally and keep only the text before the first '=': a value may contain newlines
    # (LIVESPEC_CREDENTIAL_USE_GUARD_SCRIPT carries a whole script), and a newline split prints value text.
    names=$(sshn "$node" "sudo -n cat /proc/$p/environ 2>/dev/null" | python3 -I -c '
import sys
recs = [r for r in sys.stdin.buffer.read().split(b"\0") if r]
print(" ".join(sorted({r.split(b"=", 1)[0].decode("utf-8", "replace") for r in recs})))')
    echo "    env NAMES of pid $p: $names"
    envshown=1
  fi
done
