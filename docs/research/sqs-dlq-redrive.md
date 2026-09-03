# SQS DLQ redrive recovery notes

Date: 2026-09-03

Scope: official AWS behavior relevant to recovering ZerdeBot's vector-memory DLQ. This note does not authorize or perform a production redrive.

## ZerdeBot incident findings

Production evidence captured at 2026-09-03 16:42 UTC identified a deterministic startup failure:

- the vector-indexer Lambda had 126 invocations and 126 errors in the retained seven-day window;
- every retained error was an `AccessDeniedException` while importing `core.config`: the process attempted to batch-read `/zerde/prod/bot-token`, although the indexer's least-privilege role correctly grants access only to the Gemini API-key parameters;
- because initialization failed before the SQS handler ran, affected DynamoDB items have no `vector_status` or `vector_error` marker;
- the source queue was empty while the DLQ had 80 visible messages, with `maxReceiveCount=3` and a 14-day DLQ retention;
- a non-destructive ten-message sample contained only `PROCESS_VECTOR_MEMORY` tasks; all ten referenced source records still existed and none had been indexed;
- the oldest sampled message was originally enqueued at 2026-08-20 20:55:07 UTC and was due to expire at approximately 2026-09-03 20:55:07 UTC.

The least-privilege code fix is to stop eagerly loading every bot secret during `core.config` import and rely on the existing secret accessors to load only the key a worker actually requests. Granting the vector indexer access to Telegram, webhook, and Groq secrets would mask the bug by over-privileging the worker.

After that code is deployed, send one explicit vector canary for an existing unindexed source item. Only after it reaches `Vector memory indexed` (or a deliberate safe-skip reason) without a Lambda error should the DLQ be redriven to its original source at a low fixed rate.

## Executive recommendation

For a small backlog whose oldest messages are close to the 14-day limit, first verify that the current consumer can successfully process a fresh vector task and that the old failure cause is gone. Then redrive to the original vector queue at a deliberately low fixed rate, observe the Lambda and both queues, and stop immediately if failures reappear. For an 80-message backlog, `1` message/second is a conservative starting point; this rate is a project recommendation, not an AWS-prescribed value.

If the cause is still unknown and expiry is imminent, moving the messages to a same-type, consumer-disabled quarantine queue can reset their retention clock. That buys time, but it is not a complete recovery: native SQS redrive cannot filter or modify messages, and a normal quarantine queue cannot itself be used as the source of `StartMessageMoveTask` unless it is configured as an SQS DLQ. Plan a controlled later reinjection path before choosing this option.

## What AWS redrive does

- `StartMessageMoveTask` starts an asynchronous move from an SQS DLQ. Omitting `DestinationArn` sends messages back to their respective original source queues; specifying it sends them to a custom destination queue. Only SQS-to-SQS DLQs are supported, and only one movement task can be active for a given DLQ. The rate may be fixed up to 500 messages/second; omitting it lets SQS choose a variable optimized rate. ([AWS API: StartMessageMoveTask](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_StartMessageMoveTask.html))
- A custom destination must have the same queue type as the DLQ. Redrive starts with the oldest DLQ messages, but moved messages can interleave with newly produced messages in the destination. Every moved message receives a new message ID and enqueue time, so its destination retention clock restarts. ([AWS guide: configure DLQ redrive](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html))
- Native redrive cannot filter or edit individual message bodies. A task may run for at most 36 hours, and an account may have at most 100 active tasks. AWS recommends starting with a small custom velocity and gradually increasing it while watching the destination queue. ([AWS guide: configure DLQ redrive](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html))

## Retention and urgency

