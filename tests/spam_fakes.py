"""Stateful moderation store fake for service-level retry and race scenarios."""

import copy
import time
import uuid

import pytest
from services.repositories.spam import SpamLeaseBusyError, SpamRepository


class MemorySpamRepository(SpamRepository):
    def __init__(self):
        self.rows = {}
        self.ban_count = 0

    def get(self, case_id):
        return copy.deepcopy(self.rows.get(case_id, {}))

    def _create(self, case_id, fields):
        self.rows.setdefault(
            case_id,
            {"case_id": case_id, "state": "pending", "ttl": int(time.time()) + 30 * 86400, **copy.deepcopy(fields)},
        )
        return self.get(case_id)

    def claim(self, case_id):
        row = self.rows[case_id]
        if row.get("lease_owner"):
            raise SpamLeaseBusyError("busy")
        owner = uuid.uuid4().hex
        row["lease_owner"] = owner
        return owner, self.get(case_id)

    def update(self, case_id, owner, fields, *, remove_ttl=False):
        assert self.rows[case_id]["lease_owner"] == owner
        self.rows[case_id].update(copy.deepcopy(fields))
        if remove_ttl:
            self.rows[case_id].pop("ttl", None)

    def release(self, case_id, owner):
        row = self.rows[case_id]
        if row.get("lease_owner") == owner:
            row.pop("lease_owner")

    def confirm_ban(self, case_id, owner, chat_id):
        row = self.rows[case_id]
        assert row["lease_owner"] == owner
        assert row["state"] != "banned"
        row["state"] = "banned"
        row.pop("lease_owner")
        self.ban_count += 1


@pytest.fixture(autouse=True)
def spam_repo(monkeypatch):
    from services.handlers import spam_review
    from services.spam import enforcer, processor

    repo = MemorySpamRepository()
    for module in (enforcer, processor, spam_review):
        monkeypatch.setattr(module, "SpamRepository", lambda: repo)
    return repo
