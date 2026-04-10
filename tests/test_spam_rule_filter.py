"""Tests for RuleBasedSpamFilter — pure logic, no I/O, no mocks."""

import pytest
from services.spam.rule_filter import RuleBasedSpamFilter

_USER_ID = 123456
_CHAT_ID = -1001234567890


@pytest.fixture
def f():
    return RuleBasedSpamFilter()


def test_vpn_ad_with_contact_scores_above_threshold(f):
    # VPN ad with referral @username — typical real-world spam pattern
    score, rules = f.check("Отличный ВПН! Пиши сюда: @vpn_service_bot", _USER_ID, _CHAT_ID)
    assert score > 0.8
    assert "vpn_pattern" in rules
    assert "external_mention" in rules


def test_vpn_ad_alone_queues_for_ai_check(f):
    # VPN mention alone: not auto-banned but flagged for AI (score > 0.3)
    score, rules = f.check("Отличный ВПН! Телеграм с ним просто летает!!", _USER_ID, _CHAT_ID)
    assert score > 0.3
    assert "vpn_pattern" in rules


def test_income_and_mention_scores_above_threshold(f):
    score, rules = f.check("ОНЛАЙН РАБОТА C ДОХОДОМ ОТ 80-230$! @Victoriaa_S7", _USER_ID, _CHAT_ID)
    assert score > 0.8
    assert "money_pattern" in rules
    assert "external_mention" in rules


def test_cyrillic_latin_mixed_triggers_obfuscation_rule(f):
    # PAБOTA — A and P are Latin, rest are Cyrillic
    score, rules = f.check("PAБOTA удалённо, гибкий график!", _USER_ID, _CHAT_ID)
    assert "cis_spam_obfuscation" in rules


def test_normal_russian_it_question_scores_low(f):
    score, rules = f.check("кто знает как настроить nginx на ubuntu 24?", _USER_ID, _CHAT_ID)
    assert score < 0.3


def test_normal_kazakh_it_question_scores_low(f):
    score, rules = f.check("FastAPI үшін қандай ORM жақсы?", _USER_ID, _CHAT_ID)
    assert score < 0.3


def test_plain_mention_without_risk_signals_no_external_mention_score(f):
    """@username alone (no money/vpn/job/mixed-script) is treated as normal chat."""
    score, rules = f.check("Сұрақ бар, @john_doe ге жаз", _USER_ID, _CHAT_ID)
    assert "external_mention" not in rules
    assert "short_text_with_contact" not in rules
    assert score < 0.3


def test_empty_string_returns_zero_score(f):
    score, rules = f.check("", _USER_ID, _CHAT_ID)
    assert score == 0.0
    assert rules == []


def test_score_capped_at_one(f):
    text = "PAБOTA удалённо, доход от 500$, впн @spam_bot хороший"
    score, _ = f.check(text, _USER_ID, _CHAT_ID)
    assert score <= 1.0


def test_vpn_latin_spelling_triggers_rule(f):
    score, rules = f.check("Рабочий vpn, обходит белые списки", _USER_ID, _CHAT_ID)
    assert "vpn_pattern" in rules
    assert score > 0.3


def test_job_offer_without_other_signals(f):
    score, rules = f.check("есть удалённая работа для разработчиков?", _USER_ID, _CHAT_ID)
    assert "job_offer" in rules
    # Job offer alone (0.25) should not auto-ban
    assert score < 0.8


def test_mention_only_does_not_trigger_external_even_if_short(f):
    score, rules = f.check("@user", _USER_ID, _CHAT_ID)
    assert "external_mention" not in rules
    assert score == 0.0
