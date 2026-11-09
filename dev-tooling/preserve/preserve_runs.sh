#!/usr/bin/env bash
# Preserve live factory runs' checkouts to origin WITHOUT Fabro (bd-ib-m7lxgn workaround). See README.md.
# READ-ONLY on every fleet host: kubectl get, crictl ps/inspect, sudo find, sudo cat over ssh. A container
# worker node (homelab-worker.livespec.dev/class=worker) is read through `kubectl exec` into the sandbox
# instead: find, cat and `git config --get` only (README rule 11).
# Pushes from a local bare copy to refs/heads/preserve/run-<RUNID> on the run's own origin.
#
# usage: preserve_runs.sh [RUNID ...]     (no args = every Running pod in the factory namespace)
# output: one TSV line per run: RUNID NODE REPO HEAD_SHA REF VERIFIED SECONDS SOURCE
#   SOURCE names the commit chosen: `tip` (the run branch's tip), `reflog@{N}` (the Nth older run-branch
#   reflog entry), `HEAD` (no run branch), or `-` when nothing carried work (VERIFIED reads EMPTY).
set -u
WORK=${PRESERVE_WORK:-${XDG_STATE_HOME:-$HOME/.local/state}/livespec-preserve}
mkdir -p "$WORK"
CP="-o ControlMaster=auto -o ControlPersist=120 -o ControlPath=${TMPDIR:-/tmp}/pcm-$$-%C"
sshn() { local h=$1; shift; ssh -n -o BatchMode=yes $CP "$h" "$@"; }

