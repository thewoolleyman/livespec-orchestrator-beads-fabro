# Instrument-aim traps: a probe that cannot return a hit, reporting none

Moved word for word from `AGENTS.md` §"Beads runtime prerequisites" on 2026-10-30, when the maintainer
directed AGENTS.md split into a short core plus read-on-demand `.ai/` files
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Words such as "above" and "below" point into the AGENTS.md this text came from;
the sections they name now live in the `.ai/` files AGENTS.md routes to.

**An instrument that CANNOT RETURN A HIT, reporting no hits.** This is the sibling
of the sparseness trap above and it sits one level earlier: there the observation
was correct and the conclusion wrong; here THE QUERY ITSELF WAS INCAPABLE OF FINDING
THE THING, and it reported a clean negative with no error. Every instance below
returned valid output, exit 0, and a plausible answer.

The sharp form of the rule, which is what makes it usable: **a control that
establishes an instrument FUNCTIONS is not a control that establishes it is POINTED
CORRECTLY.** The second needs its own positive case — a query that SHOULD return
something, returning it. The discriminating question for aim is therefore: *what
should this query return if it is pointed correctly, and does it?*

Measured instances from 2026-08-21 and 2026-08-22:

- **An anchored regex that cannot match the real line.** Claim: "`bd update` has no
  `--description` flag, so a description cannot be edited non-interactively."
  The pattern was anchored `^\s+--(description|acceptance|notes)`; the help line
  reads `-d, --description string`, leading with the SHORT flag, so a two-dash
  anchored pattern can never match it. Three routes existed (`-d/--description`,
  `--body-file` with `-` for stdin, `--stdin`). The same shape recurred within the
  hour: a ten-repo sweep for `sorted(children)[-1]` — a PARAPHRASE reconstructed
  from a peer's prose — returned zero while two live instances existed as a
  multi-line `sorted(...)` assigned to `matches`, then `matches[-1]`.
- **A wrong-target query with a confident empty answer.** Claim: "no fabro run
  exists for either dispatch." The query was `fabro ps`, which defaults to the LOCAL
  server, while the Dispatcher submits with `--server https://hp-xubuntu…`. Both
  runs were alive on that host. The local query returned 725 rows — a large,
  healthy, entirely irrelevant population. The discriminator was not a better run
  query but PROCESS ANCESTRY: the live `fabro run` process carries `--server <host>`
  in its own cmdline, which NAMES the target instead of assuming one.
- **A PATH false-absence**, hit by two sessions independently. Claim: "fabro is not
  installed." It is; the credential wrapper does not carry it on PATH. Preserve PATH
  explicitly.
- **The most credible one, because the instrument was demonstrably healthy.** Claim,
  reached independently by two sessions: "there is no local route to a remote run's
  store, so `fabro dump` cannot rescue an interview-destroyed run." The control that
  was run was a GOOD control — `fabro ps -a` returned 726 rows, proving the binary
  works, the query shape is valid and the store is readable. It proved the instrument
  FUNCTIONED; it could not prove the instrument was AIMED at the right host. Every
  zero collected was equally consistent with "this run does not exist" and with "I am
  querying the wrong store", and nothing in the output distinguished them. Falsified
  by execution: `fabro dump <run> --server https://hp-xubuntu… -o <dir>` exported 34
  files including `stages/002-implement@1/diff.patch` at 21,949 bytes — the very
  artifact the rescue procedure is written around. Re-confirmed independently on run
  `01M0H73GQ8Y0`: `dump --server` exported 61 files, and `attach --server` reached a
  run genuinely holding a human gate, rendered its prompt and accepted an answer. The
  remedy was fully operative the whole time, and defects were filed against a
  capability that already worked.
- **Docker measured through the wrong storage root.** Claim: "Docker cannot be
  filling the factory disk." The measurements were aimed at `/var/lib/docker` and
  were CORRECT — two independent sessions saw small values (12M and 4.3G), and a
  post-cutover check on the same host saw `/var/lib/docker` at 1.8M. The population
  was wrong: on Docker 29 the image bytes live in `/var/lib/containerd`, which
  measured 28G on the same host. A small `/var/lib/docker` reading therefore
  exonerates the wrong tree while the factory is out of room. Do not rely on
  `docker system df` on a large store; it can hang. A whole-tree `du` can time out
  too. Bisect per-subtree under `/var/lib/containerd`, and treat the subtree that
  never returns as the finding rather than as an absence.
