"""Reference-only answer processing; the repository is the sole score/outbox owner."""

import time

from services.repositories._quiz_answers import QuizAnswerConflict

_TERMINAL = {"SCORED", "DUPLICATE", "INVALID", "EXPIRED"}


def process_quiz_answer_task(*, repo, body):
    if (
        set(body) != {"schema", "task_type", "poll_id", "user_id"}
        or body["schema"] != 2
        or body["task_type"] != "PROCESS_QUIZ_ANSWER"
    ):
        raise ValueError("Unsupported quiz answer task")
    for _ in range(4):
        answer = repo.get_answer(body["poll_id"], body["user_id"])
        if not answer:
            return {"state": "MISSING"}
        if answer["state"] in _TERMINAL or int(answer["next_attempt_at"]) > int(time.time()):
            return {"state": answer["state"], "next_attempt_at": int(answer["next_attempt_at"])}
        try:
            if int(answer["expires_at"]) <= int(time.time()):
                result = repo.finish_answer(answer, "EXPIRED")
            else:
                poll = repo.lookup_poll(answer["poll_id"])
                result = repo.score_answer(answer, poll) if poll else repo.defer_answer(answer)
            return {"state": result["state"], "next_attempt_at": int(result["next_attempt_at"])}
        except QuizAnswerConflict:
            continue
    raise QuizAnswerConflict("Answer or score remains busy")


def recover_quiz_answers(*, repo, sqs_repo, limit=100):
    """One bounded persisted page; failed rows remain in outbox for the next traversal."""
    control, rows, cursor = repo.answer_recovery_page(limit=limit)
    counts = {"seen": len(rows), "queued": 0, "future": 0, "expired": 0, "errors": 0}
    for row in rows:
        try:
            answer = repo.get_answer(row["poll_id"], row["user_id"])
            if not answer:
                repo.expire_answer_orphan(row)
                counts["expired"] += 1
                continue
            if int(answer["expires_at"]) <= int(time.time()):
                if answer["state"] not in _TERMINAL:
                    repo.finish_answer(answer, "EXPIRED")
                    counts["expired"] += 1
                continue
            if int(answer["next_attempt_at"]) > int(time.time()):
                counts["future"] += 1
                continue
            sqs_repo.send_quiz_answer_task(answer["poll_id"], answer["user_id"])
            counts["queued"] += 1
        except QuizAnswerConflict:
            # Another worker completed/deferred the same receipt. Its durable state wins.
            continue
        except Exception:
            counts["errors"] += 1
    repo.checkpoint_answer_recovery(control, cursor)
    if counts["errors"]:
        raise RuntimeError("Quiz answer recovery has retryable row failures")
    return counts
