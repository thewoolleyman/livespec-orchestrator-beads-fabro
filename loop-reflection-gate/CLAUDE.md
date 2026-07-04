# loop-reflection-gate/

Best-practices survey + design docs for the fabro factory loop's
eval/audit/reflection gate, plus the human-ratified `lessons.md`
digest. Moved here WHOLE from `research/loop-reflection-gate/`
(epic `livespec-gt7crt`, livespec tenant): these documents are live
operational surface — cited as design-of-record by shipping code and
written to by the production reflector — not completed research, so
they live at top level rather than under `research/`.

**LOAD-BEARING — do not move or archive without a coordinated code
change:** the out-of-band reflector's default lessons path is
`loop-reflection-gate/lessons.md`
(`commands/_dispatcher_reflector_oob.py`), and the telemetry modules
(`_otel_receive.py`, `_otel_scrub.py`, `_dispatcher_cost_pricing.py`,
`_dispatcher_heartbeat_probe.py`) cite these docs as design-of-record.

`lessons.md` is the human-ratification seam: the reflector proposes
lesson entries via PR (`GitPrLessonsProposer`), and only entries the
maintainer MERGES count as ratified. Edit the other documents through
the normal PR flow; they are design-of-record, not frozen archives.
