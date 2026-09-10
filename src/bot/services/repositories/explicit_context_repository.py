"""Compatibility overlay: retain business settings, retire legacy reply/album IO."""

from services.memory_v2.media_ephemeral import EphemeralMediaRepository
from services.memory_v2.models import MemoryUnavailable, SourceRef, positive_id

from .group_memory import GroupMemoryRepository


class ExplicitContextRepository(GroupMemoryRepository):
    def __init__(self, table_name=None, *, memory_v2_repo=None):
        super().__init__(table_name)
        self.ephemeral_media = EphemeralMediaRepository(memory_v2_repo) if memory_v2_repo is not None else None

    def record_agent_reply(self, **kwargs):
        """V2 answer receipts have their own owner; never write AGENT_REPLY."""

    def get_agent_reply_explanation(self, chat_id, *, bot_message_id=None):
        return {}

    def count_recent_agent_replies(self, chat_id, *, since_epoch, limit=25):
        return 0

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
