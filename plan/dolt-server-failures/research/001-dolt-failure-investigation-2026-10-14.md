## The maintainer's statement of what done means

Start a codex astra subagent to investigate all the dolt failures, and create a new plan using orchestrator plan skill to address them.

## Definition of Done assertions derived from that statement

- Sustained ledger reads that run the Beads dependency date-format query keep succeeding on the deployed shared Dolt server build, with no strftime read-lock wait in a goroutine dump taken after the run.
- A shared Dolt server that still accepts TCP connections and serves backups while its ledger queries hang produces a delivered operator alert within five minutes and a delivered recovery signal once queries succeed.
- A shared Dolt server that cannot finish its shutdown is replaced by the committed unit and runbook within a stated bound, with diagnostics captured first.
- A dispatcher whose ledger read fails while it iterates work items keeps supervising its Fabro run and resumes journaling once the ledger answers.
- Centrally backed ledger tenants stop issuing denied backup_export registrations while the hourly central backups keep reporting every tenant synced.

# Shared Dolt ledger server failures: investigation 2026-10-14

## The maintainer's statement of what done means

"Start a codex astra subagent to investigate all the dolt failures, and create a new plan using orchestrator plan skill to address them."

## Definition of Done assertions derived from that statement

- Sustained ledger reads that run the Beads dependency date-format query keep succeeding on the deployed shared Dolt server build, with no strftime read-lock wait in a goroutine dump taken after the run.
- A shared Dolt server that still accepts TCP connections and serves backups while its ledger queries hang produces a delivered operator alert within five minutes and a delivered recovery signal once queries succeed.
- A shared Dolt server that cannot finish its shutdown is replaced by the committed unit and runbook within a stated bound, with diagnostics captured first.
- A dispatcher whose ledger read fails while it iterates work items keeps supervising its Fabro run and resumes journaling once the ledger answers.
- Centrally backed ledger tenants stop issuing denied backup_export registrations while the hourly central backups keep reporting every tenant synced.

The assertions are session-derived from the investigation below; the maintainer has not yet confirmed them.

## Provenance

Investigation by a read-only Codex gpt-6-astra session started from plan factory-configurable-model-fallback-priority (epic bd-ib-jxvgq5) at the maintainer's direction on 2026-10-14, after the 2026-10-13 fleet-wide ledger outage. Report reproduced verbatim below.

# Shared family Dolt failure investigation

Investigation: 2026-10-14 CEST, on vmi3006760. Unless explicitly marked CEST, timestamps below are UTC (CEST = UTC+2). This report records the investigation already performed in this session; it does not imply that the live system was remeasured when this file was saved.

Investigation was read-only except for this report: no service changes, signals, configuration edits, ledger write verbs, dependency installs, or test workloads. The brief explicitly permits wrapped `bd list` and `bd show`; those commands were run from the target repository root. They can themselves attempt Beads auto-backup, which the server denies (finding 6). No attempt was made to bypass that behavior or grant privileges. The originally requested repository-local report write was blocked by the primary-checkout hook and did not create a file. The user then explicitly authorized this scratch report path outside the repository.

## Findings that change the initial diagnosis

The October 13 outage did **not** recover spontaneously. The sudo journal records `systemctl restart doltdb.service` at **22:39:56**, followed by `kill -QUIT 3356894` at **22:44:17**. The new service started at **22:44:25**. These actions predate this investigation; their authorization is recorded in existing item `dolt-server-6fdarx`.

The best-supported mechanism is **a process-global date-formatting read-lock leak, followed by blocked query execution and connection exhaustion**. The existing SIGQUIT dump remains in the journal and supplies much stronger evidence than the socket count alone. Eight-hour socket timeouts and a 256-connection ceiling are aggravating configuration choices, but changing them does not repair a blocked `RWMutex.RLock`.

The earlier “September 29 outage” started on **September 15 around 22:45**, and persisted until September 29 at 02:22. The 193 restart count is a sequence of unsuccessful replacement attempts during that incident, not 193 independent Dolt crashes.

The credential wrapper's nested-call cache defect is a separate historical failure. Its fix is present in the installed wrapper; default and cache-bypass credential-length probes both returned **29** during this investigation. There is no evidence that it caused the October query deadlock.

## Scope, evidence collection, and limitations

The primary checkout was confirmed with `git config --get livespec.primaryPath` (this repository) and `git status --short --branch` (`## master...origin/master`, clean). It remained clean at the end of collection. No worktree, PR, or ledger item was created.

Sources searched:

- Entire retained `doltdb` journal: **7,379,193 lines**, from **2026-09-10 19:07:50** to the collection cutoff **2026-10-13 23:53:55**. A second streaming classification used that same cutoff. Initial unprivileged `journalctl` returned no entries plus an access warning; substantive journal reads used `sudo -n journalctl`.
- Entire available `dolt-backup.service` journal, targeted `reconcile-runs.service` windows covering September 15–29 and October 13, and sudo windows around onset and recovery.
- Live systemd unit/configuration, process identity, socket state, installed wrapper source, Dolt build metadata, and Beads source at the **installed binary's commit `6c124203e771`**, rather than the unrelated current Beads working branch.
- `/data/projects/dolt-server/{config,scripts,runbooks,plan,SPECIFICATION}`, this repository's Beads client and dispatcher sources, upgrade receipts, and `/data/projects/livespec-dev-tooling/ansible`.
- All-status, unlimited ledger listings: **103 dolt-server records** and **1,317 orchestrator records** at collection. Full records were text-searched for Dolt, backup, connection, timeout, circuit-breaker, schema, and cache terms; relevant plain `bd show` reads included comments. Large full-record terminal output was truncated, so the dolt-server inventory was repeated as a compact ID/status/title list and incident records were read individually. Counts are snapshots of a live ledger, not invariants.

