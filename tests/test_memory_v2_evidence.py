"""Regression shapes from the failed real run; synthetic evidence only."""

import asyncio
import json
from dataclasses import replace

import pytest
from services.memory_v2.commands import MemoryCommandService
from services.memory_v2.extraction_prompt import build_request, input_upper_bytes, validate_request
from services.memory_v2.extractor import parse_extraction_response
from services.memory_v2.lifecycle import MemoryLifecycle
from services.memory_v2.models import EvidenceSpan, FactChange, MemoryInputError

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, change, commit, event
from tests.test_memory_v2_extraction import extractor, fact, response, source
from tests.test_memory_v2_ingestion import records, worker

env = contract.env


@pytest.mark.parametrize(
    "text,excerpt",
    [
        ("We share the name Aster, but I use Java.", "I use Java."),
        ("In this group: I use TypeScript.", "I use TypeScript."),
        ("Correction: I use Julia at work.", "I use Julia at work."),
        ("Though I used to\nwork with Java, I now use Rust.", "I now use Rust."),
        ("🙂 We share the same name,\nbut I use Java.", "I use Java."),
        ("Біз аттаспыз, бірақ мен Java қолданамын.", "мен Java қолданамын."),
        ("Мы тёзки, но я использую Java.", "я использую Java."),
        ("Осы group-та: I use TypeScript.", "I use TypeScript."),
        ("I use .NET 8.0. This is for my current project.", "I use .NET 8.0."),
    ],
)
def test_complete_source_keeps_prefix_suffix_and_cross_line_qualifiers(text, excerpt):
    original = source(" \n" + text + "\t ")
    result = parse_extraction_response(response([fact(excerpt)]), [original])[0]
    assert result.ref == original.ref
    assert result.changes[0].evidence == EvidenceSpan(2, 2 + len(text))
    assert result.changes[0].evidence.excerpt({"text": original.text}) == text


@pytest.mark.parametrize("text", ["I use Java. " + "x" * 240, "a" * 241, "a" * 9000])
def test_long_sources_defer_before_even_empty_model_output(text):
    instance, provider, budget, _, quota = extractor(replies=[response()])
    result = asyncio.run(instance.extract_batch([source(text)]))[0]
    assert (result.status, result.reason, result.changes) == ("defer", "evidence_scope_unsupported", ())
    assert result.retry_at == 2_000_086_410
    provider.generate.assert_not_awaited()
    budget.reserve.assert_not_called()
    quota.increment_and_check.assert_not_called()
    with pytest.raises(MemoryInputError, match="Complete source evidence"):
        parse_extraction_response(response(), [source(text)])
    with pytest.raises(MemoryInputError, match="Complete source evidence"):
        validate_request(build_request([source(text)]))


def test_filtering_sources_reindexes_only_provider_batch_and_restores_exact_refs():
    originals = [source("x" * 241), source(message_id="9"), source("y" * 241, message_id="10")]
    instance, provider, _, validate, _ = extractor()
    results = asyncio.run(instance.extract_batch(originals))
    assert [result.ref for result in results] == [item.ref for item in originals]
    assert [result.status for result in results] == ["defer", "complete", "defer"]
    sent = json.loads(provider.generate.call_args.args[0]["contents"][0]["parts"][0]["text"])["sources"]
    assert sent == [{"source_index": 0, "text": "I use Python.", "quoted_spans": []}]
    assert all(call.args == ([originals[1]],) for call in validate.await_args_list)
    assert results[1].changes[0].value == "Python"


def test_full_source_cannot_expand_across_a_quote_into_an_own_statement():
    original = source("Bob uses Rust. I use Python.", quoted_spans=((0, 14),))
    instance, provider, budget, _, _ = extractor()
    result = asyncio.run(instance.extract_batch([original]))[0]
    assert result.status == "defer" and result.reason == "evidence_scope_unsupported"
    provider.generate.assert_not_awaited()
    budget.reserve.assert_not_called()
    with pytest.raises(MemoryInputError):
        parse_extraction_response(response([fact()]), [original])


@pytest.mark.parametrize("nickname", ["Астра", "Ａｓｔｒａ", "Élodie", "Jo-Ann", "Astra  Lee"])
def test_original_name_spelling_survives_extractor_slot_and_persistent_writer(env, nickname):
    activate(env)
    text = "Please call me " + nickname + "."
    ref = env.repo.register_source(event(env, text=text))
    snapshot = replace(source(text), ref=ref)
    changes = parse_extraction_response(
        response([fact(text, value=nickname, field="communication_preferences", facet="name")]), [snapshot]
    )[0].changes
    assert changes[0].slot() == ("name", nickname)
    commit(env, ref, list(changes))
    stored = env.repo._read(CHAT, f"FACT#USER#{USER}#communication_preferences#name")
    assert stored["value"] == nickname
    assert stored["evidence"]["excerpt"] == text


