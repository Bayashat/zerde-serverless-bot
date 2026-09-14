# Memory quality follow-up after the interrupted real baseline

These are local correctness fixes following the 2026-09-11 signed Gemini baseline.
That immutable run remains **56 EXECUTED / 184 UNSUPPORTED, NOT_VERIFIED**. Its
gold, scorer and provider responses are unchanged. Regression tests below use new
synthetic examples; they do not establish improved real-model quality or deployment.

The sole public-content policy in `memory_v2/safety.py` distinguishes the Kazakh
handbook noun `нұсқаулық` (including its common inflected/spelling forms) from the
instruction stem `нұсқау`. Instruction words remain rejected. A handbook mention
does not exempt the message: control language in another sentence, secrets,
contacts, hidden controls and existing unsafe-content checks still reject it.
This lexical guard is not a semantic proof against every prompt injection. Allowed
text stays untrusted, with the original bytes and evidence offsets; ingestion,
extraction and the final fact writer keep using the same policy.

`memory_v2/answer_scope.py` recognizes complete, simple personal education questions
in a bounded set of Kazakh, Russian, English, Chinese and mixed forms. It does not
identify people or inspect evaluation metadata. Quotes, multiple questions,
combined topics, unfamiliar names/wording and ambiguous requests retain the ordinary
selection path. For a recognized question, the existing answer owner checks the
validated selection before binding facts: selecting a non-education field, a mixed
selection or `general` becomes one normal `unknown` answer. It never renumbers
indices, retries the provider for this semantic mismatch, or invokes plain fallback.
The normal lease, deletion checks and durable send receipt still apply. Deterministic
profile/about output is unaffected.

This field check prevents occupation from answering an education question. It does
not establish that any education value proves a requested degree level, institution,
completion date or qualification, and it does not claim to understand every natural
language question. Identity, source validity and supported selection remain separate
requirements. The model prompt and generation configuration are unchanged.

Tests exercise the real Moto source/work/fact/lease/receipt owners, with synthetic
provider and Telegram endpoints: a new handbook project survives extraction without
text rewriting; editing it into an instruction invalidates the fact; direct unsafe
writer output fails; a wrong-field selection settles once and sends unknown once;
forget and unknown-delivery replay protections remain enforced. Real model and
production acceptance are separate follow-up gates.
