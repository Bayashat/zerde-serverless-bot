"""Persisted streak outcomes through the single score/receipt transaction."""

from datetime import datetime, timedelta, timezone

import pytest

from tests import quiz_support

quiz_env = quiz_support.quiz_env


def publish(env, request_id=1):
    env.svc.process_on_demand_quiz("-100123", "en", "python", "medium", request_id=request_id)


@pytest.mark.parametrize("age,streak,best,expected", [(None, 0, 0, 1), (0, 4, 4, 4), (1, 3, 3, 4), (2, 5, 8, 1)])
def test_correct_streak_is_persisted_without_losing_best(quiz_env, age, streak, best, expected):
    env = quiz_env
    publish(env)
    if age is not None:
        day = datetime.fromtimestamp(env.clock.now, timezone(timedelta(hours=5))).date() - timedelta(days=age)
        env.table.put_item(
            Item={
                "PK": "SCORE#-100123",
                "SK": "USER#7",
                "current_streak": streak,
                "best_streak": best,
                "last_correct_date": str(day),
            }
        )
    env.answer()
    assert env.process()["state"] == "SCORED"
    score = env.bot.get_user_score("-100123", "7")
    assert score["current_streak"] == expected
    assert score["best_streak"] == max(best, expected)
    assert score["total_score"] == 3
    assert score["week_score"] == 0
    assert "answered_poll_ids" not in score


def test_duplicate_answer_does_not_score_twice_but_different_poll_does(quiz_env):
    env = quiz_env
    publish(env)
    env.answer()
    env.process()
    env.answer(update_id=99)
    env.process()
    publish(env, 2)
    env.answer("poll-1", update_id=100)
    env.process("poll-1")
    assert env.bot.get_user_score("-100123", "7")["total_score"] == 6
    assert env.bot.answer_coverage()["scored"] == 2


def test_wrong_then_correct_same_day_restores_streak_one(quiz_env):
    env = quiz_env
    publish(env)
    env.answer(option=1)
    env.process()
    assert env.bot.get_user_score("-100123", "7")["current_streak"] == 0
    publish(env, 2)
    env.answer("poll-1", update_id=2)
    env.process("poll-1")
    assert env.bot.get_user_score("-100123", "7")["current_streak"] == 1


def test_daily_earned_points_count_in_current_week(quiz_env):
    env = quiz_env
    draft = env.svc._draft(quiz_support.question(), "python", "en", "medium")
    env.svc._prepare_daily_publication = lambda *args: (draft, [])
    assert env.svc.process_daily_quiz(["-100123"], "en", scheduled_at=env.clock.now)["status"] == "ok"
    env.answer()
    env.process()
    assert env.bot.get_user_score("-100123", "7")["week_score"] == 3


def test_legacy_answer_dedupe_is_preserved(quiz_env):
    env = quiz_env
    publish(env)
    env.table.put_item(Item={"PK": "SCORE#-100123", "SK": "USER#7", "total_score": 99, "answered_poll_ids": ["poll-0"]})
    env.answer()
    assert env.process()["state"] == "DUPLICATE"
    assert env.bot.get_user_score("-100123", "7")["total_score"] == 99


def test_late_older_wrong_answer_cannot_reset_newer_streak(quiz_env):
    env = quiz_env
    publish(env)
    env.answer(option=1, update_id=1)
    publish(env, 2)
    env.answer("poll-1", update_id=2)
    env.process("poll-1")
    env.process("poll-0")
    assert env.bot.get_user_score("-100123", "7")["current_streak"] == 1