- SQS retention can be configured from 60 seconds to 14 days. Lowering retention may expire existing messages, and the setting can take up to 15 minutes to propagate. ([AWS API: SetQueueAttributes](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_SetQueueAttributes.html))
- Before redrive, a **standard** queue message keeps its original enqueue timestamp when moved into a DLQ; therefore its total lifetime continues from the original send, even though the DLQ's `ApproximateAgeOfOldestMessage` reflects time since arrival in the DLQ. A **FIFO** message's enqueue timestamp resets when it enters the DLQ. ([AWS guide: DLQ retention periods](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html#sqs-understanding-dlq-message-retention-periods))
- A successful redrive creates a new destination enqueue time for both queue types. When standard-queue messages are already near the 14-day ceiling, increasing the DLQ retention cannot extend them beyond that ceiling; moving them before expiry is the only native operation here that starts a fresh retention period. This urgency statement is an inference from the two AWS behaviors above.

## Standard versus FIFO

- ZerdeBot's vector queue and vector DLQ are standard queues because their CDK definitions do not set `fifo=True`; the queue retries three times and the configured DLQ retention is passed into the construct. See [`infra/components/messaging.py`](../../infra/components/messaging.py#L50-L69).
- Standard SQS is at-least-once delivery and can deliver duplicates or messages out of order. Lambda's SQS event-source mapping can likewise process a record more than once, so the consumer must be idempotent. ([AWS SQS at-least-once delivery](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/standard-queues-at-least-once-delivery.html), [AWS Lambda with SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html))
- FIFO redrive has additional semantics: a FIFO DLQ can redrive only to a FIFO destination; when a message first moves to a FIFO DLQ, its deduplication ID is replaced with the original message ID. Redriven messages can still interleave with live producer traffic at the destination. ([AWS guide: configure DLQ redrive](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html))

## ZerdeBot idempotency implications

Redrive assigns a new SQS message ID, so SQS message ID must not be the business idempotency key. ZerdeBot is already designed around stable memory identity and content/config state:

- vector keys are deterministic from `chat_id` and `source_sk`;
- a record is skipped only when status, rendered-document hash, embedding model, dimensions, and schema version all match the current configuration;
- successful indexing then persists those current markers.

See [`src/bot/services/vector_memory.py`](../../src/bot/services/vector_memory.py#L188-L217) and [`src/bot/services/vector_memory.py`](../../src/bot/services/vector_memory.py#L403-L459). Before production redrive, targeted tests should verify repeated delivery does not create an inconsistent DynamoDB/vector state and that stale/failed records are retried rather than incorrectly skipped.

## Permissions checklist

The IAM principal that starts the redrive needs:

- On the DLQ: `sqs:StartMessageMoveTask`, `sqs:ReceiveMessage`, `sqs:DeleteMessage`, and `sqs:GetQueueAttributes`.
- On the destination: `sqs:SendMessage`.
- To inspect task status: `sqs:ListMessageMoveTasks` plus `sqs:GetQueueAttributes` on the DLQ.
- To cancel: `sqs:CancelMessageMoveTask` plus receive/delete/get-attributes on the DLQ.
- If either the DLQ or original source queue is KMS-encrypted: `kms:Decrypt` for every key that encrypted the affected messages. If the destination is KMS-encrypted: `kms:GenerateDataKey` and `kms:Decrypt` for its key.

AWS documents the complete minimum policy in [Configuring queue permissions for DLQ redrive](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html#sqs-configure-dead-letter-queue-redrive-permissions). `StartMessageMoveTask`, `ListMessageMoveTasks`, and `CancelMessageMoveTask` are not supported through cross-account delegation; the caller must be in the queue-owning account. ([AWS SQS access overview](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-overview-of-managing-access.html))

If queue policies restrict access with `aws:SourceVpc`, SQS performs the move outside the VPC. AWS says to preserve the VPC deny while exempting AWS-mediated redrive with `aws:CalledViaLast = sqs.amazonaws.com` (or the documented `aws:ViaAWSService` alternative), on both DLQ and destination policies. ([AWS guide: redrive with VPC endpoint access control](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html#sqs-dlq-redrive-vpc-endpoint))

## Controlled production playbook

The following is a proposed gate sequence. Commands shown under the move/cancel sections change production state and must not be run without explicit approval.

1. **Read-only preflight**
   - Confirm the exact DLQ ARN, original source queue ARN, queue types, retention, encryption, redrive policy, and current visible/in-flight/delayed counts.
   - Confirm no redrive task is already running.
   - Confirm current vector Lambda health from an equivalent recent successful task; inspect recent vector-indexer errors and throttles. If there is no suitable recent task, require separate approval before sending a fresh canary because that changes production state.
   - Inspect a bounded sample of old messages without deleting them, and validate that their source DynamoDB records still exist. Note that receiving/console-viewing messages increments receive counters even when they are not deleted. ([AWS troubleshooting guide](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/troubleshooting-dlq-redrive.html))

2. **Start slowly, redrive to source**

   ```bash
   aws sqs start-message-move-task \
     --source-arn "$VECTOR_DLQ_ARN" \
     --max-number-of-messages-per-second 1 \
     --region eu-central-1
   ```

   Omitting `--destination-arn` means "back to original source". If SQS returns `CouldNotDetermineMessageSource` because messages were sent directly to the DLQ or arrived from a non-SQS source, AWS requires an explicit custom SQS destination. ([AWS troubleshooting guide](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/troubleshooting-dlq-redrive.html))

3. **Observe the task and workload**

   ```bash
   aws sqs list-message-move-tasks \
     --source-arn "$VECTOR_DLQ_ARN" \
     --max-results 10 \
     --region eu-central-1
   ```

   The API reports status, approximate messages moved/to-move, destination, configured rate, failure reason, start time, and task handle. It returns at most the ten most recent tasks. ([AWS API: ListMessageMoveTasks](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_ListMessageMoveTasks.html))

   Monitor at least:
   - vector source queue visible/in-flight/oldest-age metrics;
   - vector DLQ visible count and whether it starts rising again;
   - vector-indexer Lambda errors, throttles, duration, concurrency, and successful indexing/skip logs;
   - downstream embedding-provider throttles and S3 Vectors/DynamoDB errors.

4. **Stop on regression**

   ```bash
   aws sqs cancel-message-move-task \
     --task-handle "$TASK_HANDLE" \
     --region eu-central-1
   ```

   Cancellation works only while status is `RUNNING`, stops only messages not yet moved, and does not roll back messages already delivered to the destination. ([AWS API: CancelMessageMoveTask](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_CancelMessageMoveTask.html))

5. **Acceptance evidence**
   - move task reaches `COMPLETED` with the expected approximate count;
   - source vector queue drains and remains healthy;
   - vector DLQ reaches zero and stays zero through at least one retry/visibility window;
   - every sampled memory item is either indexed with current markers or deliberately skipped for a logged safe reason;
   - no new Lambda/provider/S3 Vectors errors or unintended duplicate side effects appear.

## Decision rule for messages close to expiry

1. If the current consumer is proven healthy and work is idempotent, redrive to source immediately at a low fixed rate.
2. If the current consumer is not proven healthy but expiry is imminent, move to a same-type quarantine destination to restart retention, with its consumer disabled and a documented later reinjection plan.
3. Do not use system-optimized speed for the first recovery attempt, do not redrive all messages blindly before validating the failure cause, and do not assume cancellation will undo already moved work.
