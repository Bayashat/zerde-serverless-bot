"""
Repository for vote-to-ban functionality in DynamoDB.
vote_key format: "chat:{chat_id}:target:{target_user_id}:initiator:{initiator_user_id}"
"""

import time
from typing import Any

import boto3
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError
from repositories import VOTE_BAN_TABLE_NAME

logger = Logger()

dynamodb = boto3.resource("dynamodb")

# Minimum votes required to ban
VOTES_THRESHOLD = 15
# Vote session TTL in seconds (24 hours)
VOTE_SESSION_TTL_SECONDS = 86400


class VoteRepository:
    """
    Repository for VoteBan table: tracks vote-to-ban sessions.
    PK: vote_key = "chat:{chat_id}:target:{target_user_id}:initiator:{initiator_user_id}"
    """

    def __init__(self) -> None:
        self._table = dynamodb.Table(VOTE_BAN_TABLE_NAME)
        logger.info("VoteRepository initialized", extra={"table_name": VOTE_BAN_TABLE_NAME})

    def create_vote_session(
        self, chat_id: int | str, target_user_id: int, initiator_user_id: int, message_id: int
    ) -> str:
        """
        Create a new vote session. Returns the vote_key.
        TTL is set to 24 hours from now.
        """
        vote_key = f"chat:{chat_id}:target:{target_user_id}:initiator:{initiator_user_id}"
        ttl = int(time.time()) + VOTE_SESSION_TTL_SECONDS

        try:
            self._table.put_item(
                Item={
                    "vote_key": vote_key,
                    "chat_id": str(chat_id),
                    "target_user_id": int(target_user_id),
                    "initiator_user_id": int(initiator_user_id),
                    "message_id": int(message_id),
                    "ban_votes": [],
                    "forgive_votes": [],
                    "created_at": int(time.time()),
                    "ttl": ttl,
                }
            )
            logger.info(f"Created vote session: {vote_key}")
            return vote_key
        except ClientError as e:
            logger.exception(f"Failed to create vote session: {e}")
            raise

    def add_vote(self, vote_key: str, user_id: int, vote_type: str) -> dict[str, Any]:
        """
        Add a vote (ban or forgive) to the session.
        Returns updated vote counts.
        vote_type: "ban" or "forgive"
        """
        if vote_type not in ("ban", "forgive"):
            raise ValueError("vote_type must be 'ban' or 'forgive'")

        # Determine which list to update
        vote_list = "ban_votes" if vote_type == "ban" else "forgive_votes"
        other_list = "forgive_votes" if vote_type == "ban" else "ban_votes"

        try:
            # Combine both operations into a single atomic update
            response = self._table.update_item(
                Key={"vote_key": vote_key},
                UpdateExpression=f"DELETE {other_list} :user_set ADD {vote_list} :user_set",
                ExpressionAttributeValues={":user_set": {user_id}},
                ReturnValues="ALL_NEW",
            )

            item = response.get("Attributes", {})
            ban_count = len(item.get("ban_votes", []))
            forgive_count = len(item.get("forgive_votes", []))

            logger.info(
                f"Vote added: {vote_type}",
                extra={
                    "vote_key": vote_key,
                    "user_id": user_id,
                    "ban_votes": ban_count,
                    "forgive_votes": forgive_count,
                },
            )

            return {
                "ban_votes": ban_count,
                "forgive_votes": forgive_count,
                "target_user_id": item.get("target_user_id"),
                "chat_id": item.get("chat_id"),
            }
        except ClientError as e:
            logger.exception(f"Failed to add vote: {e}")
            raise

    def get_vote_session(self, vote_key: str) -> dict[str, Any] | None:
        """Get vote session data."""
        try:
            response = self._table.get_item(Key={"vote_key": vote_key})
            item = response.get("Item")
            if item:
                return {
                    "vote_key": item.get("vote_key"),
                    "chat_id": item.get("chat_id"),
                    "target_user_id": int(item.get("target_user_id", 0)),
                    "initiator_user_id": int(item.get("initiator_user_id", 0)),
                    "message_id": int(item.get("message_id", 0)),
                    "ban_votes": len(item.get("ban_votes", [])),
                    "forgive_votes": len(item.get("forgive_votes", [])),
                }
            return None
        except ClientError as e:
            logger.exception(f"Failed to get vote session: {e}")
            raise

    def delete_vote_session(self, vote_key: str) -> None:
        """Delete a vote session."""
        try:
            self._table.delete_item(Key={"vote_key": vote_key})
            logger.info(f"Deleted vote session: {vote_key}")
        except ClientError as e:
            logger.exception(f"Failed to delete vote session: {e}")
            raise
