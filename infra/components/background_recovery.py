"""Bounded recovery triggers for existing background owners; no new data writer."""

from aws_cdk import Duration
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda_destinations as destinations


def add_background_recovery(scope, *, env_name, runtime_active, quiz_lambda, news_lambda, queue, dlq):
    # Failure envelopes are retained in the existing unconsumed DLQ for operator
    # inspection. They are not valid task bodies and must never be blindly replayed.
    for function in (quiz_lambda, news_lambda):
        function.configure_async_invoke(
            max_event_age=Duration.hours(6), retry_attempts=2, on_failure=destinations.SqsDestination(dlq)
        )
    publications = events.Rule(
        scope,
        "QuizPublicationRecovery",
        rule_name=f"zerde-serverless-quiz-publication-recovery-{env_name}",
        schedule=events.Schedule.rate(Duration.minutes(5)),
        enabled=runtime_active,
    )
    publications.add_target(
        targets.LambdaFunction(
            quiz_lambda,
            event=events.RuleTargetInput.from_object({"action": "recover_publications"}),
            dead_letter_queue=dlq,
            max_event_age=Duration.hours(1),
            retry_attempts=3,
        )
    )
    answers = events.Rule(
        scope,
        "QuizAnswerRecovery",
        rule_name=f"zerde-serverless-quiz-answer-recovery-{env_name}",
        schedule=events.Schedule.rate(Duration.minutes(5)),
        enabled=runtime_active,
    )
    answers.add_target(
        targets.SqsQueue(
            queue,
            message=events.RuleTargetInput.from_object({"schema": 2, "task_type": "PROCESS_QUIZ_ANSWER_RECOVERY"}),
            dead_letter_queue=dlq,
            max_event_age=Duration.hours(1),
            retry_attempts=3,
        )
    )