pods=$(sshn poweredge-xubuntu 'sudo -n k3s kubectl get pods -n factory -o json' | python3 -c '
import json,sys
for p in json.load(sys.stdin)["items"]:
    if p["status"].get("phase")!="Running": continue
    l=p["metadata"].get("labels") or {}
    print(l.get("petri.run",""), p["metadata"]["name"], p["spec"].get("nodeName",""))')
# Container worker nodes run plain containerd and take no ssh login (no k3s crictl, no fleet ssh user):
# their sandboxes are read through the API server's exec, the route the cluster already authorizes
# (legacy-coordinator-agent ruling 2026-11-09, livespec-dev-tooling-smzkpu). Every other node keeps ssh.
workers=" $(sshn poweredge-xubuntu "sudo -n k3s kubectl get nodes -l homelab-worker.livespec.dev/class=worker -o jsonpath='{.items[*].metadata.name}'") "
want=" $* "
printf 'RUN\tNODE\tREPO\tHEAD\tREF\tVERIFIED\tSECONDS\tSOURCE\n'
while read -r run pod node; do
  [ -n "$run" ] || continue
  if [ $# -gt 0 ] && [[ "$want" != *" $run "* ]]; then continue; fi
  t0=$(date +%s); out="$run\t$node"
  if [[ "$workers" == *" $node "* ]]; then
    # rd <command>: run one read-only command inside the pod's sandbox container, through the API server.
    rd() { sshn poweredge-xubuntu "sudo -n k3s kubectl exec -n factory $pod -c sandbox -- sh -c $(printf '%q' "$1")"; }
    # rd_files <list>: the listed files (relative to $G), concatenated in order. The list goes on stdin:
    # as exec arguments it would ride in the exec request's URL, which a large object store outgrows.
    rd_files() { tr '\n' '\0' < "$1" | ssh -o BatchMode=yes $CP poweredge-xubuntu \
      "sudo -n k3s kubectl exec -i -n factory $pod -c sandbox -- sh -c $(printf '%q' "cd $G && xargs -0 -r cat")"; }
    rd 'test -d /workspace/.git' 2>/dev/null || { printf "$out\t-\t-\t-\tNO_CONTAINER\t%s\t-\n" $(( $(date +%s)-t0 )); continue; }
    G=/workspace/.git
  else
    rd() { sshn "$node" "sudo -n $1"; }
    rd_files() { (cd "$D" && sed "s#^#$G/#" "$1" | tr '\n' '\0' | xargs -0 -r printf '%q ' > "$D.args"); rd "cat $(cat "$D.args")"; }
    cid=$(sshn "$node" 'sudo -n k3s crictl ps --name sandbox -o json' | POD="$pod" python3 -c '
import json,sys,os
for c in json.load(sys.stdin)["containers"]:
    if c["labels"].get("io.kubernetes.pod.name")==os.environ["POD"]: print(c["id"]); break')
    [ -n "$cid" ] || { printf "$out\t-\t-\t-\tNO_CONTAINER\t%s\t-\n" $(( $(date +%s)-t0 )); continue; }
    pid=$(sshn "$node" "sudo -n k3s crictl inspect $cid" | python3 -c 'import json,sys;print(json.load(sys.stdin)["info"]["pid"])')
    G=/proc/$pid/root/workspace/.git
  fi
  url=$(rd "git config --file $G/config --get remote.origin.url" 2>/dev/null)
  # The Dispatcher's dispatch id, from the clone's livespec.factoryRunId marker (the same marker
  # preserve_dispatch.sh checks). The factory's own needs-human ending keys its ref by THIS id, and
  # pods carry no dispatch-id label, so the marker is the only source on the node.
  did=$(rd "git config --file $G/config --get livespec.factoryRunId" 2>/dev/null)
  # Strip any credential the sandbox's remote carries; push with this host's own auth.
  repo=$(printf '%s' "$url" | grep -oE 'github\.com[:/][^/]+/[^/ ]+' | sed -E 's#^github\.com[:/]#https://github.com/#; s#\.git$##')
  D=$WORK/$run.git
  for _ in 1 2 3; do
    head=$(rd "cat $G/HEAD")
    rm -rf "$D" "$D.push.err"; mkdir -p "$D/refs/tags" "$D/refs/remotes"
    printf '[core]\n\trepositoryformatversion = 0\n\tbare = true\n' > "$D/config"
    # One find (with sizes) and ONE bulk cat, split locally by size: a per-file ssh round trip
    # took >30 min for 16 parallel runs under CI load (2026-11-05 window). The run branch's REFLOG is
    # copied too: a fix or refresh round can reset the branch to plain master, and the reflog is then
    # the only record of the commits that carried the run's work (7fdesc, reuccp, 2026-11-09).
    rd "find $G -type f -printf '%s %P\\n'" \
      | grep -E " (objects/|refs/heads/|HEAD$|packed-refs$|logs/HEAD$|logs/refs/heads/fabro/run/$run$)" \
      | grep -v ' objects/info/' > "$D.sizes"
    cut -d' ' -f2- "$D.sizes" > "$D.list"
    fail=0
    rd_files "$D.list" | python3 -I -c '
import os, sys
# stdin = the listed files concatenated in order; split them back by the sizes file.
dest, inp = sys.argv[1], sys.stdin.buffer
for line in open(sys.argv[2]):
    n, rel = line.rstrip("\n").split(" ", 1)
    data = inp.read(int(n))
    if len(data) != int(n): sys.exit(1)
    p = os.path.join(dest, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(data)
sys.exit(1 if inp.read(1) else 0)' "$D" "$D.sizes" || fail=1
    case "$head" in ref:*) sha=$(git -C "$D" rev-parse --verify -q "${head#ref: }") ;; *) sha=$head ;; esac
    # The run's checkpoints live on fabro/run/<RUN>. A late node (e.g. refresh_repair) can leave the
    # workspace HEAD detached on master; preserving HEAD then drops the run's work (rhivsm, 2026-11-05).
    rb=$(git -C "$D" rev-parse --verify -q "refs/heads/fabro/run/$run" 2>/dev/null)
    [ -n "$rb" ] && sha=$rb
    # A commit landing mid-copy leaves HEAD pointing at objects never listed: re-read.
    [ "$fail" = 0 ] && [ -n "$sha" ] && git -C "$D" fsck --connectivity-only --no-dangling "$sha" >/dev/null 2>&1 && break
  done
  # CHOOSE THE COMMIT THAT CARRIES THE WORK (bd-ib-anmcjq). A commit carries work when its tree differs
  # from the tree of its merge base with origin/master; a two-way diff against master's current tip
  # would count master's later commits as work. Candidates, in order: the run-branch tip (`tip`, or
  # `HEAD` when there is no run branch), then the run branch's reflog newest first (`reflog@{N}`),
  # then the HEAD reflog newest first (`HEAD@{N}`). With none carrying work the row reads EMPTY and
  # NOTHING is pushed, so represerve.sh writes no alias either.
  src=-; carries=0; decided=0
  if [ "$fail" = 0 ] && [ -n "$sha" ] && [ -n "$repo" ] \
     && git -C "$D" fetch -q "$repo" "+refs/heads/master:refs/remotes/origin/master" 2>/dev/null; then
    decided=1
    # Reflog lines are oldest first: `<old> <new> <who> <when>\t<msg>`, so tac gives newest first.
    # Entry 0 of each reflog is the current value; @{N} counts older entries as git does.
    newest_first() { tac "$1" 2>/dev/null | awk '{print $2}'; }
    # Parallel arrays, never `set --`: the run filter above reads this script's own `$#`.
    labels=("$([ -n "$rb" ] && echo tip || echo HEAD)"); shas=("$sha")
    if [ -n "$rb" ]; then
      i=0; for c in $(newest_first "$D/logs/refs/heads/fabro/run/$run"); do labels+=("reflog@{$i}"); shas+=("$c"); i=$((i + 1)); done
    fi
    i=0; for c in $(newest_first "$D/logs/HEAD"); do labels+=("HEAD@{$i}"); shas+=("$c"); i=$((i + 1)); done
    seen=" "
    for k in "${!shas[@]}"; do
      label=${labels[$k]}; c=${shas[$k]}
      case "$seen" in *" $c "*) continue ;; esac
      seen="$seen$c "
      git -C "$D" cat-file -e "$c^{commit}" 2>/dev/null || continue
      git -C "$D" fsck --connectivity-only --no-dangling "$c" >/dev/null 2>&1 || continue
      mb=$(git -C "$D" merge-base "$c" refs/remotes/origin/master 2>/dev/null) || continue
      if ! git -C "$D" diff --quiet "$mb" "$c" 2>/dev/null; then sha=$c; src=$label; carries=1; break; fi
    done
  fi
  ref=refs/heads/preserve/run-$run
  if [ "$carries" = 0 ]; then
    # Either nothing carried work (EMPTY) or the choice could not be made (copy, fsck or master fetch
    # failed); never push a commit whose content was not established.
    if [ "$decided" = 1 ]; then v=EMPTY
    else v="FAILED(fail=$fail sha=${sha:-none} repo=${repo:-none}: copy, fsck or master fetch failed)"; fi
    printf "$out\t%s\t%s\t-\t%s\t%s\t-\n" "${repo:--}" "${sha:-none}" "$v" $(( $(date +%s)-t0 ))
    continue
  fi
  # Never move a preserve ref off its own history: if the new tip does not contain the old one, keep
  # the old ref and write this pass to a SHA-suffixed sibling instead.
  old=$(git ls-remote "$repo" "$ref" | cut -f1)
  if [ -n "$old" ] && [ "$old" != "$sha" ] && ! git -C "$D" merge-base --is-ancestor "$old" "$sha" 2>/dev/null; then
    ref=$ref-${sha:0:12}
  fi
  if { pushed=1; for pa in 1 2 3 4 5; do git -C "$D" push -q "$repo" "+${sha}:${ref}" 2>"$D.push.err" && { pushed=0; break; }
          # GitHub answers "[remote rejected] ... (failed)" to concurrent pushes into one repo: back off, retry.
          sleep $((pa * 7 + RANDOM % 7)); done; [ "$pushed" = 0 ]; }; then
    # GitHub can lag a just-pushed ref by a few seconds: re-read before calling it a mismatch.
    for _ in 1 2 3 4 5; do got=$(git ls-remote "$repo" "$ref" | cut -f1); [ "$got" = "$sha" ] && break; sleep 3; done
    v=$([ "$got" = "$sha" ] && echo VERIFIED || echo "MISMATCH:$got")
    # A run's needs-human ref SEEDS its recovery, and a run-keyed ref leads the seed list, so a
    # mid-run copy written here pre-empts the tree the run's own ending later pushes. Measured
    # 2026-11-07 on bd-ib-azhnw5 and livespec-dev-tooling-t5ct2q. So only a preserve at the
    # 330-minute wall-budget line or right before a cancel writes one: set
    # PRESERVE_WRITE_NEEDS_HUMAN=1. CREATE-ONLY at the verified sha; never move an existing one.
    # The ref is keyed by the DISPATCH id, the name the factory's own needs-human ending writes and
    # every seed lookup reads; keying it by the run ULID left two refs per run and lookups finding
    # none (bd-ib-mfl2qa, 2026-11-08). An existing dispatch-id ref at another sha (the run ended on
    # its own) is never overwritten: this pass goes to a SHA-suffixed sibling and the row says so.
    # No marker means no needs-human ref at all, never a fallback to the run ULID.
    # TEMPORARY (legacy-coordinator-agent, 2026-11-07): remove this flag and restore one behaviour
    # when bd-ib-qshcwc ships.
    if [ "$v" = VERIFIED ] && [ "${PRESERVE_WRITE_NEEDS_HUMAN:-0}" = 1 ]; then
      if [ -z "$did" ]; then v="VERIFIED+NH_NO_DISPATCH_ID"
      else
        nh=refs/heads/needs-human/$did; nold=$(git ls-remote "$repo" "$nh" | cut -f1); kept=""
        if [ -n "$nold" ] && [ "$nold" != "$sha" ]; then kept=$nold; nh=$nh-${sha:0:12}; nold=$(git ls-remote "$repo" "$nh" | cut -f1); fi
        if [ -z "$nold" ]; then
          for pa in 1 2 3 4 5; do git -C "$D" push -q "$repo" "${sha}:${nh}" 2>"$D.nh.err" && break; sleep $((pa * 7 + RANDOM % 7)); done
          for _ in 1 2 3 4 5; do nold=$(git ls-remote "$repo" "$nh" | cut -f1); [ "$nold" = "$sha" ] && break; sleep 3; done
        fi
        if [ "$nold" != "$sha" ]; then v="VERIFIED+NH_FAILED:${nh#refs/heads/}"
        elif [ -n "$kept" ]; then v="VERIFIED+NH_KEPT:${kept:0:12}+NH_SUFFIX:${nh#refs/heads/}"
        else v="VERIFIED+NH:${nh#refs/heads/}"; fi
      fi
    fi
  else v="FAILED(push sha=$sha $(tail -1 "$D.push.err" 2>/dev/null))"; fi
  printf "$out\t%s\t%s\t%s\t%s\t%s\t%s\n" "$repo" "$sha" "$ref" "$v" $(( $(date +%s)-t0 )) "$src"
done <<< "$pods"
