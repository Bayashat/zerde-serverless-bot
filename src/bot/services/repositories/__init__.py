"""Data-access layer: DynamoDB (stats + voteban + quiz + rate limit) and SQS (timeout tasks)."""

from services.repositories.lambda_invoker import LambdaInvoker
from services.repositories.quiz import QuizRepository
from services.repositories.rate_limit import RateLimitRepository
from services.repositories.sqs import SQSClient
from services.repositories.stats import StatsRepository
from services.repositories.votes import VoteRepository

__all__ = [
    "LambdaInvoker",
    "QuizRepository",
    "RateLimitRepository",
    "SQSClient",
    "StatsRepository",
    "VoteRepository",
]
