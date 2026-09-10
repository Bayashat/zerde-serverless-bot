"""Explicit prerecorded synthetic responses; no gold input and no network fallback."""

import copy
import hashlib
import json

from .contract import EvaluationInputError, read_jsonl


class MissingFixture(EvaluationInputError):
    pass


def text_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def gemini_payload(document):
    return {
        "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(document)}]}}],
        "usageMetadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 100,
            "thoughtsTokenCount": 0,
            "totalTokenCount": 200,
        },
    }


class FixtureCatalog:
    def __init__(self, rows):
        self.rows = {}
        for row in rows:
            if (
                not isinstance(row, dict)
                or set(row) != {"kind", "input_sha256", "input_text", "response"}
                or row["kind"] not in {"extraction", "answer", "confirmation"}
                or not isinstance(row["input_sha256"], str)
                or len(row["input_sha256"]) != 64
                or not isinstance(row["input_text"], str)
                or text_hash(row["input_text"]) != row["input_sha256"]
                or not isinstance(row["response"], dict)
            ):
                raise EvaluationInputError("Invalid independent provider fixture")
            key = (row["kind"], row["input_sha256"])
            if key in self.rows:
                raise EvaluationInputError("Duplicate provider fixture")
            self.rows[key] = copy.deepcopy(row["response"])

    @classmethod
    def read(cls, path):
        return cls(read_jsonl(path))

    def get(self, kind, text):
        key = kind, text_hash(text)
        if key not in self.rows:
            raise MissingFixture("No independent provider fixture for this input")
        return copy.deepcopy(self.rows[key])


class FixtureProvider:
    """Fixtures store per-source facts / answer field-selection policies, not labels.

    Only indices are rebound to the actual request. Missing entries are explicit
    coverage failures, not successful empty extraction or abstention.
    """

    def __init__(self, catalog, *, kind, trace):
        self.catalog, self.kind, self.trace = catalog, kind, trace
        self.failed = False
        self.missing = []

    async def generate(self, request):
        document = json.loads(request["contents"][0]["parts"][0]["text"])
        self.trace.append(copy.deepcopy(request))
        if self.failed:
            raise TimeoutError("Synthetic provider failure")
        try:
            if self.kind == "extraction":
                sources = []
                for source in document["sources"]:
                    response = self.catalog.get("extraction", source["text"])
                    if set(response) != {"facts"}:
                        raise EvaluationInputError("Extraction fixture requires explicit facts")
                    sources.append({"source_index": source["source_index"], **response})
                return gemini_payload({"sources": sources})
            response = self.catalog.get("answer", document["question"])
            if set(response) != {"fields"} or not isinstance(response["fields"], list):
                raise EvaluationInputError("Answer fixture requires explicit requested fields")
            indices = [
                fact["index"]
                for fact in document["facts"]
                if "*" in response["fields"] or fact["field"] in response["fields"]
            ]
            return gemini_payload({"mode": "facts" if indices else "unknown", "indices": indices[:16]})
        except MissingFixture:
            self.missing.append({"kind": self.kind, "request_sha256": text_hash(json.dumps(request, sort_keys=True))})
            raise
