# Stage Context Audit: Work-Item Field Delivery

This audit records whether the current Fabro implementation workflow delivers each work-item context field to each stage. It is research evidence for follow-up slices; it is not a specification change.

Legend: `yes` means the field is present in the stage brief through `{{ goal }}` or prior-stage context; `partial` means the field is inferable or present only through a different mechanism; `no` means the stage does not currently receive it.

## Field Inventory

| Field | Source in current brief | Delivered by this slice | Notes |
| --- | --- | --- | --- |
| title | `render_goal()` | yes | Rendered as `Title:`. |
| description | `render_goal()` | yes | Rendered as `Description:`. |
| acceptance_criteria | `render_goal()` | yes | Newly rendered as `Acceptance criteria:` when non-null. |
| notes | `render_goal()` | yes | Newly rendered as `Notes:` when non-null. |
| gap_id | `render_goal()` | yes | Rendered as `Gap id:` when non-null. |
| depends_on | pre-dispatch readiness machinery | deliberately excluded | Dependencies are resolved before dispatch; they do not belong in the human-visible goal. |
| spec_id | `render_goal()` | yes | Rendered as `Spec id:` from `spec_commitment_hint` when non-null. |
| rank | `render_goal()` | yes | Rendered on the `Rank: ... Type: ...` line. |
| type | `render_goal()` | yes | Rendered on the `Rank: ... Type: ...` line. |
| origin | triage/provenance metadata | deliberately excluded | Provenance metadata is not needed by the implementer and remains outside the human-visible goal. |
| ledger comments | `render_goal(comments=...)` | yes | Rendered as `Ledger comments ...` when comments exist. |

## Stage Matrix

All prompt files listed here are audit context only for this slice; none were edited. The currently audited workflow files are:

- `.claude-plugin/.fabro/workflows/implement-work-item/prompts/implement.md`
- `.claude-plugin/.fabro/workflows/implement-work-item/prompts/review.md`
- `.claude-plugin/.fabro/workflows/implement-work-item/prompts/review-fix.md`
- `.claude-plugin/.fabro/workflows/implement-work-item/prompts/fix.md`
- `.claude-plugin/.fabro/workflows/implement-work-item/prompts/pr.md`
- `.claude-plugin/.fabro/workflows/implement-work-item/workflow.toml`

| Stage | title | description | acceptance_criteria | notes | gap_id | depends_on | spec_id | rank | type | origin | ledger comments | Current delivery path |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| start | yes | yes | yes | yes | yes | deliberately excluded | yes | yes | yes | deliberately excluded | yes | The dispatcher constructs the goal before the phase graph starts; dependencies are resolved before dispatch and origin stays provenance-only. |
| implement | yes | yes | yes | yes | yes | deliberately excluded | yes | yes | yes | deliberately excluded | yes | `implement.md` embeds `{{ goal }}` under `Your assignment`; dependencies are resolved before dispatch and origin stays provenance-only. |
| review | yes | yes | yes | yes | yes | deliberately excluded | yes | yes | yes | deliberately excluded | yes | `review.md` embeds `{{ goal }}` as the reviewed work-item; dependencies are resolved before dispatch and origin stays provenance-only. |
| review-fix | yes | yes | yes | yes | yes | deliberately excluded | yes | yes | yes | deliberately excluded | yes | `review-fix.md` embeds the unchanged `{{ goal }}`; dependencies are resolved before dispatch and origin stays provenance-only. |
| fix | yes | yes | yes | yes | yes | deliberately excluded | yes | yes | yes | deliberately excluded | yes | `fix.md` embeds the unchanged `{{ goal }}`; dependencies are resolved before dispatch and origin stays provenance-only. |
| pr | yes | yes | yes | yes | yes | deliberately excluded | yes | yes | yes | deliberately excluded | yes | `pr.md` embeds `{{ goal }}` and now directs PR title/body drafting from the work-item acceptance criteria. |
| janitor | partial | partial | partial | partial | partial | deliberately excluded | partial | partial | partial | deliberately excluded | partial | The janitor gate receives prior-stage context plus committed diff/check output, not a distinct field-rendered brief. |
| acceptance | partial | partial | partial | partial | partial | deliberately excluded | partial | partial | partial | deliberately excluded | partial | Post-merge acceptance is an internal dispatcher valve; it uses the `WorkItem` object and policy, not a prompt-stage field table. |

## Follow-Up Targets

- No further per-stage/per-field gaps remain from this audit. `spec_id` is now rendered as `Spec id:` when present; `depends_on` is deliberately excluded because readiness is resolved before dispatch; `origin` is deliberately excluded as triage/provenance metadata.
- The PR prompt now directs the PR title/body draft from the delivered acceptance criteria in `{{ goal }}`.
