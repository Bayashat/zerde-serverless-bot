"""Vote-to-ban sessions in DynamoDB."""

import time
from typing import Any

from botocore.exceptions import ClientError
from core.config import STATS_TABLE_NAME
from core.logger import LoggerAdapter, get_logger
from services.repositories._common import get_dynamodb

logger = LoggerAdapter(get_logger(__name__), {})

VOTEBAN_TTL_SECONDS = 3 * 60 * 60  # 3 hours


class VoteRepository:
    """Vote-to-ban sessions on the same DynamoDB table.

    PK: ``stat_key = voteban_<chat_id>_<target_user_id>``.
    """

    def __init__(self) -> None:
        self._table = get_dynamodb().Table(STATS_TABLE_NAME)
        logger.info("VoteRepository initialized", extra={"table_name": STATS_TABLE_NAME})

    def get_vote_session(self, chat_id: int | str, target_user_id: int) -> dict[str, Any]:
        """Get vote session data for a target user in a chat."""
        key = f"voteban_{chat_id}_{target_user_id}"
        try:
            resp = self._table.get_item(Key={"stat_key": key}, ConsistentRead=False)
            item: dict[str, Any] = resp.get("Item") or {}
            return {
                "votes_for": set(item.get("votes_for", [])),
                "votes_against": set(item.get("votes_against", [])),
                "votes_for_info": list(item.get("votes_for_info", [])),
                "votes_against_info": list(item.get("votes_against_info", [])),
                "reply_message_id": item.get("reply_message_id"),
                "sent_message_id": item.get("sent_message_id"),
                "target_user_id": item.get("target_user_id"),
                "initiator_user_id": item.get("initiator_user_id"),
                "initiator_username": item.get("initiator_username"),
                "initiator_first_name": item.get("initiator_first_name"),
                "target_username": item.get("target_username"),
                "target_first_name": item.get("target_first_name"),
            }
        except ClientError as e:
            logger.exception(f"Failed to get vote session: {e}")
            raise

    def create_vote_session(
        self,
        chat_id: int | str,
        target_user_id: int,
        reply_message_id: int,
        sent_message_id: int,
        initiator_user_id: int,
        initiator_username: str | None = None,
        initiator_first_name: str = "User",
        target_username: str | None = None,
        target_first_name: str = "User",
    ) -> None:
        """Create a new vote session with the initiator's vote and user info."""
        key = f"voteban_{chat_id}_{target_user_id}"
        try:
            self._table.put_item(
                Item={
                    "stat_key": key,
                    "target_user_id": target_user_id,
                    "reply_message_id": reply_message_id,
                    "sent_message_id": sent_message_id,
                    "initiator_user_id": initiator_user_id,
                    "initiator_username": initiator_username,
                    "initiator_first_name": initiator_first_name,
                    "target_username": target_username,
                    "target_first_name": target_first_name,
                    "votes_for": [initiator_user_id],
                    "votes_against": [],
                    "votes_for_info": [
                        {
                            "id": initiator_user_id,
                            "username": initiator_username or "",
                            "first_name": initiator_first_name,
                        }
                    ],
                    "votes_against_info": [],
                    "ttl": int(time.time()) + VOTEBAN_TTL_SECONDS,
                }
            )
        except ClientError as e:
            logger.exception(f"Failed to create vote session: {e}")
            raise

    def add_vote(
        self,
        chat_id: int | str,
        target_user_id: int,
        voter_id: int,
        vote_for: bool,
        voter_username: str | None = None,
        voter_first_name: str = "User",
    ) -> dict[str, Any]:
        """Atomically add a vote; returns updated counts and ``already_voted`` flag."""
        key = f"voteban_{chat_id}_{target_user_id}"
        attribute_name = "votes_for" if vote_for else "votes_against"
        info_attribute_name = "votes_for_info" if vote_for else "votes_against_info"

        try:
            update_expr = (
                f"SET {attribute_name} = list_append("
                f"if_not_exists({attribute_name}, :empty_list), :voter_list), "
                f"{info_attribute_name} = list_append("
                f"if_not_exists({info_attribute_name}, :empty_info_list), :voter_info_list)"
            )
            condition_expr = "(NOT contains(#votes_for, :voter_id)) " "AND (NOT contains(#votes_against, :voter_id))"
            response = self._table.update_item(
                Key={"stat_key": key},
                UpdateExpression=update_expr,
                ConditionExpression=condition_expr,
                ExpressionAttributeNames={
                    "#votes_for": "votes_for",
                    "#votes_against": "votes_against",
                },
                ExpressionAttributeValues={
                    ":voter_list": [voter_id],
                    ":voter_id": voter_id,
                    ":empty_list": [],
                    ":voter_info_list": [
                        {
                            "id": voter_id,
                            "username": voter_username or "",
                            "first_name": voter_first_name,
                        }
                    ],
                    ":empty_info_list": [],
                },
                ReturnValues="ALL_NEW",
            )

            updated_item = response.get("Attributes", {})
            return {
                "votes_for": len(updated_item.get("votes_for", [])),
                "votes_against": len(updated_item.get("votes_against", [])),
                "already_voted": False,
            }
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                session = self.get_vote_session(chat_id, target_user_id)
                return {
                    "votes_for": len(session["votes_for"]),
                    "votes_against": len(session["votes_against"]),
                    "already_voted": True,
                }
            logger.exception(f"Failed to add vote: {e}")
            raise

    def delete_vote_session(self, chat_id: int | str, target_user_id: int) -> None:
        """Delete a vote session (after ban or forgiveness)."""
        key = f"voteban_{chat_id}_{target_user_id}"
        try:
            self._table.delete_item(Key={"stat_key": key})
        except ClientError as e:
            logger.exception(f"Failed to delete vote session: {e}")
            raise