Reproducible command families used (read commands, not instructions to mutate):

```sh
sudo -n journalctl -u doltdb --utc --no-pager -o short-iso
sudo -n journalctl -u doltdb --until '2026-10-13 23:53:55 UTC' --utc --no-pager -o cat
sudo -n journalctl -u doltdb --since '2026-10-13 22:44:17 UTC' --until '2026-10-13 22:44:20 UTC' -o cat --no-pager
sudo -n journalctl _COMM=sudo --since '2026-10-13 18:20 UTC' --until '2026-10-13 19:00 UTC' --utc --no-pager -o short-iso
sudo -n journalctl -u reconcile-runs.service --since '2026-09-15 20:00 UTC' --until '2026-09-29 03:00 UTC' --utc --no-pager -o short-iso
sudo -n cat /etc/doltdb/config.yaml
systemctl show doltdb -p ExecStart -p ActiveEnterTimestamp -p NRestarts -p Result
systemctl cat reconcile-runs.service reconcile-runs.timer dolt-backup.service dolt-backup.timer
cat /etc/systemd/system/doltdb.service
go version -m /usr/local/bin/dolt
git -C /data/projects/beads show 6c124203e771:internal/storage/dolt/store.go
# Run separately from each target repository root:
/data/projects/1password-env-wrapper/with-livespec-env.sh -- bd list --status all --limit 0 --json
/data/projects/1password-env-wrapper/with-livespec-env.sh -- bd show <relevant-id>
```

Journal classifications counted literal `msg=NewConnection`, `msg=ConnectionClosed`, and warning/error messages; normalized errors replaced quoted identities and numbers before grouping. Results:

| Retained-journal signature | Count |
|---|---:|
| NewConnection | 2,308,464 |
| ConnectionClosed | 2,307,955 |
| max connections reached | 77,161 |
| socket state is broken | 512 |
| Command-denied prepare errors, first rendering | 1,331,166 |
| Corresponding errno/SQLSTATE rendering | 1,331,166 |
| error running query | 84 |
| Failed with result resources | 198 |
| Failed with result timeout | 2 |
| Scheduled restart | 198 |
| Started / Stopping service | 2 / 2 |

The 509 difference between opens and closes across multiple process lifetimes is **not** a count of presently leaked sessions: retention begins mid-process, shutdowns discard state, and live calls straddle cutoffs. Two concrete periods accumulate approximately 256 unclosed handlers each. Normal days show nearly exact open/close parity: September 11 **159,259/159,259**, October 5 **120,254/120,254** (day grouping here uses embedded CEST dates). That is roughly 1–2 opens/second on those days, mostly churn, not that many concurrent clients.

Absence scope: the retained Dolt-unit journal contained **zero literal `panic:`, `fatal error:`, `oom-kill`, or `Main process exited`** matches. This is not a claim that no host OOM, crash before retention, or unlogged failure ever occurred. July failures are documented history, outside this journal's retention. No current SQL process list, lock-counter memory, historical packet capture, slow-query duration inventory, current Honeycomb recipient delivery, or fresh restore test was obtained. No destructive fault reproduction was attempted. The report inventories failure classes evidenced in this scope; it cannot establish every failure in the server's lifetime.

## 1. Date-formatting lock leak → stuck queries → fleet-wide connection exhaustion

**Impact: critical; recurrent fleet-wide ledger unavailability. Still live in deployed binary.**

### Measured timeline and mechanism

October 13:

- **17:52:31**: `socket state is broken, returning error`, `connectionDb=livespec-orch-beads-fabro`, connection 1390184, opened at **17:52:21.557**. Similar warnings follow for other requests and tenants.
- **17:53:02 / 17:53:19**: two local dispatch processes finish in error. Evidence: `/data/projects/livespec-orchestrator-beads-fabro/tmp/gate-runs/20261013T171235Z-3481179/finished_at:1`, its `output.log:166`, and `tmp/gate-runs/20261013T141937Z-1151049/output.log:176`. The latter says `Error: search count issues: invalid connection (circuit breaker tripped)`.
- **18:37:03**: first `max connections reached. Clients waiting. Increase server max_connections` in the 17:40–22:40 window. Last at **22:38:45**, **325 warnings** in that window.
- 17:40–22:40: **2,722 opens, 2,467 closes**, net **255**. In the 17:40–18:00 portion, 759/685; 18:00–19:00, 600/418. Later hours mostly return to parity for newly accepted/closed connections while old handlers remain stuck.
- **22:44:17**: existing SIGQUIT dump of PID 3356894 contains **658 goroutines**: **122 `sync.RWMutex.RLock`**, **124 `chan send`**, **374 `sync.WaitGroup.Wait`**, plus background runtime/service workers. The strftime wait ages are **248–291 minutes**. No `sync.(*RWMutex).Lock(` frame occurs in that dump.

