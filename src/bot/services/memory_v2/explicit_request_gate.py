"""Body-free cutover/delete fences for plain or media explicit SQS requests."""

from .models import MemoryInputError, MemoryUnavailable, positive_id

_FIELDS = {"schema", "epoch", "control_revision", "actor_generation", "requested_at", "request_source_version"}


def capture(repo, chat_id, actor_user_id, message_id, *, requested_at):
    actor, source_id = positive_id(actor_user_id), positive_id(message_id)
    if type(requested_at) is not int or not repo.now() - 86400 <= requested_at <= repo.now():
        raise MemoryInputError("Explicit request requires its original recent send time")
    control = repo.get_control(chat_id)
    subject = repo.get_subject(chat_id, actor)
    observation = repo.get_observation(chat_id, source_id)
    if control["state"] == "STOPPING" or subject.get("state", "ACTIVE") != "ACTIVE":
        raise MemoryUnavailable("Explicit request overlaps memory erasure")
    if requested_at < max(int(control.get("learning_started_at", 0)), int(control.get("purged_through", -1)) + 1):
        raise MemoryUnavailable("Explicit request predates this group generation")
    if subject and requested_at < int(subject.get("learning_started_at", 0)):
        raise MemoryUnavailable("Explicit request predates this actor generation")
    source_version = 0
    if observation:
        if (
            observation.get("deleted")
            or observation.get("ambiguous")
            or observation.get("edited_at")
            or observation.get("actor_user_id") != actor
            or observation.get("original_sent_at") != requested_at
            or observation.get("epoch") != control["epoch"]
        ):
            raise MemoryUnavailable("Explicit request source is obsolete")
        source_version = int(observation["revision"])
    return {
        "schema": 1,
        "epoch": control["epoch"],
        "control_revision": int(control["revision"]),
        "actor_generation": int(subject.get("generation", 0)),
        "requested_at": requested_at,
        "request_source_version": source_version,
    }


def validate(repo, chat_id, actor_user_id, message_id, gate):
    if not isinstance(gate, dict) or set(gate) != _FIELDS or type(gate.get("schema")) is not int or gate["schema"] != 1:
        raise MemoryUnavailable("Old explicit request protocol is retired")
    if any(type(gate[key]) is not int or gate[key] < 0 for key in _FIELDS - {"schema", "epoch"}):
        raise MemoryInputError("Invalid explicit request fence")
    current = capture(repo, chat_id, actor_user_id, message_id, requested_at=gate["requested_at"])
    if current != gate:
        raise MemoryUnavailable("Explicit request belongs to an old source or control generation")
    return True


def capture_configured(chat_id, actor_user_id, message_id, requested_at):
    from .runtime import get_memory_v2_repo

    repo = get_memory_v2_repo()
    return capture(repo, chat_id, actor_user_id, message_id, requested_at=requested_at) if repo else None


def validate_configured(body):
    from .runtime import get_memory_v2_repo

    repo = get_memory_v2_repo()
    if repo is None:
        return True
    return validate(
        repo,
        body.get("chat_id"),
        body.get("requester_user_id"),
        body.get("reply_to_message_id"),
        body.get("request_gate"),
    )
