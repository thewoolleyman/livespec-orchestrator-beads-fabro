#!/usr/bin/env bash
# Preserve a live factory run named by its Dispatcher DISPATCH ID (the uuid4 hex the Dispatcher mints).
# See README.md. READ-ONLY on every fleet host: kubectl get, crictl ps/inspect, sudo cat over ssh.
#
# usage: preserve_dispatch.sh [--dry-run] <dispatch-id> [<factory-url>]
#   Resolves the dispatch id to its run ULID through the factory server's `livespec.dispatch.id`
#   run label, checks that the sandbox clone's `livespec.factoryRunId` git-config marker names the
#   same dispatch id, then runs preserve_runs.sh <run ULID> and prints its TSV row.
#   --dry-run      resolve and locate only (run, pod, node, HEAD, marker); push nothing.
#   <factory-url>  default https://gmktec-xubuntu.perch-rudd.ts.net:32276 (petri).
#   FABRO_BIN      the fabro client; default .livespec.jsonc
#                  livespec-orchestrator-beads-fabro.dispatcher.factories.petri.bin.
#
# Refusals (each exits non-zero and pushes nothing):
#   RESOLVE_FAILED  (exit 2) the server lists zero or several runs for that dispatch id.
#   NO_POD          (exit 3) the run has no Running sandbox pod (or no sandbox container):
#                   a terminal run's tree is gone, so there is nothing to copy.
#   MARKER_MISMATCH (exit 4) the pod's clone names a different dispatch id: refusing to
#                   preserve the wrong tree.
#   NO_CLIENT       (exit 5) no executable fabro client was found to ask the server.
set -u
dry=0; [ "${1:-}" = --dry-run ] && { dry=1; shift; }
did=${1:?usage: preserve_dispatch.sh [--dry-run] <dispatch-id> [<factory-url>]}
url=${2:-https://gmktec-xubuntu.perch-rudd.ts.net:32276}
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
fabro=${FABRO_BIN:-$(python3 -I - "$repo/.livespec.jsonc" <<'EOF'
import json, re, sys
text = re.sub(r"(?m)^\s*//.*$", "", open(sys.argv[1]).read())
print(json.loads(text)["livespec-orchestrator-beads-fabro"]["dispatcher"]["factories"]["petri"]["bin"])
EOF
)}
[ -x "$fabro" ] || { echo "NO_CLIENT fabro client not executable: ${fabro:-unset} (set FABRO_BIN)"; exit 5; }
sshn() { local h=$1; shift; ssh -n -o BatchMode=yes "$h" "$@"; }

rows=$(timeout 120 "$fabro" ps -a --server "$url" --label "livespec.dispatch.id=$did" --json | python3 -I -c '
import json, sys
d = json.load(sys.stdin); d = d if isinstance(d, list) else d.get("runs", [])
for r in d: print(r["run_id"], (r.get("status") or {}).get("kind", "?"))')
n=$(printf '%s\n' "$rows" | grep -c . || true)
[ "$n" = 1 ] || { echo "RESOLVE_FAILED dispatch=$did runs=$n ${rows//$'\n'/; }"; exit 2; }
run=${rows%% *}; status=${rows#* }
echo "dispatch=$did run=$run status=$status"

pod=$(sshn poweredge-xubuntu "sudo -n k3s kubectl get pods -n factory -l petri.run=$run --field-selector=status.phase=Running -o jsonpath='{range .items[*]}{.metadata.name} {.spec.nodeName}{\"\\n\"}{end}'")
[ -n "$pod" ] || { echo "NO_POD run=$run status=$status: no Running sandbox pod, nothing to copy"; exit 3; }
read -r podname node <<<"$pod"
echo "pod=$podname node=$node"
cid=$(sshn "$node" 'sudo -n k3s crictl ps --name sandbox -o json' | POD="$podname" python3 -I -c '
import json, os, sys
for c in json.load(sys.stdin)["containers"]:
    if c["labels"].get("io.kubernetes.pod.name") == os.environ["POD"]: print(c["id"]); break')
[ -n "$cid" ] || { echo "NO_POD run=$run pod=$podname: no sandbox container"; exit 3; }
pid=$(sshn "$node" "sudo -n k3s crictl inspect $cid" | python3 -I -c 'import json,sys;print(json.load(sys.stdin)["info"]["pid"])')
G=/proc/$pid/root/workspace/.git
marker=$(sshn "$node" "sudo -n git config --file $G/config --get livespec.factoryRunId" 2>/dev/null)
head=$(sshn "$node" "sudo -n cat $G/HEAD")
echo "pid=$pid head=[$head] marker=${marker:-none}"
[ "$marker" = "$did" ] || { echo "MARKER_MISMATCH want=$did got=${marker:-none}: refusing to preserve the wrong tree"; exit 4; }
[ "$dry" = 1 ] && { echo "DRY_RUN_OK run=$run (no push)"; exit 0; }
exec bash "$here/preserve_runs.sh" "$run"
