"""Authenticated local archives with explicit seven-day retention deadlines."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .policy import CleanupError, canonical, untagged

RETENTION_SECONDS = 7 * 86400
MAGIC = "zerde-legacy-cleanup-v1"


def secure_directory(directory, *, repository_root):
    directory = Path(directory).resolve()
    repository_root = Path(repository_root).resolve()
    if (
        directory == repository_root
        or repository_root in directory.parents
        or any((parent / ".git").exists() for parent in (directory, *directory.parents))
    ):
        raise CleanupError("archive_must_be_outside_repository")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    current = directory.stat()
    if not stat.S_ISDIR(current.st_mode) or current.st_uid != os.getuid() or current.st_mode & 0o077:
        raise CleanupError("archive_directory_requires_owner_only_permissions")
    return directory


def load_key(key_path):
    key_path = Path(key_path)
    metadata = key_path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_mode & 0o077
        or metadata.st_size != 32
    ):
        raise CleanupError("key_requires_owned_private_32_byte_file")
    fd = os.open(key_path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        key = stream.read(33)
    if len(key) != 32:
        raise CleanupError("invalid_key_length")
    return key


def _safe_path(directory, name):
    if not name or Path(name).name != name or not name.endswith(".zenc"):
        raise CleanupError("invalid_archive_filename")
    return directory / name


def seal(directory, name, value, key, *, now, expires_at=None, replace=False):
    directory = Path(directory)
    metadata = directory.stat()
    if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
        raise CleanupError("archive_directory_requires_owner_only_permissions")
    path = _safe_path(directory, name)
    if len(key) != 32:
        raise CleanupError("invalid_key_length")
    expiry = now + RETENTION_SECONDS if expires_at is None else expires_at
    if not now < expiry <= now + RETENTION_SECONDS:
        raise CleanupError("invalid_archive_retention")
    header = {
        "format": MAGIC,
        "created_at": now,
        "expires_at": expiry,
        "content_sha256": hashlib.sha256(canonical(value)).hexdigest(),
    }
    aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    nonce = os.urandom(12)
    encrypted = AESGCM(key).encrypt(nonce, canonical(value), aad)
    payload = json.dumps(
        {"header": header, "nonce": nonce.hex(), "ciphertext": encrypted.hex()}, separators=(",", ":")
    ).encode()
    temporary = directory / ("." + uuid.uuid4().hex + ".zenc") if replace else path
    if replace and path.exists():
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
            raise CleanupError("unsafe_existing_archive")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    if replace:
        os.replace(temporary, path)
    directory_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest(), "expires_at": expiry}


def open_archive(path, key, *, now, allow_expired=False):
    path = Path(path)
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
        raise CleanupError("unsafe_archive_permissions")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        encoded = json.load(stream)
    header = encoded["header"]
    if (
        header.get("format") != MAGIC
        or type(header.get("created_at")) is not int
        or type(header.get("expires_at")) is not int
        or header["created_at"] > now
        or not 0 < header["expires_at"] - header["created_at"] <= RETENTION_SECONDS
    ):
        raise CleanupError("invalid_archive_header")
    if not allow_expired and now >= header["expires_at"]:
        raise CleanupError("archive_expired")
    aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    try:
        raw = AESGCM(key).decrypt(bytes.fromhex(encoded["nonce"]), bytes.fromhex(encoded["ciphertext"]), aad)
    except Exception:
        raise CleanupError("archive_authentication_failed") from None
    if hashlib.sha256(raw).hexdigest() != header["content_sha256"]:
        raise CleanupError("archive_digest_mismatch")
    return untagged(json.loads(raw)), header


def expire(path, key, *, now, expected_digest, apply=False):
    _, header = open_archive(path, key, now=now, allow_expired=True)
    if header["content_sha256"] != expected_digest or now < header["expires_at"]:
        raise CleanupError("archive_expiry_not_authorized")
    if apply:
        Path(path).unlink()
        directory_fd = os.open(Path(path).parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    return {"expired": True, "removed": bool(apply), "physical_disk_erasure_proven": False}
