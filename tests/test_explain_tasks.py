"""Explain task repository enqueue and idempotency behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from services.repositories.explain_tasks import ExplainTaskRepository


def _conditional_check_failed() -> ClientError:
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "condition failed"}},
        "UpdateItem",
    )


@patch("services.repositories.explain_tasks.get_dynamodb")
def test_enqueue_after_reserve_releases_only_when_send_fails(mock_dynamo: MagicMock) -> None:
    table = MagicMock()
    mock_dynamo.return_value.Table.return_value = table
    repo = ExplainTaskRepository()

    def fail_send() -> None:
        raise RuntimeError("sqs down")

    with pytest.raises(RuntimeError, match="sqs down"):
        repo.enqueue_after_reserve(42, fail_send)

    table.delete_item.assert_called_once()
    table.update_item.assert_not_called()


@patch("services.repositories.explain_tasks.get_dynamodb")
def test_enqueue_after_reserve_keeps_reservation_when_mark_enqueued_fails(mock_dynamo: MagicMock) -> None:
    table = MagicMock()
    table.update_item.side_effect = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "throttled"}},
        "UpdateItem",
    )
    mock_dynamo.return_value.Table.return_value = table
    repo = ExplainTaskRepository()

    repo.enqueue_after_reserve(42, lambda: None)

    table.delete_item.assert_not_called()
    table.update_item.assert_called_once()


@patch("services.repositories.explain_tasks.get_dynamodb")
def test_is_completed_true_when_status_completed(mock_dynamo: MagicMock) -> None:
    table = MagicMock()
    table.get_item.return_value = {"Item": {"status": "completed"}}
    mock_dynamo.return_value.Table.return_value = table
    repo = ExplainTaskRepository()

    assert repo.is_completed(7) is True


@patch("services.repositories.explain_tasks.get_dynamodb")
def test_is_completed_false_for_missing_or_non_completed(mock_dynamo: MagicMock) -> None:
    table = MagicMock()
    table.get_item.return_value = {"Item": {"status": "enqueued"}}
    mock_dynamo.return_value.Table.return_value = table
    repo = ExplainTaskRepository()

    assert repo.is_completed(7) is False
