from __future__ import annotations

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from services.repositories.rate_limit import RateLimitRepository


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "UpdateItem")


@patch("services.repositories.rate_limit.get_dynamodb")
def test_increment_and_check_fails_closed_when_counter_write_fails(mock_dynamodb: MagicMock) -> None:
    table = MagicMock()
    table.update_item.side_effect = _client_error("ProvisionedThroughputExceededException")
    mock_dynamodb.return_value.Table.return_value = table

    count, within_limit = RateLimitRepository().increment_and_check()

    assert count == 0
    assert within_limit is False