Representative stack evidence, all from that timestamp:

```text
github.com/lestrrat-go/strftime.(*specificationSet).Lookup
  github.com/lestrrat-go/strftime@v1.0.4/specifications.go:122
github.com/lestrrat-go/strftime.compile
  github.com/lestrrat-go/strftime@v1.0.4/strftime.go:63
github.com/dolthub/go-mysql-server/sql/expression/function.formatDate
  .../sql/expression/function/date_format.go:243

github.com/dolthub/go-mysql-server/sql/rowexec.(*groupByGroupingIter).compute.func1
  .../sql/rowexec/agg.go:184  [chan send]
github.com/dolthub/go-mysql-server/server.(*Handler).resultForDefaultIter
  .../server/handler.go:789  [errgroup Wait]
```

The goroutine census was obtained by splitting the existing journal dump on `goroutine <number>` and classifying each header's bracketed state; the 122 strftime-containing stacks supplied the wait-age range. No signal was sent to obtain these results.

`go version -m /usr/local/bin/dolt` reports Go **1.26.2**, `go-mysql-server v0.20.1-0.20260605175459-433dbaebc97f`, and **strftime v1.0.4**. `dolt version` reports **2.1.4**. Existing incident item **dolt-server-6fdarx** identifies the v1.0.4 bug: `Lookup` acquires `RLock` and defers another **RLock**, rather than `RUnlock`. Independently inspected local v1.0.6 source retains exactly this bug at `/home/ubuntu/go/pkg/mod/github.com/lestrrat-go/strftime@v1.0.6/specifications.go:120–124`; cached v1.2.0 has `defer ds.lock.RUnlock()` at `/home/ubuntu/go/pkg/mod/github.com/lestrrat-go/strftime@v1.2.0/specifications.go:127–130`. The exact v1.0.4 source was not available in the inspected module cache, and binary disassembly failed with `no symbol section`; the exact old-source statement therefore relies on the existing investigation, reinforced by installed build metadata and matching blocked stacks.

The installed Go runtime source, `/home/ubuntu/.local/share/mise/installs/go/1.26.2/src/sync/rwmutex.go:72`, parks when the signed reader count becomes negative. **Correction to prior art:** with no writer, signed int32 overflow occurs around **2^31 leaked increments**, or **2^30 double-acquiring lookups**; `rwmutexMaxReaders = 1<<30` is the writer offset, not the no-writer overflow boundary. The counter was not read from the dead process, so overflow is a strongly supported mechanism, not a measured counter value.

The relevant Beads query is real: `/data/projects/beads` at `6c124203e771`, `internal/storage/sqlbuild/counts.go:12–19`, formats dependency timestamps with `DATE_FORMAT` inside `JSON_OBJECT`; lines 89–93 aggregate it with `JSON_ARRAYAGG`. The matching engine's `date_format.go:242–249` compiles a formatter for each evaluation. Thus cumulative ledger scans steadily consume the leaked lock count. Time to recurrence depends on read volume and dependency rows, not a guaranteed two-week clock.

Cancellation then cannot unwind ordinary blocking locks. Matching cached engine source under `/home/ubuntu/go/pkg/mod/github.com/dolthub/go-mysql-server@v0.20.1-0.20260605175459-433dbaebc97f/`, `sql/rowexec/agg.go:184`, sends a row without a cancellation select; `server/handler.go:785–789` waits for row workers/iterator close. This explains why closing client sockets does not free all server handlers. The brief's six TCP sockets cannot by itself prove 250 idle sessions: TCP excludes Unix backup sessions and socket state differs from server handler state. The dump and open/close delta establish blocked execution much more directly.

Live `/etc/doltdb/config.yaml`, read through sudo, confirms `max_connections: 256`, `read_timeout_millis: 28800000`, and `write_timeout_millis: 28800000`, alongside TCP 127.0.0.1:3307 and socket `/var/lib/doltdb/dolt.sock`. These are socket I/O settings, not proof of an eight-hour bound on arbitrary query goroutines.

**Earlier recurrence:** September 15 **22:45:05** is the first broken-socket warning in the inspected 21:00–02:00 window, for `livespec-console-beads-fabro`, opened 22:44:55. First max-connection warning in retained classification: **23:32:32**. Reconciliation first logged a timeout at **22:46:19**, then 143–144 timeout-bearing lines per UTC day September 16–28. September 29 recovery is **02:22:38**, about **13 days 3h 37m** after onset. This corroborates the correction comment on **dolt-server-63etnh**. There is no September goroutine dump in the evidence examined, so attributing that incident to the identical strftime defect remains an inference from matching signatures and recurrence.

The retained journal also records a September 15 **23:32:09** connection checker failure, `more than one socket found for inode`, for connection 1971498, followed at September 16 **07:31:59** by `connection timeout`, exactly eight hours after that connection opened. This is an additional observed cleanup/diagnostic anomaly. It is not established as the primary cause: widespread query failure started about 47 minutes earlier, and this single timeout did not end the outage. It belongs in cancellation/socket-checker regression investigation rather than a separate unsupported root-cause claim.

