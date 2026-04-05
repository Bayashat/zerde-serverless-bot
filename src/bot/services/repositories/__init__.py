"""Data-access layer: DynamoDB (stats + voteban + quiz) and SQS (timeout tasks)."""

from services.repositories.quiz import QuizRepository
from services.repositories.sqs import SQSClient
from services.repositories.stats import StatsRepository
from services.repositories.votes import VoteRepository

__all__ = ["StatsRepository", "VoteRepository", "SQSClient", "QuizRepository"]
