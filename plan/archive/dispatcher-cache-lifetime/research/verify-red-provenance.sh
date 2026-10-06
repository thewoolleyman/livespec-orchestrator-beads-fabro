#!/usr/bin/env bash
# Re-runnable audit of the bd-ib-mtuqxb Red-provenance recovery.
# One PASS/FAIL line per claim; exits with the number of failures.
# See 002-red-provenance-recovery-2026-10-06.md for what each claim means.
set -u
g() { mise exec -- git "$@"; }
pass=0; fail=0
ck() { if [ "$2" = "$3" ]; then echo "PASS  $1"; pass=$((pass+1)); else echo "FAIL  $1 (got '$2' want '$3')"; fail=$((fail+1)); fi; }

ck "1 original Red preserved by ref" \
   "$(g for-each-ref refs/recovery/bd-ib-mtuqxb/original-accepted-red --format='%(objectname)')" \
   "4ffae66e98ca429d3643fc046a5399f8e9eb375d"
ck "1 replacement Red preserved by ref" \
   "$(g for-each-ref refs/recovery/bd-ib-mtuqxb/replacement-red --format='%(objectname)')" \
   "0cc08d7f008962783f94de04d14ba4148352dfcb"
ck "1 replacement candidate HEAD preserved by ref" \
   "$(g for-each-ref refs/recovery/bd-ib-mtuqxb/replacement-candidate-head --format='%(objectname)')" \
   "f3a638c19c93a2847df4978e1f7ec880ed1e2598"
ck "2 cycle-1 Green parent == original Red parent" \
   "$(g rev-parse 9fb4bce6^)" "$(g rev-parse 4ffae66e98ca429d3643fc046a5399f8e9eb375d^)"
ck "2 cycle-1 Green author date == original Red author date" \
   "$(g log -1 --format=%at 9fb4bce6)" "$(g log -1 --format=%at 4ffae66e98ca429d3643fc046a5399f8e9eb375d)"
ck "2 frozen test bytes in HEAD tree" \
   "$(g show HEAD:tests/bin/test_payload_retention_after_eviction.py | sha256sum | cut -c1-64)" \
   "fa555625773305951cfcb12308c0f3faeb3e6234b2fab451dabf71217f140644"
ck "2 frozen test bytes on disk" \
   "$(sha256sum tests/bin/test_payload_retention_after_eviction.py | cut -c1-64)" \
   "fa555625773305951cfcb12308c0f3faeb3e6234b2fab451dabf71217f140644"
ck "4 HEAD-side Red trailer names the original checksum" \
   "$(g log -1 --format=%B 9fb4bce6 | sed -n 's/^TDD-Red-Test-File-Checksum: sha256://p')" \
   "fa555625773305951cfcb12308c0f3faeb3e6234b2fab451dabf71217f140644"
ck "4 HEAD-side Red capture time is the ORIGINAL capture" \
   "$(g log -1 --format=%B 9fb4bce6 | sed -n 's/^TDD-Red-Captured-At: //p')" "2026-10-06T03:53:10Z"
ck "replacement NOT an ancestor of HEAD" \
   "$(g merge-base --is-ancestor 0cc08d7f HEAD 2>/dev/null && echo yes || echo no)" "no"
ck "replacement checksum credited nowhere" \
   "$(g log --format=%B origin/master..HEAD | grep -c 1554d168)" "0"
ck "3 harness coverage lives in a SEPARATE file" \
   "$(test -f tests/bin/test_payload_retention_harness.py && echo yes || echo no)" "yes"
for t in test_dispatch_gate_auto_normalizes_beads_native_open test_dispatch_green_closes_item_and_journals test_dispatch_default_workflow_materializes_from_repo_fabro_tree; do
  a=$(g show origin/master:tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher.py | awk -v n="def $t" '$0 ~ n {f=1} f {print} f && /^def test_/ && $0 !~ n {exit}' | sha256sum | cut -c1-16)
  b=$(awk -v n="def $t" '$0 ~ n {f=1} f {print} f && /^def test_/ && $0 !~ n {exit}' tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher.py | sha256sum | cut -c1-16)
  ck "3 Dispatcher expectation unchanged: $t" "$b" "$a"
done
for c in 082f2593:db5df3a5 b88a2997:0ba18ba3 5429ec38:22d1af29 41d62420:fc8ff8d4; do
  sha=${c%%:*}; want=${c##*:}
  ck "5 cycle $sha carries its own Red checksum $want" \
     "$(g log -1 --format=%B $sha | sed -n 's/^TDD-Red-Test-File-Checksum: sha256://p' | cut -c1-8)" "$want"
done
ck "not published: no remote ref contains HEAD" "$(g branch -r --contains HEAD 2>/dev/null | wc -l | tr -d ' ')" "0"
ck "working tree clean" "$(g status --porcelain | wc -l | tr -d ' ')" "0"
echo
echo "TOTAL: $pass passed, $fail failed"
exit $fail
