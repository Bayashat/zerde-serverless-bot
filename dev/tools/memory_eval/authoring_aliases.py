"""Finite, independently reviewed gold aliases; never used by a provider/runtime."""

import json
from pathlib import Path

_DOCUMENT = json.loads(Path(__file__).with_name("accepted_values.json").read_text())
APPROVED_PROPOSAL_SHA256 = _DOCUMENT["approved_proposal_sha256"]
_ALIASES = {(row["language"], row["field"], row["facet"], row["canonical_value"]): row for row in _DOCUMENT["entries"]}


def accepted_values_for(language, text, field, facet, value):
    """Only the reviewed source template may use its explicitly approved forms."""
    row = _ALIASES.get((language, field, facet, value))
    if row is None or text not in row["source_texts"]:
        return []
    return list(row["accepted_values"])