**Recommended fix:** extend existing **dolt-server-6fdarx** with a verified Dolt dependency upgrade, or narrowly patched build, that releases this read lock, plus cancellation/load regression coverage on disposable databases. Verify the candidate binary's build dependencies and actual source; do not assume a higher Dolt version fixes it. Validate real Beads list/show/transaction and backup/restore compatibility before fleet rollout. Raising `max_connections` only delays saturation; lowering socket timeouts does not unblock `RLock`. A bounded preemptive restart can only be an interim mitigation after recovery is made reliable and its consistency policy is approved. Permanent scheduled restarts are not the root fix.

## 2. Hung shutdown makes ordinary restart unable to recover

**Impact: critical recovery failure affecting every tenant. Still configured.**

Live unit and `/data/projects/dolt-server/config/doltdb.service.template:87–91` specify `KillSignal=SIGTERM`, `SendSIGKILL=no`, `TimeoutStopSec=120`, `Restart=on-failure`, `RestartSec=5`. Systemd confirms `KillMode=control-group` and `SendSIGKILL=no`.

October 13 journal:

```text
22:39:56 Stopping doltdb.service
22:41:57 State 'stop-sigterm' timed out. Skipping SIGKILL.
22:43:57 State 'final-sigterm' timed out. Skipping SIGKILL. Entering failed mode.
22:43:57 Failed with result 'timeout'.
22:43:57 Unit process 3356894 (dolt) remains running after unit stopped.
22:43:57 Will not start SendSIGKILL=no service ... while processes exist
22:43:57 Failed with result 'resources'.
22:44:17 SIGQUIT: quit
22:44:23 Scheduled restart job, restart counter is at 5.
22:44:25 Started doltdb.service
```

The dump shows shutdown in `SessionManager.WaitForClosedConnections` (`server/context.go:93`), waiting behind stuck query handlers. This is a shutdown dependency on work that cannot finish, not ignored signal delivery: the server began shutdown but could not complete it.

September evidence further corrects the initial ledger prose: sudo records restart **02:01:46**, `kill -9 2808509` **02:22:31**; journal records new service **02:22:38**. The item's original 04:08 CEST recovery estimate is inaccurate; use the journal's 04:22 CEST. There were **193** scheduled restart attempts then and **5** in October, with 198 resource failures and two timeout failures across retention. At collection, `systemctl show` reported the new process **1814707**, start **2026-10-14 00:44:23 CEST**, active **00:44:25 CEST**, and `NRestarts=5`.

**Prior art:** **dolt-server-63etnh**, **dolt-server-6fdarx**. **Constraint:** `/data/projects/dolt-server/SPECIFICATION/constraints.md:101–105` explicitly mandates `SendSIGKILL=no` and prohibits hard kills. The implementation presently follows that policy; changing only the unit would violate the governed contract.

**Recommended fix:** revise that policy to define bounded graceful shutdown, capture diagnostics, and a controlled final escalation with demonstrated crash-recovery and restore behavior on an isolated copy. Then implement and test the unit/runbook together. Preserve the intent of giving Dolt time to flush, but avoid an indefinitely unrecoverable failed unit. A standby offers another recovery route but is deferred by maintainer ruling under **dolt-server-u193o8**; this report does not override that priority. Merely increasing TimeoutStopSec or adding retries cannot resolve an immortal handler.

## 3. Monitoring declares success for a live process while ledger queries are dead

**Impact: critical duration multiplier; allowed a roughly thirteen-day ledger outage.**

Reconciliation evidence was independently counted over September 15 20:00 through September 29 03:00: **1,893 timeout-bearing log lines** (18 on September 15, 143–144/day September 16–28, 12 on September 29), with successful `reconciled` output after recovery. Counts are log lines, not necessarily unique attempts. October 13 has successful reconciliation at **17:43:23**, errors at **17:53:28** and later ten-minute ticks.

Yet hourly backups on October 13 completed **14/14** at **18:02:31, 19:02:36, 20:02:41, 21:03:11, 22:01:51**, during the ledger outage. Whole retained backup journal classification found **795** `all syncs succeeded (14/14)` lines, one signal failure at September 29 **02:01:46**, and dependency failure at **02:05:46** during attempted recovery. Backup procedures can work through the Unix socket without exercising the affected list/date-format execution path; this also explains why TCP exhaustion is not proof that every SQL operation stopped.

`/data/projects/dolt-server/scripts/assert-listeners.sh:38–51` checks only `ss` listeners, at startup. Its intentionally nonfatal behavior is correct for partial transport failure. `OnFailure` triggers when the service fails, not while its userspace queries hang. The root `/etc/systemd/system/reconcile-runs.service` has `Restart=no` and no `OnFailure` directive in its complete inspected contents. Its timer is ten-minute `OnUnitActiveSec`, with one pass bounded by 600 seconds; it is not a ledger-health alarm.