- **A rebase-merged PR read through its series tip.** This repo rebase-merges, so
  the merge SHA is the LAST COMMIT OF THE REBASED SERIES, not a merge commit that
  contains the series. `git show <merge-sha>` therefore renders exactly one commit
  and SILENTLY OMITS the rest of the PR — no warning, no indication that earlier
  commits exist. Measured 2026-08-22 on PR #1736: the fix for `bd-ib-2os2` landed
  in the FIRST commit, `3377f7d4` (shell-aware command-position matching), while
  the PR tip `6c776441` was unrelated hardening. A `git show 6c77644...` read
  concluded "the merged diff does not address the filed defect at all", a false
  negative that would reopen settled work and re-dispatch a closed item. The
  discriminator for "what does this PR contain?" is the PR's commit list
  (`gh pr view <n> --json commits`), but that is the WRONG instrument for "what
  actually landed on master?" Verifying a landing by commit SHA is verifying the
  wrong identity: under rebase-merge, PR/branch SHAs do not survive. Measured
  2026-08-22 on PR #1776: `git branch -r --contains ac7ebb0f` returned
  `origin/master` for the merge-sha control, while the same command returned ZERO
  for each branch SHA `90d094df`, `eaaa24ab`, `10f0b4a0`, and `60a16fb7`. Master
  carried three `fix:` commits under new hashes (`ac7ebb0f`, `36026f97`,
  `89997f93`), and the four `fabro(<run-id>): <stage> (succeeded)`
  stage-checkpoint commits were absent entirely. So a PR's commit count is not
  master's commit count either. Use the PR commit list only to read what the PR
  contains. To verify the landing, use a CONTENT check that survives a rebase,
  such as `git show origin/master:<path> | grep -c <token>`, or a master-side
  range read such as `git log <base>..origin/master`. This was caught by a peer
  session on the report that landed the original trap entry: the author had also
  run a "positive check on the substance rather than the shape", and that content
  check was the load-bearing proof.
- **A killed run presumed to have lost work that it had already published.** A
  Fabro run that parks on a human gate and is later killed leaves an item stranded.
  The natural conclusion — "the sandbox is gone, so the work is gone" — is right
  only when the run had not yet published, and nothing in the stranded item
  distinguishes the two. Measured 2026-08-22 on `bd-ib-2os2`: the claim-release
  comment recorded "expected to start from scratch. Any unpublished work in the
  dead sandbox is gone." Run `01M0KXYZRWXNF7SSRN2KHJ57DK` had in fact published PR
  #1736 — implement, janitor, review and disposition stages all `(succeeded)` —
  before parking, and re-dispatch found and merged the PR in five minutes. The
  discriminator is a forge search for a PR carrying the run id before
  re-dispatching a killed or stranded run; the run id is stamped into its commits.
  `bd-ib-6o6h` is the genuine-loss counterpart, `bd-ib-2os2` is the survived case,
  and one query separates them.
- **A mutation that never applied, reporting as a surviving mutant.** This belongs
  here because it is the same "query incapable of returning the hit" failure in the
  test harness itself. While mutation-checking `storage-reclaim.test.sh` on
  2026-08-22, `sed` patterns silently matched nothing, so three of five mutants ran
  against an unmodified script and reported `50 passed, 0 failed` — exactly the
  same surface a genuinely surviving mutant would produce. The discriminator is
  not the suite result; the harness must prove the mutation landed, for example by
  appending a `grep -c` or equivalent content check that would be nonzero only
  after the edit. The same rule applies to guard tests: isolate the arm being
  guarded. A "live process in a subdirectory" case that also has a live process at
  the worktree root still passes after the subdirectory arm is deleted.
- **A hand probe filtered out the state it was trying to disprove.** While checking
  a claim that a blocked Fabro run was never reaped, `fabro ps -a | grep -iE
  "blocked|RUN ID"` returned no cited run and produced the wrong report that the
  run was "no longer listed on hp at all". The run had already reached `failed`, so
  a filter on `blocked` could never return it; the proper measurement found it in
  `ps -a` with a terminal status at `240m00s`. The mirror failure happened in the
  same audit: probing this item's text for the retracted phrase "never reaped"
  found a real hit inside the retraction narrative and nearly turned a quotation
  into a false correction. A count is not a verdict in either direction. Absence
  does not prove the claim is gone, and presence does not prove it is asserted.
  Discriminate by position and context: for panes, key on the tail region where a
  live picker renders its footer; for prose, read the surrounding sentence to see
  whether the hit is a claim or a quotation. This is the same family as
  `livespec-overseer`'s `overseer-i6eu2k` shipped-detector defect, but these two
  were ad-hoc verification lapses with no code to fix, so cite the family rather
  than widening that item.
- **An instrument so slow that its own observation changed the answer.** This is
  adjacent to wrong-population probes but not identical: the instrument was aimed
  at the right population, and that population changed while the instrument was
  looking. Measured 2026-08-22, the storage-reclamation liveness guard forked
  `readlink` once per process per worktree: 1,727 process entries, 27.5 seconds for
  one call, 608 worktrees, over one million forks, and a projected 4.6-hour scan.
  The scan outlived the fixture's own sleep, so the subject exited before the
  answer arrived. The discriminator is: does this measurement take long enough for
  the subject to change underneath it?
