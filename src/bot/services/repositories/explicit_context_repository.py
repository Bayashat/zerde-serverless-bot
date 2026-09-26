"""Explicit media facade backed exclusively by the V2 ephemeral media owner."""

from services.memory_v2.media_ephemeral import EphemeralMediaRepository
from services.memory_v2.models import MemoryUnavailable, SourceRef, positive_id


class ExplicitContextRepository:
    def __init__(self, *, memory_v2_repo=None):
        self.ephemeral_media = EphemeralMediaRepository(memory_v2_repo) if memory_v2_repo is not None else None

    def store_media_group_item(self, *, chat_id, media_group_id, message_id, media_ref, created_at=None):
        if self.ephemeral_media is None:
            raise MemoryUnavailable("Ephemeral album storage is not configured")
        source_id = positive_id(message_id)
        observation = self.ephemeral_media.repo.get_observation(chat_id, source_id)
        if not observation:
            raise MemoryUnavailable("Album source was not observed")
        self.ephemeral_media.store(
            chat_id=chat_id,
            media_group_id=media_group_id,
            source_ref=SourceRef(source_id, int(observation["revision"]), observation["epoch"]),
            actor_user_id=positive_id(media_ref.get("source_user_id")),
            created_at=created_at,
            media_ref=media_ref,
        )

    def get_media_group_refs(self, chat_id, media_group_id):
        if self.ephemeral_media is None:
            return []
        return self.ephemeral_media.get_refs(chat_id, media_group_id)
