# Telegram history import (retired)

Historical Telegram imports are retired by the approved Memory V2 cutover. The CLI
and library apply path reject writes before opening exports or accessing AWS. Do not
re-enable the importer, enqueue a backfill, or use old exports to initialize V2.

V2 begins from a newly enabled group epoch and derives personal facts only from
explicit self-statements under the new source, moderation and deletion contracts.
The user's original Telegram export files are outside cleanup scope and remain theirs.

All legacy imported **and** realtime memory must be removed through the reviewed
[Z10 cleanup process](legacy-memory-cleanup.md), after every legacy reader/writer
(including explicit reply threads and album membership) has stopped and drained.
That process backs up only the exact selected AWS records/vectors into temporary
local encrypted archives, protects mixed-table business records, and never deletes
original export files. An old audit report is not an executable deletion manifest.

See [the approved plan](goals/zerdebot-memory-v2/PLAN.md),
[Z01 deployment gates](MEMORY_CUTOVER.md), and
[Z03 type/marker boundaries](legacy-memory-deletion.md).

This documentation and the tool's offline tests do not establish that a production
backup, cleanup, physical erasure, or V2 rollout has occurred.
