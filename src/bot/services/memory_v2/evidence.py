"""Conservative source bounds; this does not infer facts or sentence meaning."""

from .models import EvidenceSpan

EVIDENCE_DEFER_REASON = "evidence_scope_unsupported"
EVIDENCE_RETRY_SECONDS = 86400


def complete_evidence_span(text: str, quoted_spans) -> EvidenceSpan | None:
    """Keep all source qualifiers without guessing sentence or line boundaries.

    Inputs have already passed the source contract. Unsupported bounds remain
    pending, including a short self-statement inside a longer/quoted source.
    """
    start = len(text) - len(text.lstrip())
    end = len(text.rstrip())
    if not 0 < end - start <= 240:
        return None
    if any(start < quote_end and end > quote_start for quote_start, quote_end in quoted_spans):
        return None
    return EvidenceSpan(start, end)
