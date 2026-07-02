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
| depends_on | not rendered | no | Readiness uses dependencies before dispatch, but the brief does not enumerate them. |
| spec_id | not rendered | no | `spec_commitment_hint` is mapped in store but not included in the goal. |
| rank | `render_goal()` | yes | Rendered on the `Rank: ... Type: ...` line. |
| type | `render_goal()` | yes | Rendered on the `Rank: ... Type: ...` line. |
| origin | not rendered | no | Not included in `render_goal()`. |
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
| start | yes | yes | yes | yes | yes | no | no | yes | yes | no | yes | The dispatcher constructs the goal before the phase graph starts. |
| implement | yes | yes | yes | yes | yes | no | no | yes | yes | no | yes | `implement.md` embeds `{{ goal }}` under `Your assignment`. |
| review | yes | yes | yes | yes | yes | no | no | yes | yes | no | yes | `review.md` embeds `{{ goal }}` as the reviewed work-item. |
| review-fix | yes | yes | yes | yes | yes | no | no | yes | yes | no | yes | `review-fix.md` embeds the unchanged `{{ goal }}`. |
| fix | yes | yes | yes | yes | yes | no | no | yes | yes | no | yes | `fix.md` embeds the unchanged `{{ goal }}`. |
| pr | yes | yes | yes | yes | yes | no | no | yes | yes | no | yes | `pr.md` embeds `{{ goal }}` for the PR description. |
| janitor | partial | partial | partial | partial | partial | no | no | partial | partial | no | partial | The janitor gate receives prior-stage context plus committed diff/check output, not a distinct field-rendered brief. |
| acceptance | partial | partial | partial | partial | partial | no | no | partial | partial | no | partial | Post-merge acceptance is an internal dispatcher valve; it uses the `WorkItem` object and policy, not a prompt-stage field table. |

## Follow-Up Targets

- S4 can make prompt stages consume the newly delivered `Acceptance criteria:` and `Notes:` sections explicitly.
- A later slice should decide whether `depends_on`, `spec_commitment_hint`, and `origin` belong in the human-visible goal or only in pre-dispatch machinery.