@pytest.mark.parametrize(
    "nickname,value",
    [
        ("Астра", "Astra"),
        ("Astra", "astra"),
        ("Joanne", "Ann"),
        ("Jo-Ann", "Ann"),
        ("Jo－Ann", "Ann"),
        ("Jo﹣Ann", "Ann"),
        ("Jo–Ann", "Ann"),
        ("O‘Neil", "Neil"),
        ("O＇Neil", "Neil"),
        ("Ann_Lee", "Ann"),
        ("Ann2", "Ann"),
        ("Ann\u0301", "Ann"),
        ("Élodie", "Elodie"),
    ],
)
def test_name_transliteration_and_partial_name_cannot_be_committed(env, nickname, value):
    activate(env)
    text = "Please call me " + nickname + "."
    ref = env.repo.register_source(event(env, text=text))
    with pytest.raises(MemoryInputError):
        parse_extraction_response(
            response([fact(text, value=value, field="communication_preferences", facet="name")]), [source(text)]
        )
    with pytest.raises(MemoryInputError):
        commit(env, ref, [change(text, value=value, field="communication_preferences", facet="name")])
    assert list(env.repo._list(CHAT, "FACT#")) == []


def test_name_elsewhere_in_source_cannot_rescue_original_model_excerpt():
    original = source("Please call me Astra. I like short replies.")
    with pytest.raises(MemoryInputError):
        parse_extraction_response(
            response([fact("I like short replies.", value="Astra", field="communication_preferences", facet="name")]),
            [original],
        )


def test_explicit_name_correction_preserves_original_script_and_spaces(env):
    activate(env)
    text = "Please call me Astra."
    ref = env.repo.register_source(event(env, text=text))
    commit(env, ref, [change(text, value="Astra", field="communication_preferences", facet="name")])
    prior = env.repo.get_profile(CHAT, USER)[0]
    service = MemoryCommandService(
        env.repo, MemoryLifecycle(env.repo), authorize=lambda chat, actor, require_admin=False: actor == USER
    )
    env.clock.now += 1
    preferred = "Астра  Ли"
    correction = event(env, "99", "/memory correct selected@1 " + preferred, source_kind="confirmation")
    result = service.correct(
        CHAT,
        USER,
        {"fact_id": prior["fact_id"], "fact_version": int(prior["revision"])},
        source_event=correction,
        value=preferred,
    )
    assert result["state"] == "CORRECTED"
    stored = env.repo.get_profile(CHAT, USER)
    assert len(stored) == 1 and stored[0]["value"] == preferred
    assert stored[0]["evidence"]["excerpt"] == preferred
    assert stored[0]["evidence"]["source_ref"]["source_id"] == "99"


@pytest.mark.parametrize("value", [None, "", " Astra", "Astra ", "A" * 161])
def test_name_slot_cannot_normalize_invalid_input_into_a_valid_name(value):
    with pytest.raises(MemoryInputError):
        FactChange("communication_preferences", value, EvidenceSpan(0, 1), facet="name").slot()


def test_combining_spelling_keeps_existing_name_validation_without_silent_normalization():
    nickname = "E\u0301lodie"
    text = "Please call me " + nickname + "."
    with pytest.raises(MemoryInputError):
        parse_extraction_response(
            response([fact(text, value=nickname, field="communication_preferences", facet="name")]), [source(text)]
        )


def test_worker_keeps_oversized_work_pending_and_processes_short_neighbor_then_expires(env):
    activate(env)
    long_ref = env.repo.register_source(event(env, text="a" * 9000))
    short_ref = env.repo.register_source(event(env, message_id="9"))
    before = env.repo.get_work(CHAT, long_ref)
    instance, calls = worker(env, sizing_fn=input_upper_bytes)
    assert asyncio.run(instance.handle_records(records(long_ref, short_ref))) == {"batchItemFailures": []}
    pending = env.repo.get_work(CHAT, long_ref)
    assert pending["state"] == "PENDING" and pending["last_reason"] == "evidence_scope_unsupported"
    assert pending["expires_at"] == before["expires_at"] and pending["source_ref"] == before["source_ref"]
    assert pending["next_attempt_at"] == env.clock.now + 86400
    assert len(calls) == 1 and [item.ref for item in calls[0]] == [short_ref]
    assert env.repo.get_work(CHAT, short_ref)["state"] == "DONE"
    assert env.repo.coverage_snapshot(CHAT)["pending"] == 1
    env.clock.now = int(before["expires_at"]) - 10
    asyncio.run(instance.handle_records(records(long_ref)))
    assert env.repo.get_work(CHAT, long_ref)["next_attempt_at"] == before["expires_at"]
    env.clock.now += 10
    asyncio.run(instance.handle_records(records(long_ref)))
    assert env.repo.get_work(CHAT, long_ref)["state"] == "EXPIRED"
    assert len(calls) == 1