- **Partial output from a still-running job is not an outcome.** This is folded
  here because it is another healthy-looking observation aimed at the wrong
  question. During the same storage-reclamation dry run, output stopped after the
  LEG A header with `sort: write failed: Broken pipe`; the first conclusion was
  that LEG A had died, and the second was that the script was fine. Both were
  wrong. The job was still running, 25 minutes into the 4.6-hour scan above, and
  there was a real guard defect, just not the broken-pipe line. The discriminators
  are separate: a process that has not exited has not reported its outcome, so
  "output stopped" and "process died" are different claims; and the broken pipe was
  cosmetic for `find | sort -rn | head -1`, because `head` exits first and `sort`
  takes EPIPE. That pipeline was verified over 60 real worktrees, 60/60 valid.

- **A forge search whose query syntax cannot match the title it was given.**
  `gh pr list --search "chore(deps): bump livespec-dev-tooling"` returned ZERO
  rows in every one of nine fleet repos on 2026-09-10, exit 0, no warning — while
  twenty-three such pull requests existed in this repo alone. GitHub search treats
  `(` and `)` as grouping, so a conventional-commit scope turns the query into
  one that matches nothing; the same string without the parentheses plus
  `in:title`, or a `--json number,title --jq 'select(.title|test(...))'` filter,
  returned every PR. The survey had a stated scope (nine named repos) and a
  healthy instrument (`gh` worked), and was still worthless. The positive
  control is the one this catalogue already prescribes: search for a PR you KNOW
  exists before believing an empty survey.

- **A factory-readiness wait aimed at the web console, then at the API.**
  Measured 2026-10-12 on hp. After an attended `fabro-server` restart, a wait
  for `curl …:32276/runs` to return 200 burned its whole two-hour deadline.
  `/runs` and `/login` are the web console's routes and returned 404 throughout,
  while `/api/v1/runs` answered 200 and `fabro ps --server` worked from the
  second minute after the restart. The second layer was also wrong: an API that
  answers does not mean a factory that accepts work. Docker and containerd had
  been stopped for a storage move, so every run on hp failed at 0 ms with
  "Failed to inspect Docker image … Connection refused" (category
  `transient_infra`). The positive control is a run that EXECUTES. Wait for
  `systemctl is-active docker` to report `active` on the factory host AND for
  `fabro ps --server <factory>` to list a run in progress. Read
  `fabro inspect --server <factory> <run>` at
  `conclusion.failure.detail.causes` for any 0 ms failure. Put an ssh probe that
  runs in a loop into a script file, because the fleet host guard refuses an
  inline loop it cannot classify.

**The existing "state the scope you searched" rule is necessary and NOT sufficient**
— see "Verification discipline (repo-additive)" below, whose Rule 1 this extends. In
the anchored-regex instance the scope was stated and correct (ten repos, every `.py`,
exclusions named) and the sweep was still worthless, because the PATTERN could not
match. State the scope AND establish that the instrument could have returned a hit
within it.

Why this one is worth re-deriving before acting: an "I checked and it is IMPOSSIBLE"
conclusion FORECLOSES THE ACTION, and nothing downstream ever re-tests it. A wrong
measurement gets contradicted by the next reader; a false impossibility just quietly
stops being examined. In the anchored-regex instance the fix was one command away, and
the false conclusion was passed to two other sessions as advice before being caught.

**Classify a flaky safety test by the direction it fails before dismissing it as
noise.** This is its own entry because the actionable rule is about deletion risk,
not search shape. Measured 2026-08-22, `storage-reclaim.test.sh`'s liveness case
failed 2 runs in 3 on a load-71 box and looked like a fixture race. It was the guard:
`readlink /proc/<pid>/cwd` printed the target while `worktree_is_live` returned
not-live, 5 of 5 attempts. A liveness guard failing toward NOT-LIVE permits a
deletion. That is the expensive direction, and environmental noise only made the
wrong guard look like a flaky test.

**When two honest measurements disagree, the difference is the data.** This is not
folded into the wrong-population catalogue because neither instrument is the
villain; they answered different questions correctly. Measured 2026-08-22 on the
factory host, `du -xsm /var/lib/docker` returned 3M while `du -sm /var/lib/docker`
returned 2055M. Read as a 700x under-report, that would be a false defect against
the size helper. The divergence localized to one subdirectory on another device,
and `df` settled the intended reclamation question: `-x` is correct when asking
"how many bytes does deleting this tree free on this filesystem", not "how large is
this mounted tree including other filesystems". Before believing either number,
locate the difference with an independent instrument such as `df`/`findmnt`.
