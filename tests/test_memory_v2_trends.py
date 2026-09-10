"""Deterministic group word frequencies require caller-validated source snapshots."""

from dataclasses import replace

import pytest
from services.memory_v2.models import ExtractionSource, MemoryInputError, SourceRef
from services.memory_v2.trends import WINDOW_SECONDS, aggregate_trends

NOW = 2_000_000_000


def source(text, message_id="1", actor="42", age=0, **changes):
    return replace(
        ExtractionSource("-100123", SourceRef(message_id, 1, "epoch"), actor, text, (), NOW - age), **changes
    )


def aggregate(sources):
    return aggregate_trends(sources, chat_id="-100123", epoch="epoch", as_of=NOW)


def test_frequency_counts_messages_and_people_once_and_is_order_independent():
    sources = [
        source("Python python PYTHON and PostgreSQL"),
        source("Python question", "2"),
        source("Python advice", "3", "99"),
    ]
    snapshot = aggregate(sources)
    assert snapshot == aggregate(list(reversed(sources)))
    python = snapshot.topics[0]
    assert python.topic == "python" and python.message_count == 3 and python.participant_count == 2
    assert len(python.source_refs) == 3
    assert sum(count for _, count in python.daily_message_counts) == 3
    assert snapshot.eligible_source_count == 3


def test_seven_day_window_excludes_old_sources_and_does_not_use_quoted_text():
    text = "Quoted Python. I asked about SQL."
    snapshot = aggregate([source(text, quoted_spans=((0, 14),)), source("Python", "2", age=WINDOW_SECONDS + 1)])
    assert snapshot.eligible_source_count == 1
    assert [topic.topic for topic in snapshot.topics] == ["databases"]


def test_topic_keywords_are_group_frequencies_even_when_the_message_is_a_question():
    snapshot = aggregate([source("Why choose Django rather than React?")])
    assert snapshot.topics[0].topic == "web_development"
    assert snapshot.topics[0].message_count == 1
    assert not hasattr(snapshot.topics[0], "interests")  # No personal projection exists in this result.


@pytest.mark.parametrize(
    "sources",
    [
        [source("Python", chat_id="-100999")],
        [source("Python", ref=SourceRef("1", 1, "other"))],
        [source("Python"), source("Python")],
        [source("Python", edited_at=NOW + 1)],
        [source("Python and my password is synthetic")],
    ],
)
def test_invalid_or_sensitive_snapshots_fail_closed(sources):
    with pytest.raises(MemoryInputError):
        aggregate(sources)


def test_no_matching_words_is_an_empty_trend_not_an_invented_group_profile():
    snapshot = aggregate([source("Сәлем баршаңызға")])
    assert snapshot.topics == () and snapshot.eligible_source_count == 1
