"""Data-access layer: DynamoDB repositories and SQS task helpers."""

from services.repositories.captcha import CaptchaRepository
from services.repositories.group_memory import GroupMemoryRepository
from services.repositories.lambda_invoker import LambdaInvoker
from services.repositories.quiz import QuizRepository
from services.repositories.rate_limit import RateLimitRepository
from services.repositories.sqs import SQSClient
from services.repositories.stats import StatsRepository
from services.repositories.votes import VoteRepository

__all__ = [
    "CaptchaRepository",
    "GroupMemoryRepository",
    "LambdaInvoker",
    "QuizRepository",
    "RateLimitRepository",
    "SQSClient",
    "StatsRepository",
    "VoteRepository",
]
