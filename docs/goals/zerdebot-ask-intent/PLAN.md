# /ask intent repair

Status: PRE review. Base main `af90a3682deca630e4188596e249fc1a66c72d3a`.
Evidence root: `2026-10-20-ask-intent-repair` under the local acceptance directory.

## Problem and expected result

The screenshot shows `/ask RTX SPARK` receiving the deterministic personal-memory
unknown message. Current non-media `/ask` calls `MemoryPublicAnswers.try_answer`;
the selector chooses `facts`, `unknown` or `general`. Only `general` reaches the
ordinary queued answer. The prompt leads with selecting self-statements and
applies an ambiguous-person rule without first establishing a personal question.
The screenshot proves a wrong response, not the precise original model output.

Determine the requested task before inspecting whether candidate facts support it.
An isolated product/technology/topic name is a request for public explanation,
unless the question actually asks about a participant or this group's history.
Products, translation, arithmetic and public knowledge must not become personal
queries because the actor/profile exists, facts are absent or unrelated, or a
request uses a courtesy first-person phrase such as “I want to understand”.
Personal/group questions without evidence must retain the fixed unknown answer.

## Architecture slice and unchanged owners

`handlers/commands.py` and explicit triggers in `group_agent.py` keep calling the
sole `memory_v2/public_answers.py` adapter. `answer_prompt.py` owns the classification
instructions and exact structured request. `answer_selector.py` retains the
single budgeted selection call, current model, at most two attempts, schema,
strict parser, quota, reserve/settle and UNKNOWN billing. `answers.py` retains
source validation, identity checks, deterministic fact rendering and delivery.
`general` returns to the existing explicit-context/queue/provider owner without
personal fact text. No alternative classifier, keyword routing, new command,
new personal context owner, provider, fallback or identity inference is added.

The displaced behavior is the old intent instruction in the same request owner;
there is no second runtime path. Cutover is the new immutable Bot/Memory package.
Unknown aliases retain their conservative existing behavior. Existing selector
unavailability still falls back to the guarded fact-free ordinary path; this
repair does not claim to redesign failure UX or guarantee its semantic output.
MemoryConflict/MemoryUnavailable and SENT/UNKNOWN duplicate protections remain.
Reply/mention can supply identity candidates, not by itself personal intent.
Historical bot answer text remains excluded as a fact source.

## Implementation and evidence

1. Independent PRE review of this finite slice. Main agent implements sequentially.
2. Rewrite the selector instructions to decide task intent first, then select
   validated facts only for personal/group-history requests. Include contrastive
   four-language examples, unfamiliar public names and mixed-task boundaries.
3. Freeze a small synthetic question matrix with expected intent and empty versus
   irrelevant-fact contexts. Add integrated offline tests through the real
   selector parser, transaction owner and command/general fallback. Stubs prove
   control flow only, never real model semantic quality. Preserve education,
   alias, reply, edit/forget, cross-group and duplicate-delivery tests.
4. Independent correctness and maintenance review, targeted tests, full suite and
   required hooks. Source PR and three-job CI. No frozen historical model run is
   rerun or relabelled.
5. Separate finite release plan/PRE bound to the immutable source: fresh current
   baseline, actual five-handler ARM package/probe, exactly Bot/Memory code
   change, dev unique changeset, full primary/independent package/config readback
   and at least 300 seconds stable. Preserve other functions, layer, identity,
   alarms, schedules, four prod controls and valid revisions. No manual Invoke.
6. Before claiming semantic success, use a newly authorized dev Telegram window
   for a bounded real question/response check, including the reported short
   product topic and an unsupported personal counterpart. Verify the actual
   route and complete response, no replay of old inputs, no fabricated update.
   If no window is available, report the real check as pending, not passed.
   Source/package evidence may support publishing the narrow prompt correction
   under existing deployment authority; it does not prove production semantics.
7. Prod follows the same unique changeset and independent readback/stability gates.
   Final docs/task_manifest/issues reflect actual evidence only, with frozen
   historical reports unchanged; merge causes no additional runtime deployment.

Target perspective: an ordinary user sees a topical answer (or a relevant
clarification), not a claim about missing self-statements. A personal question
gets source-backed facts or the existing unknown reply. Independent reviewers
inspect real provider/Telegram receipts when available, not a mock-only “PASS”.

## Stop, rollback and retained responsibilities

Stop release for unexpected source/package/config differences, unsafe identity,
budget or delivery behavior, failed required tests or unreviewed changeset.
If real checks misroute public topics or invent unsupported personal facts, retain
the failed evidence, narrow the fix and re-review; do not silently broaden fallback.
Any required rollback uses the prior verified package through a new bounded
changeset, preserving current controls and business data, never resetting epochs.

No unrelated production/group activation, payment/secret changes, model-limit
bypass, history import, background interaction, mixed-queue Receive/Purge or
manual Lambda Invoke. New API/config/model/UI raw evidence must get its own
actual seven-day anchor before capture and immediate Z10/automation registration;
source/ZIP/safe summaries are distinguished. All fifteen existing exact deadlines,
including Oct21 13:10:50.198516 UTC, remain unchanged. No old once entry is rerun.
