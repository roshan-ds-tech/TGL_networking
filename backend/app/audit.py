"""Append-only audit trail.

`record()` adds an `audit_log` row to the CALLER'S session, so the entry commits
(or rolls back) together with the change it describes: there is never a change
without a record or a record without a change.

Tamper resistance, in three layers:
  1. this module only ever inserts;
  2. an ORM guard below refuses to update or delete an AuditLog;
  3. database triggers (database.install_audit_triggers, migration 0008) refuse
     UPDATE and DELETE even for someone with raw SQL access through the app's role.

Never put secrets in an audit entry. `_clean()` strips anything that looks like
a credential and truncates long values, but callers should pass only the fields
that describe the change (ids, statuses, amounts), not whole request bodies.
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Admin, AuditLog, User
from .observability import current_request_id

_SECRET_KEY = re.compile(r"pass(word)?|secret|token|api[_-]?key|authorization|cookie|card|cvv|otp|csrf|hash", re.I)
_MAX_STR = 500


def _clean(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "…"
    if isinstance(value, dict):
        return {str(k): ("[redacted]" if _SECRET_KEY.search(str(k)) else _clean(v, depth + 1)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(v, depth + 1) for v in list(value)[:50]]
    if isinstance(value, str):
        return value if len(value) <= _MAX_STR else value[: _MAX_STR - 1] + "…"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:_MAX_STR]


def _dump(value: Any) -> str | None:
    return None if value is None else json.dumps(_clean(value), ensure_ascii=False, default=str, sort_keys=True)


def record(
    db: AsyncSession,
    *,
    actor: User | Admin | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    actor_role: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    reason: str | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    if isinstance(actor, Admin):
        actor_type, role = "ADMIN", "admin"
    elif isinstance(actor, User):
        actor_type, role = "USER", actor_role or "member"
    else:
        actor_type, role = "SYSTEM", actor_role or "system"
    row = AuditLog(
        actor_type=actor_type,
        actor_id=getattr(actor, "id", None),
        actor_role=role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before_json=_dump(before),
        after_json=_dump(after),
        reason=(reason or None) and reason[:2000],
        request_id=current_request_id(),
        metadata_json=_dump(metadata),
    )
    db.add(row)
    return row


@event.listens_for(AuditLog, "before_update")
@event.listens_for(AuditLog, "before_delete")
def _refuse_change(mapper, connection, target):  # pragma: no cover - exercised by tests
    raise RuntimeError("audit_log is append-only")
