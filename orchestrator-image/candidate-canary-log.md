# Candidate-canary log

The factory-ops record of which candidate canaries have been taken. Each entry
is the trace a canary leaves behind: the fixture work-item that carried it and
the factory it was dispatched to. The runbook section
`### Taking a candidate canary` of `orchestrator-image/README.md` names the
recipe that files and dispatches one.

This file is deliberately the DULLEST deliverable in the repository. A canary
measures the engine, so the change it makes must be one that cannot fail for a
reason of its own: one appended line, in a file nothing else reads, whose format
is checkable in a sentence.

## Format

Every non-blank line below the `## Entries` heading is ONE entry beginning with
`- `. A canary's entire change is appending one such line as this file's LAST
line; no existing entry is edited, and nothing else in the repository is
touched.

The format is enforced by `marker_entry_findings` in
`livespec_orchestrator_beads_fabro.commands.take_candidate_canary`, exercised
against this committed file by the repository's own suite — so a malformed
append fails the janitor gate rather than merging quietly, and an entry that
conforms is accepted by construction rather than by nothing having looked.

## Entries

- bd-ib-tixpma seeded the candidate-canary log
