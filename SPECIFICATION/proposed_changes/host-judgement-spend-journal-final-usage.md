---
topic: host-judgement-spend-journal-final-usage
author: claude-opus-5-5
created_at: 2026-11-08T18:25:42Z
---

## Proposal: A host Claude judgement's spend journal ends with the closing result event's final usage

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State the host judgement spend journal, which no ratified clause states today, inside contracts.md's existing "Host model-judgement caller labelling" subsection, and add one scenario that exercises it. Each host model-judgement spawn whose candidate is the Claude agent MUST journal its responses under `$HOME/.claude/spend-journal/`. A header line declares `"final_usage_line": true`. When the stream emits a closing `result` event, the journal MUST end with a `result` line carrying that event's `usage` object unchanged and the `message_ids` of the journal's `assistant` lines. A process that ends without a `result` event leaves its last `assistant` line last. This holds whether the launch reads the candidate's output as it streams or after the process exits. The only new H2 heading is the scenario.

### Motivation

Work item bd-ib-st2sby (plan spec-implementation-lockstep, epic bd-ib-ax3rds) corrects the host judgement spend journal so that the Honeycomb llm-spend dataset reports true output tokens. Its Definition-of-Done preflight refused it on 2026-11-08: its References line named Scenario 280, which governs only `livespec.caller` labelling, and no ratified clause states the spend journal at all. The journal module `_host_judge_spend_journal.py` arrived in commit 5c843b30d on 2026-11-02 from a factory run with no ledger item, so its behaviour was never specified. That is the drift this plan exists to close: new behaviour gets a clause before its implementation is dispatched.

MEASURED CAUSE (2026-11-07, plan session cdae00, recorded on bd-ib-st2sby). The journal keeps only stream-json `assistant` events, whose `usage` is the pre-completion figure: `stop_reason` is null and `output_tokens` is a small placeholder. Final usage arrives only in the closing `result` event, which is discarded. Probes: haiku assistant 5 against result 1148 output tokens; sonnet assistant 8 against result 109. In the 48 hours to 2026-11-07T17:22Z, 1,413 journal-sourced llm-spend events recorded 5,743 output tokens with a maximum of 10, against an estimated true 361K to 523K, so journal-sourced spend reads about 3 to 4 percent low. The emitter that reads the journal (owned by session token-spend-analysis) relies on the header flag and the `result` line shape stated here. In particular it treats a non-assistant line carrying `started_at` as a header, which is why the `result` line MUST NOT carry that key.

PLACEMENT. The subsection already defines a host model-judgement spawn and the caller vocabulary the journal's `purpose:` name carries, so the clause extends it rather than adding a section.

SIDE OBSERVATION, not proposed here: the subsection's caller list names `drift_run`, `dod_governing_heading`, `dod_judgement_pre_admission`, `dod_judgement_pre_dispatch` and `ledger_intent_scan`, while the journal records the callers `spec_change_tier_gate` and `groom_spec_change_classification` too. The subsection requires a new spawn site to add its caller value in the same change, so those two are drift for this plan's reconciliation batch, bd-ib-76ztny.

### Proposed Changes

In `SPECIFICATION/contracts.md`, §"Bounded session waits and observable inventory" → "### Host model-judgement caller labelling", insert the following paragraphs after the paragraph that begins "The receiver allowlist MUST admit `livespec.caller` as a resource attribute" and before the line "Scenario 280 in `scenarios.md` exercises this subsection.", each separated by one blank line:

> **A host Claude judgement journals its spend, ending with its final usage.** A host judgement runs its candidate without session persistence, so the agent writes no transcript that a spend reader could consume. Each host model-judgement spawn whose resolved candidate's agent identity is `claude-acp` (a Claude candidate) MUST therefore write a spend journal: one JSON-lines file under `$HOME/.claude/spend-journal/`, named by a session id generated for the launch. Its first line MUST be a header carrying `session_id`, `name`, `cwd`, `started_at`, the first 2,000 characters of the prompt as `first_prompt`, and `"final_usage_line": true`. `name` MUST be `purpose:<caller>@<working directory name>`, with `<caller>` the spawn's `livespec.caller` value, or `host_judgement` when the spawn names none.
>
> The candidate's output is Claude's stream-json event stream: one JSON object per line, of which `assistant` events carry each response and a closing `result` event, when the process reaches it, carries the final usage. Each `assistant` event that carries a message id, a model and a `usage` object MUST be appended as one line, with a `ts` timestamp. When the candidate's stream emits a closing `result` event, the journal's last line MUST be a line of type `result`. It MUST carry that event's `usage` object unchanged, a `message_ids` array listing the message ids of the journal's `assistant` lines in order, and a `ts` timestamp, and it MUST NOT carry a `started_at` key. When the process ends without emitting a `result` event, including a candidate ended by the input bound of §"Dispatcher admission, WIP cap, and post-merge acceptance", the journal's last line MUST be its last `assistant` line. These rules MUST hold whether the launch reads the candidate's output as it streams or after the process exits. Writing the journal MUST NOT fail or alter the judgement.

Replace the line "Scenario 280 in `scenarios.md` exercises this subsection." with "Scenario 280 in `scenarios.md` exercises the caller labelling of this subsection, and Scenario <the new scenario's number> exercises its spend journal."

In `SPECIFICATION/scenarios.md`, append after the last existing scenario heading of the file, taking the next free scenario number at revise time:

## Scenario <next free number> — A host Claude judgement's spend journal ends with the closing result event's final usage

```gherkin
Feature: Host judgement spend journal final usage

  Scenario: A judgement whose Claude stream emits a result event journals its final usage last
    Given a host model judgement whose resolved candidate is the Claude agent, launched with caller drift_run
    And its stream emits assistant events with message ids msg_a and msg_b, then a result event whose usage reports 1148 output tokens
    When the judgement completes
    Then a journal under $HOME/.claude/spend-journal/ has a header line carrying "final_usage_line": true and a name beginning purpose:drift_run@
    And its assistant lines are those two events in order, each with a ts timestamp
    And its last line has type result, carries that usage object unchanged and the message_ids array [msg_a, msg_b], and carries no started_at key

  Scenario: A judgement whose Claude process ends without a result event keeps its last assistant line last
    Given a host model judgement whose resolved candidate is the Claude agent
    And its process is ended by the input bound after one assistant event and before any result event
    When the judgement ends
    Then the journal's last line is that assistant event

  Scenario: A judgement read after its process exits writes the same final usage line
    Given a host model judgement that reads its Claude candidate's output only after the process exits
    And that output ends with a result event
    When the judgement completes
    Then its journal's last line has type result and carries that event's usage object unchanged
```

The revise that ratifies this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading, with `test` set to `"TODO"`, `work_item` set to `bd-ib-st2sby`, and a `reason` naming that item as the owner of the test.
