#!/usr/bin/env python3
"""Import scraped exam questions into DynamoDB.

Usage:
    uv run python dev/scrapers/import_questions.py \\
        dev/scrapers/output/clf-c02-all.json \\
        zerde-serverless-quiz-prod \\
        --source aws-clf-c02 --category cloud

    Add --dry-run to preview without writing.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

import boto3

# CLF-C02 is a foundation exam. Keep imported questions in the lower tiers.
_DOMAIN_DIFFICULTY: dict[str, str] = {
    "domain 1": "easy",  # Cloud Concepts
    "domain 2": "easy_medium",  # Security and Compliance
    "domain 3": "easy_medium",  # Cloud Technology and Services
    "domain 4": "easy",  # Billing, Pricing, and Support
}

_SUBTOPIC_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("iam", ("iam", "identity", "access management", "permission", "policy", "role")),
    ("security", ("security", "encryption", "compliance", "guardduty", "shield", "waf", "kms")),
    ("storage", ("s3", "storage", "ebs", "efs", "glacier", "backup")),
    ("compute", ("ec2", "lambda", "elastic beanstalk", "auto scaling", "compute")),
    ("networking", ("vpc", "subnet", "route table", "cloudfront", "load balancer", "dns", "route 53")),
    ("database", ("rds", "dynamodb", "aurora", "redshift", "database")),
    ("monitoring", ("cloudwatch", "cloudtrail", "config", "monitoring", "logging")),
    ("billing", ("billing", "pricing", "cost", "budget", "support plan", "trusted advisor")),
    ("migration", ("migration", "snowball", "datasync", "transfer")),
)


def _map_difficulty(domain_name: str) -> str:
    domain_lower = domain_name.lower()
    for key, diff in _DOMAIN_DIFFICULTY.items():
        if key in domain_lower:
            return diff
    return "easy_medium"


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _question_fingerprint(q: dict) -> str:
    text = " ".join(
        [
            _normalize_text(q.get("question", "")),
            *[_normalize_text(opt) for opt in q.get("options", [])],
        ]
    )
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _domain_slug(domain_name: str) -> str:
    value = _normalize_text(domain_name)
    value = re.sub(r"^domain\s+\d+:\s*", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "foundation"


def _map_subtopic(q: dict) -> str:
    haystack = _normalize_text(
        " ".join(
            [
                q.get("domain", ""),
                q.get("question", ""),
                q.get("explanation", ""),
                " ".join(q.get("options", [])),
            ]
        )
    )
    for subtopic, keywords in _SUBTOPIC_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return subtopic
    return _domain_slug(q.get("domain", ""))


def import_questions(
    json_path: str,
    table_name: str,
    source: str,
    category: str,
    dry_run: bool = False,
) -> None:
    questions = json.loads(Path(json_path).read_text(encoding="utf-8"))
    pk = f"BANK#{category}#{source}"

    skipped_bad: list[str] = []
    skipped_long: list[str] = []

    valid = []
    for q in questions:
        if len(q.get("options", [])) != 4:
            skipped_bad.append(q["uuid"])
            continue
        if int(q.get("correct_option_id", -1)) not in range(4):
            skipped_bad.append(q["uuid"])
            continue
        if not q.get("question", "").strip():
            skipped_bad.append(q["uuid"])
            continue
        # Telegram limits: question ≤ 300 chars, option ≤ 100 chars
        if len(q["question"]) > 300:
            skipped_long.append(q["uuid"])
            continue
        if any(len(opt) > 100 for opt in q["options"]):
            skipped_long.append(q["uuid"])
            continue
        valid.append(q)

    print(f"Source : {source}")
    print(f"Table  : {table_name}")
    print(f"PK     : {pk}")
    print(f"Total  : {len(questions)}")
    print(f"Valid  : {len(valid)}")
    print(f"Skipped (malformed) : {len(skipped_bad)}")
    print(f"Skipped (too long)  : {len(skipped_long)}")

    if dry_run:
        print("\n--- DRY RUN: first 3 items ---")
        for q in valid[:3]:
            item = _build_item(pk, q, source, category)
            print(json.dumps(item, ensure_ascii=False, indent=2)[:400])
            print("...")
        return

    table = boto3.resource("dynamodb").Table(table_name)
    written = 0
    with table.batch_writer() as batch:
        for q in valid:
            batch.put_item(Item=_build_item(pk, q, source, category))
            written += 1

    print(f"\nDone: {written} questions written to DynamoDB.")


def _build_item(pk: str, q: dict, source: str, category: str) -> dict:
    return {
        "PK": pk,
        "SK": f"Q#{q['uuid']}",
        "uuid": q["uuid"],
        "source": source,
        "category": category,
        "domain": q.get("domain", ""),
        "difficulty": _map_difficulty(q.get("domain", "")),
        "difficulty_band": "foundation",
        "subtopic": _map_subtopic(q),
        "fingerprint": _question_fingerprint(q),
        "question": q["question"],
        "options": q["options"],
        "correct_option_id": int(q["correct_option_id"]),
        "explanation": q.get("explanation", ""),
        "exam_name": q.get("exam_name", ""),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import exam questions into DynamoDB.")
    parser.add_argument("json_path", help="Path to the merged JSON file")
    parser.add_argument("table_name", help="DynamoDB table name")
    parser.add_argument("--source", default="aws-clf-c02", help="Source identifier")
    parser.add_argument("--category", default="cloud", help="Category this bank belongs to")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    import_questions(args.json_path, args.table_name, args.source, args.category, args.dry_run)
