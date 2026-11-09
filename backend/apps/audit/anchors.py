"""External storage for audit-chain head anchors."""

import fcntl
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings


class AuditAnchorStoreError(Exception):
    """The external anchor store is missing, unreadable, or malformed."""


@dataclass(frozen=True)
class AuditAnchor:
    """One organization's audit head at the moment it was anchored."""

    organization_id: str
    head_event_id: int
    head_hash: str
    anchored_at: datetime

    def as_dict(self) -> dict:
        return {
            "organization_id": self.organization_id,
            "head_event_id": self.head_event_id,
            "head_hash": self.head_hash,
            "timestamp": self.anchored_at.astimezone(timezone.utc).isoformat(
                timespec="microseconds"
            ),
        }


class AuditAnchorStore:
    """Interface for an append-only store that lives outside the database."""

    def append(self, anchor: AuditAnchor) -> None:
        raise NotImplementedError

    def latest(self, organization_id: str) -> AuditAnchor | None:
        raise NotImplementedError


def _anchor_from_dict(data: dict) -> AuditAnchor:
    try:
        anchored_at = datetime.fromisoformat(data["timestamp"])
        if anchored_at.tzinfo is None:
            anchored_at = anchored_at.replace(tzinfo=timezone.utc)
        return AuditAnchor(
            organization_id=str(data["organization_id"]),
            head_event_id=int(data["head_event_id"]),
            head_hash=str(data["head_hash"]),
            anchored_at=anchored_at,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AuditAnchorStoreError("Malformed audit anchor record.") from exc


class JsonlAuditAnchorStore(AuditAnchorStore):
    """Append-only JSON Lines file, one anchor record per line."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, anchor: AuditAnchor) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(anchor.as_dict(), sort_keys=True, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                handle.write(line)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def latest(self, organization_id: str) -> AuditAnchor | None:
        if not self.path.exists():
            return None
        latest = None
        with self.path.open("r", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_SH)
            try:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise AuditAnchorStoreError(
                            "Malformed audit anchor record."
                        ) from exc
                    anchor = _anchor_from_dict(data)
                    if anchor.organization_id == str(organization_id):
                        latest = anchor
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
        return latest


def get_anchor_store() -> AuditAnchorStore | None:
    """Return the configured anchor store, or None when anchoring is disabled."""
    configured = getattr(settings, "AUDIT_ANCHOR_PATH", "")
    path = str(configured).strip() if configured else ""
    if not path:
        return None
    return JsonlAuditAnchorStore(path)