**Prior art:** the September correction comment and acceptance criteria of **dolt-server-63etnh**; July alerting postmortem below. **Recommended fix:** a small, deadline-bounded synthetic probe with an independent alert path, exercising authentication and a representative dependency/date-format query in addition to `SELECT 1`, plus client latency/error metrics, server session/handler counts, and saturation alerts. A simple TCP or `SELECT 1` check alone can miss the October selective failure. Verify actual alert delivery and recovery notifications, not just event emission. Repeated reconciliation failures should also alert or contribute to an explicit health signal. Do not make a missing backup socket fail the entire database service.

## 4. Client retry and dispatcher behavior turns a read failure into lost supervision

**Impact: high; dispatches outlive the processes responsible for their completion. Still present in inspected source.**

**bd-ib-zlkjm4** records two October 13 dispatcher deaths at the `for item in items` loop, leaving Fabro runs `01M4V476JTEN` and `01M4V3RRRMZF` running on hp. Gate logs cited in finding 1 independently confirm timeout/error exits. Duplicate records **bd-ib-ob6bcd** and **bd-ib-nk7yc6** also exist; consolidate rather than file another duplicate. Remote run status was not rechecked in this read-only server investigation.

The cause is visible at `/data/projects/livespec-orchestrator-beads-fabro/.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_io_fabro_launcher.py:313–324`: `try` wraps creation of `read_work_items(...)`, but iteration is outside the handler. The generator performs the failing SQL-backed read during iteration. The intended exception handling therefore does not protect the watch loop.

Beads mechanics, from `/data/projects/beads` source at installed commit `6c124203e771`:

- `internal/storage/dolt/store.go:292–299`: pool defaults **10 open, 5 idle, 1h lifetime, 20s idle lifetime**; applied at 1376–1405. A maximum is not a preallocation of ten live connections.
- Line 1313: normal client read timeout **10s**; 1667 onward closes the database through `CloseWithTimeout`. Line 1432 defers closure of the separate initialization connection. The Python shell client starts a new `bd` subprocess per operation; it does not retain a Python SQL pool.
- `internal/storage/dolt/circuit.go:24–41`: **5 failures / 60s**, **5s cooldown**, **5min stale-state TTL**; scoped per **host:port:database** (55–58). A tenant's circuit does not inherently trip every other tenant's breaker.
- `circuit.go:123–148`: cooldown recovery accepts a TCP probe. A listening but query-dead server passes that test, weakening suppression and allowing more failed scans.
- `store.go:1494–1508`: `database ... not available after CREATE DATABASE` is the error from a final ping retry, even if the database already existed and the guarded CREATE branch at 1466 was never entered. The text is **not evidence that a tenant vanished or was newly created**.
- Orchestrator `effects/_beads_client_shell.py:145–151` and 209–215 use subprocesses with no explicit timeout; error mapping at 242–250 recognizes connection-refused/cannot-connect but sends i/o-timeout/invalid-connection through generic `BeadsCommandError`.

**Recommended fix:** complete the existing watch-loop item with iteration inside the protected region, tests that inject failure during iteration, and continuation on the same Fabro run. Add bounded, jittered read retries and truthful health/error classification without blindly replaying uncertain writes. Improve Beads circuit recovery to prove query health or retain backoff until a real request succeeds. Small pool limits and fewer repeated scans can reduce amplification, but neither repairs the server lock leak.

### Who was opening connections

The sudo journal, October 13 **18:20–19:00**, contains **95 wrapper command invocations**: **91** from this repository, **2** from livespec-dev-tooling, **1** each from dolt-server and livespec-overseer. Commands explicitly naming bd: **82 list, 4 show, 1 comments**; eight other wrapped commands. At **18:37**, four wrapper calls; peak in this window five/minute. These are wrapper calls, not all SQL connections: children of an already wrapped drive can execute bd without another sudo entry, and backup jobs use a different credential path. The sudo journal is not a complete per-query audit and cannot assign every connection ID to a caller.

The root reconcile timer opens the ledger every ten minutes through the wrapper. Multiple long-running `drive.py` processes were observed under wrapped launchers during collection. Janitor/nested wrapper traffic historically contributes both load and the credential-cache failure below. The inspected client's tenant checks are already memoized: `effects/_beads_client_shell.py:33–64` describes process-local and 300-second cross-process verification caches. Prior **bd-ib-xt2ony** (closed) measured obsolete config-get amplification at **25,593/40,129 calls/day (64%)**. Do not propose that already-shipped memoization as a new fix or use those historical percentages as current traffic measurements.

## 5. Credential cache poisoning produced fleet authentication refusal; installed fix now present

**Impact: formerly fleet-wide for callers sharing a credential-wrapper cache; distinct from a Dolt hang.**

Historical signature in this repository's AGENTS.md: October 1 **01:03–01:10**, multiple tenants returned **Error 1045 Access denied**; default wrapper injected zero bytes of `BEADS_DOLT_PASSWORD`, cache-bypass injected 29. The AGENTS entry does not explicitly attach a timezone to that historical window. The cache stored a delta against a caller already carrying secrets, then reused that empty delta for a bare caller for up to 300 seconds. No SQL connection pool or server restart is needed to explain it.

