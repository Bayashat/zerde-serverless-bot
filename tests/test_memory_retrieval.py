from unittest.mock import MagicMock

from services.memory_retrieval import (
    MemoryCandidate,
    RetrievalIntent,
    analyze_query_intent,
    build_agent_memory_context,
    pack_context,
    score_candidates,
)


def _empty_context(*args, **kwargs) -> str:
    return ""


def test_analyze_query_intent_detects_self_reference_and_targets():
    intent = analyze_query_intent(
        "我是谁 and what do you know about @ada from yesterday?",
        requester_user_id=42,
        ignored_usernames={"zerde_kz_bot"},
    )

    assert intent.is_self_reference is True
    assert intent.target_user_ids == {"42"}
    assert intent.target_usernames == {"ada"}
    assert intent.time_hint == "yesterday"


def test_build_agent_memory_context_scopes_self_reference_semantic_to_requester():
    repo = MagicMock()
    semantic_retrieval = MagicMock(return_value=[])

    bundle = build_agent_memory_context(
        repo=repo,
        chat_id=-100123,
        user_text="我是谁",
        requester_user_id=42,
        requester_username="ada",
        requester_display_name="Ada",
        recent_context_fn=_empty_context,
        long_term_context_fn=_empty_context,
        semantic_retrieval_fn=semantic_retrieval,
        semantic_context_fn=lambda rows: "",
        user_profile_context_fn=_empty_context,
        requester_profile_context_fn=lambda *args, **kwargs: "Requester profile: username=@ada",
    )

    semantic_retrieval.assert_called_once()
    assert semantic_retrieval.call_args.kwargs["user_id"] == 42
    assert bundle.requester_profile_context == "Requester profile: username=@ada"
    assert bundle.retrieval_sources[0]["source"] == "requester_profile"


def test_build_agent_memory_context_does_not_scope_non_self_reference_semantic_query():
    repo = MagicMock()
    semantic_retrieval = MagicMock(return_value=[])

    build_agent_memory_context(
        repo=repo,
        chat_id=-100123,
        user_text="what did we decide about S3 Vectors?",
        requester_user_id=42,
        recent_context_fn=_empty_context,
        long_term_context_fn=_empty_context,
        semantic_retrieval_fn=semantic_retrieval,
        semantic_context_fn=lambda rows: "",
        user_profile_context_fn=_empty_context,
        requester_profile_context_fn=_empty_context,
    )

    assert semantic_retrieval.call_args.kwargs["user_id"] is None


def test_build_agent_memory_context_injects_target_profile_context():
    repo = MagicMock()

    bundle = build_agent_memory_context(
        repo=repo,
        chat_id=-100123,
        user_text="@bayashat кім?",
        recent_context_fn=_empty_context,
        long_term_context_fn=_empty_context,
        semantic_retrieval_fn=MagicMock(return_value=[]),
        semantic_context_fn=lambda rows: "",
        user_profile_context_fn=lambda *args, **kwargs: "Trusted profile: username=@bayashat",
        requester_profile_context_fn=_empty_context,
    )

    assert bundle.intent.target_usernames == {"bayashat"}
    assert bundle.user_profile_context == "Trusted profile: username=@bayashat"
    assert any(source["source"] == "target_profile" for source in bundle.retrieval_sources)


def test_joke_intent_preserves_joke_candidate_and_non_joke_query_penalizes_it():
    joke = MemoryCandidate(
        source="semantic",
        source_sk="JOKE#1#2",
        memory_kind="joke",
        text="The banana deploy meme is a recurring group joke.",
        score=0.6,
        trust_level=60,
        created_at=None,
        metadata={},
    )
    event = MemoryCandidate(
        source="semantic",
        source_sk="EVENT#1#3",
        memory_kind="event",
        text="The group chose S3 Vectors for retrieval.",
        score=0.6,
        trust_level=60,
        created_at=None,
        metadata={},
    )

    joke_intent = analyze_query_intent("what is the banana meme?")
    joke_scored = score_candidates([joke], intent=joke_intent, user_text="what is the banana meme?")
    non_joke_intent = analyze_query_intent("what did we choose for retrieval?")
    non_joke_scored = score_candidates(
        [joke, event], intent=non_joke_intent, user_text="what did we choose for retrieval?"
    )

    assert joke_scored[0].memory_kind == "joke"
    joke_score = next(candidate.score for candidate in non_joke_scored if candidate.memory_kind == "joke")
    event_score = next(candidate.score for candidate in non_joke_scored if candidate.memory_kind == "event")
    assert joke_score < event_score


def test_pack_context_respects_char_budget():
    intent = RetrievalIntent(
        is_self_reference=False,
        target_usernames=set(),
        target_user_ids=set(),
        asks_group_decision=False,
        asks_past_event=False,
        asks_joke_or_meme=False,
        time_hint=None,
    )
    bundle = pack_context(
        intent=intent,
        contexts={
            "requester_profile_context": "requester line",
            "user_profile_context": "target line",
            "semantic_memory_context": "semantic line",
            "long_term_memory_context": "long term line",
            "recent_context": "recent line",
        },
        candidates=[],
        char_budget=26,
    )

    total_chars = sum(
        len(value)
        for value in (
            bundle.requester_profile_context,
            bundle.user_profile_context,
            bundle.semantic_memory_context,
            bundle.long_term_memory_context,
            bundle.recent_context,
        )
    )
    assert total_chars <= 26
    assert bundle.requester_profile_context == "requester line"
