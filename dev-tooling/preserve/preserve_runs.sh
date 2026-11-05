#!/usr/bin/env bash
# Preserve live factory runs' checkouts to origin WITHOUT Fabro (bd-ib-m7lxgn workaround). See README.md.
# READ-ONLY on every fleet host: kubectl get, crictl ps/inspect, sudo find, sudo cat over ssh.
# Pushes from a local bare copy to refs/heads/preserve/run-<RUNID> on the run's own origin.
#
# usage: preserve_runs.sh [RUNID ...]     (no args = every Running pod in the factory namespace)
# output: one TSV line per run: RUNID NODE REPO HEAD_SHA REF VERIFIED SECONDS
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
want=" $* "
printf 'RUN\tNODE\tREPO\tHEAD\tREF\tVERIFIED\tSECONDS\n'
while read -r run pod node; do
  [ -n "$run" ] || continue
  if [ $# -gt 0 ] && [[ "$want" != *" $run "* ]]; then continue; fi
  t0=$(date +%s); out="$run\t$node"
  cid=$(sshn "$node" 'sudo -n k3s crictl ps --name sandbox -o json' | POD="$pod" python3 -c '
import json,sys,os
for c in json.load(sys.stdin)["containers"]:
    if c["labels"].get("io.kubernetes.pod.name")==os.environ["POD"]: print(c["id"]); break')
  [ -n "$cid" ] || { printf "$out\t-\t-\t-\tNO_CONTAINER\t%s\n" $(( $(date +%s)-t0 )); continue; }
  pid=$(sshn "$node" "sudo -n k3s crictl inspect $cid" | python3 -c 'import json,sys;print(json.load(sys.stdin)["info"]["pid"])')
  G=/proc/$pid/root/workspace/.git
  url=$(sshn "$node" "sudo -n git config --file $G/config --get remote.origin.url" 2>/dev/null)
  for _ in 1 2 3; do
    head=$(sshn "$node" "sudo -n cat $G/HEAD")
    D=$WORK/$run.git; rm -rf "$D" "$D.push.err"; mkdir -p "$D/refs/tags" "$D/refs/remotes"
    printf '[core]\n\trepositoryformatversion = 0\n\tbare = true\n' > "$D/config"
    # One find (with sizes) and ONE bulk cat, split locally by size: a per-file ssh round trip
    # took >30 min for 16 parallel runs under CI load (2026-11-05 window).
    sshn "$node" "sudo -n find $G -type f -printf '%s %P\n'" | grep -E ' (objects/|refs/heads/|HEAD$|packed-refs$)' | grep -v ' objects/info/' > "$D.sizes"
    cut -d' ' -f2- "$D.sizes" > "$D.list"
    fail=0
    (cd "$D" && sed "s#^#$G/#" "$D.list" | tr '\n' '\0' | xargs -0 -r printf '%q ' > "$D.args")
    sshn "$node" "sudo -n cat $(cat "$D.args")" | python3 -I -c '
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
  # Strip any credential the sandbox's remote carries; push with this host's own auth.
  repo=$(printf '%s' "$url" | grep -oE 'github\.com[:/][^/]+/[^/ ]+' | sed -E 's#^github\.com[:/]#https://github.com/#; s#\.git$##')
  ref=refs/heads/preserve/run-$run
  # Never move a preserve ref off its own history: if the new tip does not contain the old one, keep
  # the old ref and write this pass to a SHA-suffixed sibling instead.
  old=$(git ls-remote "$repo" "$ref" | cut -f1)
  if [ -n "$old" ] && [ "$old" != "$sha" ] && ! git -C "$D" merge-base --is-ancestor "$old" "$sha" 2>/dev/null; then
    ref=$ref-${sha:0:12}
  fi
  if [ "$fail" = 0 ] && [ -n "$sha" ] && git -C "$D" fsck --connectivity-only --no-dangling "$sha" >/dev/null 2>&1 \
     && { pushed=1; for pa in 1 2 3 4 5; do git -C "$D" push -q "$repo" "+${sha}:${ref}" 2>"$D.push.err" && { pushed=0; break; }
          # GitHub answers "[remote rejected] ... (failed)" to concurrent pushes into one repo: back off, retry.
          sleep $((pa * 7 + RANDOM % 7)); done; [ "$pushed" = 0 ]; }; then
    # GitHub can lag a just-pushed ref by a few seconds: re-read before calling it a mismatch.
    for _ in 1 2 3 4 5; do got=$(git ls-remote "$repo" "$ref" | cut -f1); [ "$got" = "$sha" ] && break; sleep 3; done
    v=$([ "$got" = "$sha" ] && echo VERIFIED || echo "MISMATCH:$got")
    # route_recovery seeds ONLY from refs/heads/needs-human/<run ULID> (coordinator, 2026-11-05):
    # write it CREATE-ONLY at the verified sha; never move an existing one (report it instead).
    if [ "$v" = VERIFIED ]; then
      nh=refs/heads/needs-human/$run; nold=$(git ls-remote "$repo" "$nh" | cut -f1)
      if [ -z "$nold" ]; then
        for pa in 1 2 3 4 5; do git -C "$D" push -q "$repo" "${sha}:${nh}" 2>"$D.nh.err" && break; sleep $((pa * 7 + RANDOM % 7)); done
        for _ in 1 2 3 4 5; do nold=$(git ls-remote "$repo" "$nh" | cut -f1); [ "$nold" = "$sha" ] && break; sleep 3; done
        [ "$nold" = "$sha" ] && v="VERIFIED+NH" || v="VERIFIED+NH_FAILED"
      elif [ "$nold" = "$sha" ]; then v="VERIFIED+NH"
      else v="VERIFIED+NH_KEPT:${nold:0:12}"; fi
    fi
  else v="FAILED(fail=$fail sha=${sha:-none} $(tail -1 "$D.push.err" 2>/dev/null))"; fi
  printf "$out\t%s\t%s\t%s\t%s\t%s\n" "$repo" "${sha:-none}" "$ref" "$v" $(( $(date +%s)-t0 ))
done <<< "$pods"