Current evidence: both repository wrapper and `/usr/local/bin/with-livespec-env.sh:479–487` fingerprint the exact caller baseline; line **546** includes `caller-v1` and the hash in the cache key. Wrapper repository commit **486d866**, committed **2026-10-06 00:39:29Z**, is titled `fix: bind credential cache diffs to their caller baseline`.

Read-only length probes run in this investigation:

```sh
/data/projects/1password-env-wrapper/with-livespec-env.sh -- sh -c 'printenv BEADS_DOLT_PASSWORD | wc -c'
# 29
OP_ENV_WRAPPER_CACHE_TTL=0 /data/projects/1password-env-wrapper/with-livespec-env.sh -- sh -c 'printenv BEADS_DOLT_PASSWORD | wc -c'
# 29
```

This establishes that the defect is **addressed in installed code and was not reproducing at probe time**, not that every long-running process, other wrapper, or possible cache anomaly is fixed. Retained journal includes authentication failures (e.g. 197 for overseer, 20 for this tenant), but those messages alone do not distinguish absent credentials, wrong wrapper, deliberate negative tests, and stale cache. No secret values were printed by the probes.

**Prior art:** wrapper issue **#17** referenced in AGENTS.md, fixed commit above. **Recommended fix:** retain the baseline-bound implementation, verify deployment and nested-to-bare regression coverage across wrappers, and update stale operational guidance through its normal owner. Do not rotate credentials, touch keyrings, or make TTL=0 a standing bypass on the strength of old evidence. This class has no demonstrated causal relation to October 13 date-formatting lock exhaustion.

## 6. Tenant auto-backup attempts are denied; massive log noise is not loss of central backups

**Impact: medium ongoing overhead/noise, potentially misleading backup diagnosis across the fleet.**

Live `bd show` returned success plus `Warning: auto-backup failed: register backup remote: add backup backup_export: Error 1105 ... command denied` in this investigation. Retained server logs contain **2,662,332** prepare-error renderings of permission denial, generally `CALL DOLT_BACKUP('rm', ?)` and `('add', ?, ?)`. They are duplicate renderings/attempts, not 2.66 million lost ledger writes. Examples occur at the retention start September 10 **19:07:50** and October 13 **22:45:23** after recovery, demonstrating that these denials are not unique to the outage.

The fleet's tenant accounts deliberately lack the global privilege required by the pinned Dolt backup procedure. Central `/data/projects/dolt-server/scripts/backup-sync.sh:61–97` uses the dedicated backup principal and the `s3` remote; observed hourly 14/14 success is separate from failed `backup_export` registration.

**Prior art and ruling:** **bd-ib-rxf** (backlog), especially its August 19/22 correction comments, explicitly reject fixing this by broadening tenant grants; central backups already exist. **bd-ib-4py4** (closed) addressed discarded stderr on zero exit. **dolt-server-mm-kuq1mw** and **dolt-server-bhqotn** (closed) record the dedicated SUPER backup principal rather than upgrading ordinary ops/tenant accounts. The stale July note claiming reads never emit this warning is refuted by current successful `bd show` output and later comments. Some other comments repeat the obsolete grant proposal; the privilege boundary and central-backup evidence resolve that disagreement.

**Recommended fix:** disable the inappropriate per-client auto-backup lane for centrally managed tenants, or make it explicitly capability-aware and avoid repeated attempts; retain central backup coverage and stderr visibility. Do not grant tenants SUPER, and do not claim the central S3 chain is broken from this warning. Verify per-tenant central coverage and restorability independently. Reducing log noise should also preserve longer useful journal history and make novel errors visible.

## 7. Backup transport, provisioning, alert delivery, and recovery assurance failures

**Impact: high durability exposure across tenants, even when ledger reads remain healthy. Historical fixes exist; residual assurance gaps remain.**

These are separate from connection exhaustion and, where dated in July, outside the retained journal window:

