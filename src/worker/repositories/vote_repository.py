"""
Repository for vote-to-ban storage in DynamoDB.
Each vote session is identified by: chat_id + target_user_id.
"""

from typing import Any

import boto3
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError
from repositories import STATS_TABLE_NAME

logger = Logger()

dynamodb = boto3.resource("dynamodb")


class VoteRepository:
    """
    Repository for vote-to-ban sessions.
    PK: stat_key = "voteban_{chat_id}_{target_user_id}"
    Stores: votes_for (set), votes_against (set), message_id, target_user_id
    """

    def __init__(self) -> None:
        self._table = dynamodb.Table(STATS_TABLE_NAME)
        logger.info("VoteRepository initialized", extra={"table_name": STATS_TABLE_NAME})

    def get_vote_session(self, chat_id: int | str, target_user_id: int) -> dict[str, Any]:
        """Get vote session data for a specific target user in a chat.

        Note: votes_for and votes_against are stored as lists in DynamoDB but
        returned as sets for easier duplicate checking and counting.
        """
        key = f"voteban_{chat_id}_{target_user_id}"
        try:
            resp = self._table.get_item(Key={"stat_key": key}, ConsistentRead=False)
            item: dict[str, Any] = resp.get("Item") or {}
            return {
                "votes_for": set(item.get("votes_for", [])),
                "votes_against": set(item.get("votes_against", [])),
                "message_id": item.get("message_id"),
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
        message_id: int,
        initiator_user_id: int,
        initiator_username: str | None = None,
        initiator_first_name: str = "User",
        target_username: str | None = None,
        target_first_name: str = "User",
    ) -> None:
        """Create a new vote session with the initiator's vote and user info."""
        key = f"voteban_{chat_id}_{target_user_id}"
        try:
            # Store votes as lists in DynamoDB for compatibility
            self._table.put_item(
                Item={
                    "stat_key": key,
                    "target_user_id": target_user_id,
                    "message_id": message_id,
                    "initiator_user_id": initiator_user_id,
                    "initiator_username": initiator_username,
                    "initiator_first_name": initiator_first_name,
                    "target_username": target_username,
                    "target_first_name": target_first_name,
                    "votes_for": [initiator_user_id],  # Stored as list, converted to set on read
                    "votes_against": [],
                }
            )
        except ClientError as e:
            logger.exception(f"Failed to create vote session: {e}")
            raise

    def add_vote(self, chat_id: int | str, target_user_id: int, voter_id: int, vote_for: bool) -> dict[str, Any]:
        """
        Add a vote to the session using atomic DynamoDB operations.
        Returns updated vote counts: {"votes_for": int, "votes_against": int, "already_voted": bool}

        Uses DynamoDB's SET ADD operation to atomically add votes, preventing race conditions.
        """
        key = f"voteban_{chat_id}_{target_user_id}"
        attribute_name = "votes_for" if vote_for else "votes_against"

        try:
            # First check if user already voted (in either list)
            session = self.get_vote_session(chat_id, target_user_id)
            if voter_id in session["votes_for"] or voter_id in session["votes_against"]:
                return {
                    "votes_for": len(session["votes_for"]),
                    "votes_against": len(session["votes_against"]),
                    "already_voted": True,
                }

            # Use UpdateItem with condition to atomically add vote
            # Condition: voter_id must not exist in either votes_for or votes_against
            update_expr = (
                f"SET {attribute_name} = list_append(if_not_exists({attribute_name}, :empty_list), :voter_list)"
            )
            condition_expr = "(NOT contains(#votes_for, :voter_id)) AND (NOT contains(#votes_against, :voter_id))"
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
                },
                ReturnValues="ALL_NEW",
            )

            # Get updated item and return vote counts
            updated_item = response.get("Attributes", {})
            return {
                "votes_for": len(updated_item.get("votes_for", [])),
                "votes_against": len(updated_item.get("votes_against", [])),
                "already_voted": False,
            }
        except ClientError as e:
            # If condition fails (user already voted), return current counts
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
