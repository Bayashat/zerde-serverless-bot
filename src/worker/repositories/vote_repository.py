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
        target_username: str | None = None,
        target_first_name: str = "User",
    ) -> None:
        """Create a new vote session with the initiator's vote and target user info."""
        key = f"voteban_{chat_id}_{target_user_id}"
        try:
            # Store votes as lists in DynamoDB for compatibility
            self._table.put_item(
                Item={
                    "stat_key": key,
                    "target_user_id": target_user_id,
                    "message_id": message_id,
                    "initiator_user_id": initiator_user_id,
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
        Add a vote to the session.
        Returns updated vote counts: {"votes_for": int, "votes_against": int, "already_voted": bool}

        Note: votes are stored as lists in DynamoDB but handled as sets in memory
        to prevent duplicates and make counting easier.
        """
        key = f"voteban_{chat_id}_{target_user_id}"
        try:
            # Get current session
            session = self.get_vote_session(chat_id, target_user_id)
            votes_for = session["votes_for"]
            votes_against = session["votes_against"]

            # Check if user already voted
            if voter_id in votes_for or voter_id in votes_against:
                return {
                    "votes_for": len(votes_for),
                    "votes_against": len(votes_against),
                    "already_voted": True,
                }

            # Add vote
            if vote_for:
                votes_for.add(voter_id)
            else:
                votes_against.add(voter_id)

            # Update database (preserve all fields from original session)
            self._table.put_item(
                Item={
                    "stat_key": key,
                    "target_user_id": target_user_id,
                    "message_id": session["message_id"],
                    "initiator_user_id": session.get("initiator_user_id"),
                    "target_username": session.get("target_username"),
                    "target_first_name": session.get("target_first_name", "User"),
                    "votes_for": list(votes_for),
                    "votes_against": list(votes_against),
                }
            )

            return {
                "votes_for": len(votes_for),
                "votes_against": len(votes_against),
                "already_voted": False,
            }
        except ClientError as e:
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