1. **Stale Unix socket / half-listening server, July 9–21.** `/data/projects/dolt-server/config/doltdb.service.template:25–45` records that Dolt warns and starts TCP-only when the socket path is occupied; the unit stays active while socket-based backups fail. Historical cost: eleven days of backups. Live unit has preflight socket cleanup and nonfatal dual-listener assertion. **Recommend retaining and testing these protections**, not making a socket-only defect shut down all TCP ledgers. Prior-art pointer: `vps-info plan/dolt-reboot-safety/` in the template; historical record in `runbooks/alerting.md:199`. No dedicated matching July outage ledger item was identified in the two inventories searched.
2. **Missing `s3` remote on a newly created tenant.** `runbooks/backups.md:226–261` documents `ERROR 1105 ... backup 's3' not found`: onboarding skipped registration without loaded nonsecret target settings, and backup had no defense against concurrent creation. Fixed by `load_backup_env` and `ensure_backup_remote` self-healing. **dolt-server-1w4** is closed (PR #44). **Recommend preserving fail-closed coverage checks and concurrent-onboarding regression proof**, not treating that historical failure as currently reproduced. The cited runbook does not date each original failure; this investigation cannot assign exact timestamps before retention.
3. **Notification delivery silently removed.** `runbooks/alerting.md:199–225` records **265 backup failures and no notifications over eleven days**. Triggers fired but had no recipients after a **June 22 03:48** edit (timezone unspecified in that source). The same edit fixed an undersized dead-man window; silence was mistaken for health. Fleet Ansible has `roles/honeycomb_trigger_recipients_check`, not a doltdb-named role. **Recommend delivery-level synthetic checks plus recipient invariants and a dead-man window longer than expected backup gaps**. Current Honeycomb delivery was not queried and no test message was sent.
4. **Config rendering could remove AWS credential injection.** Unit template lines 74–82 document July 21 drift: re-rendering an older template would remove the live AWS EnvironmentFile. The current template keeps it enabled with an optional-file prefix. This was a detected configuration hazard, not a separately proven outage in the retained journal. **Recommend rendered-versus-live configuration checks** as part of deployment. The template itself is the inspected prior-art record; no separate ledger owner was identified in the two inventories.
5. **Restore assurance and stale prefixes.** **dolt-server-b6e** remains ready: weekly restore compliance lacks a durable checkable record. **dolt-server-3iv** remains ready: four stale S3 prefixes need classification. Orchestrator **bd-ib-6oikux** tracks the same deferred hygiene. Closed **dolt-server-ckue2g** records an earlier scratch restore, which does not prove ongoing weekly compliance. **Recommend a scheduled isolated restore with a retained parity receipt**, and explicit reconciliation of tenant inventory to backup inventory. This is an assurance gap, not measured corruption or data loss.

`rg -n doltdb /data/projects/livespec-dev-tooling/ansible` returned no matches across that tree. The live unit's source is the dolt-server repository's config/scripts. This is a scoped absence of a doltdb-named role/reference, not proof no deployment tooling exists elsewhere.

## 8. Beads schema auto-migration can strand tenants independently of server health

**Impact: potentially fleet-wide compatibility outage; current evidence is historical hazard and controlled upgrade history, not October's cause.**

AGENTS.md and **bd-ib-3kolea.4** document accidental v1.2.0/v1.2.1 releases advancing stores to schema v65, while the tested line expects v53. A read-like open can migrate; `bd migrate --dry-run` is not a safe preview. Current public guard `/usr/local/bin/bd:106,683` delegates to bd-real; wrapped `bd version` returned **1.2.2 (6c124203e: HEAD@6c124203e771)**. The private delegate was not invoked directly.

`/data/projects/livespec-orchestrator-beads-fabro/plan/archive/beads-v1-1-2-upgrade/research/cutover-receipt-2026-08-31.md:47,112–135` records an actual missed root reconcile timer opening this tenant at **02:50:00Z**, automatically advancing it during a planned migration. Receipt line 18 records all 14 tenants ending at v53. This proves the incomplete fleet-quiescence mechanism; it does not prove a v65 incident on this host. Current schema was not directly queried during this investigation.

**Recommended fix:** retain the public guard and approved binary pin, inspect schemas through an authorized non-migrating administrative read before upgrades, inventory both system and user timers and every client host, and validate migrations/rollback on restored isolated copies. Never probe a live tenant with an unapproved binary. Upgrade the Dolt server dependency without casually changing Beads/schema versions as part of the same fix.

## 9. Transaction conflicts and smaller query failures are real but distinct from a server wedge

**Impact: generally per-operation or per-tenant, rather than demonstrated fleet-wide unavailability.**

The **84** `error running query` messages were separately classified by their `error=` field over September 29 02:22 through collection:

| Error | Count | First observed in that scan (UTC) |
|---|---:|---|
| serialization failure: this transaction conflicts with a committed transaction from another client, try restarting transaction. | 45 | October 12 06:37:06 |
| nothing to commit | 36 | September 29 02:42:40 |
| connection was closed | 3 | October 12 04:32:38 |

Example serialization failure was on `livespec-orch-beads-fabro`, connection 1259710; example closed connection was on `livespec-overseer`, connection 1252427, opened about ten seconds before the warning. The closed-connection sample is compatible with client timeout/cancellation but does not establish its cause. `nothing to commit` describes a commit operation with no new commit to make, not necessarily lost writes or an unavailable ledger.

The observed conflict message explicitly names concurrent committed transactions. Orchestrator `_beads_client.py:299–306` documents Dolt Error 1213 on the conditional close path and requires readback rather than treating an exception as proof of the winner. **bd-ib-wdl577** (closed) is related prior art for server-side epoch-token serialization. No evidence in these 84 messages ties ordinary conflicts to the global strftime lock leak; a transaction serialization failure must not be conflated with a userspace deadlock just because both are sometimes called a deadlock.

**Recommended fix:** use bounded transaction-level retry only where the operation is designed for it, read back conditional-operation outcomes, and make no-op commit handling explicit. Avoid blanket write retries after ambiguous connection loss. Extend existing concurrency coverage with actual conflicting clients on disposable stores. No separate new fleet-wide outage item is justified solely by these messages.

The full warning classification also showed startup `secure_file_priv` warnings, first in the retained sample at September 29 **02:22:36**. They describe a security configuration property, not evidence that it caused a ledger outage or was exploited; FILE privilege holders were not inventoried in this investigation.

## 10. Port 3308 is an orphaned Beads test server, not a second fleet ledger

Measured `ps`: **PID 685, PPID 1**, started **2026-10-10 06:35:40 CEST**, command `/usr/local/bin/dolt sql-server -H 127.0.0.1 -P 3308 --loglevel=warning`.

```text
readlink /proc/685/cwd
/tmp/beads-bd-tests-1939830995/bd-metrics-home-2378728596/.beads/shared-server/dolt (deleted)
cat /proc/685/cgroup
0::/user.slice/user-1000.slice/user@1000.service/tmux-spawn-e51432f2-6023-48f1-9156-0ff08495c22a.scope
```

`/data/projects/beads/cmd/bd/init_metrics_test.go:148` creates `bd-metrics-home-*` test directories. The command, deleted test-home cwd, orphan parentage, and scope identify this as a leftover test auto-started server with high confidence; the original parent command cannot be recovered from PPID 1. `ss` confirms separate listeners at 3307 and 3308. No evidence in these observations connects it to the fleet's 3307 max-connection counter, and the observed test identity does not support treating it as a failover replica.

**Impact: low direct evidence of fleet impact; process/port/resource leak. Recommended fix:** have Beads test harnesses own and reap server lifetimes on success, failure, and interruption; perform cleanup of this orphan only in a separately authorized action after checking identity. No server was stopped for this investigation. No matching fleet incident item was found in the two ledger inventories searched; Beads' own ledger was not surveyed.

## Proposed work items, ranked by fleet impact

These are proposals only. Prefer extending existing owners and reconciling duplicates; no items were filed or changed. Priorities below express this investigation's fleet-impact assessment, not edits to existing ledger priorities.

1. **P0 — Repair the deployed date-formatting lock leak (extend dolt-server-6fdarx).** Definition of Done: a pinned, verified server build uses a correct strftime read unlock and passes isolated sustained Beads dependency-query, disconnect/cancellation, and backup/restore compatibility checks before a measured fleet rollout.
2. **P0 — Detect query-dead ledgers independently of process and backup health (extend dolt-server-63etnh).** Definition of Done: a bounded representative ledger-query probe and repeated reconciliation failures produce a delivered alert within five minutes and a delivered recovery signal, including a case where TCP and backups still work.
3. **P0 — Make hung-server replacement bounded under a revised shutdown policy (coordinate both Dolt incident items).** Definition of Done: ratified shutdown rules, deployed unit, and runbook demonstrate diagnostic capture and successful replacement of a non-exiting server within a specified bound, with isolated crash-recovery/restore validation.
4. **P1 — Preserve dispatcher supervision across ledger read failure (bd-ib-zlkjm4; reconcile bd-ib-ob6bcd/bd-ib-nk7yc6 duplicates).** Definition of Done: a failure raised during generator iteration leaves the same Fabro run supervised, recovery resumes correct journaling, and regression tests cover both failing and recovering polls.
5. **P1 — Bound and measure client retry/scan amplification (Beads and orchestrator owners).** Definition of Done: a query-unhealthy but TCP-listening fixture retains effective backoff, read operations have bounded deadlines, session/latency telemetry proves cleanup after disconnect, and uncertain writes are not blindly retried.
6. **P1 — Prove central backup restorability and end-to-end alert delivery (dolt-server-b6e/dolt-server-3iv and existing alerting owner).** Definition of Done: periodic isolated restores produce retained parity receipts for the covered tenant set, stale prefixes are explicitly classified, and synthetic failure/dead-man notifications reach their configured recipients.
7. **P2 — Remove inappropriate tenant auto-backup attempts without widening grants (bd-ib-rxf).** Definition of Done: centrally backed tenants stop issuing denied backup_export registrations while central S3 coverage, restore checks, and error visibility remain demonstrably intact.
8. **P2 — Close the credential-cache documentation/deployment loop (wrapper issue #17 follow-through).** Definition of Done: installed wrappers pass nested-to-bare credential-presence tests without exposing values, and fleet instructions describe the fixed baseline-bound cache plus a scoped diagnostic for real recurrence.
9. **P2 — Preserve backup boot/provisioning protections with deployment checks (existing dolt-server backup owners).** Definition of Done: stale-socket, concurrent tenant registration, missing backup settings, and rendered credential-injection cases are detected or repaired without taking healthy TCP ledgers down.
10. **P2 — Enforce upgrade quiescence across all ledger clients (bd-ib-3kolea follow-through).** Definition of Done: upgrade preflight inventories system/user timers and client versions, demonstrates no unexpected tenant opens during an isolated rehearsal, and refuses unapproved Beads/schema combinations.
11. **P2 — Verify conflict/no-op/ambiguous-write handling at the ledger boundary (related bd-ib-wdl577).** Definition of Done: isolated concurrent-client tests demonstrate correct transaction retries, conditional-result readback, and no duplicate effects after ambiguous connection failure, with benign no-op commits distinguished from failures.
12. **P3 — Fix Beads test-server lifetime leaks (Beads owner).** Definition of Done: normal, failed, and interrupted metrics-test runs leave no orphan Dolt process or listener, and the identified 3308 orphan is dispositioned through an authorized cleanup.
