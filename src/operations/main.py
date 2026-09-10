"""SNS entrypoint isolated from Bot business work and AI dependencies."""

import os

import boto3
from operations_notifications import parse_notice, send_private
from operations_state import DeliveryRepository


def lambda_handler(event, context):
    # Raised errors are deliberately generic: AWS logs must never render a token
    # embedded in an HTTP exception URL, an SNS body, or SSM provider details.
    try:
        records = event.get("Records")
        if not isinstance(records, list) or not records:
            raise ValueError("SNS records are required")
        notices = [parse_notice(record) for record in records]
        repo = DeliveryRepository(boto3.resource("dynamodb").Table(os.environ["STATS_TABLE_NAME"]))
        for notice in notices:
            if notice is None:
                continue
            claim = repo.claim(notice.stream, notice.observed_at)
            if claim is None:
                continue
            key, owner = claim
            try:
                send_private(notice.text)
                repo.confirm(key, owner, notice.observed_at)
            finally:
                repo.release(key, owner)
    except Exception:
        raise RuntimeError("Operations notification failed; inspect configured failure queue") from None
    return {"status": "processed"}
