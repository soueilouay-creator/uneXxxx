from __future__ import annotations

import re
import time
from typing import Any, Callable
from urllib.parse import urlsplit

from .models import ApprovalExecutionBinding


class PostgresApprovalLedger:
    """Atomically consume a GitHub approval and optionally bind it to one execution."""

    DIGEST = re.compile(r"^[0-9a-f]{64}$")

    def __init__(self, dsn: str, *, connect_factory: Callable[[], Any] | None = None):
        parsed = urlsplit(str(dsn or "").strip())
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
            raise ValueError("A valid PostgreSQL DATABASE_URL is required for the approval ledger.")
        self._dsn = str(dsn).strip()
        self._connect_factory = connect_factory

    def _connect(self):
        if self._connect_factory is not None:
            return self._connect_factory()
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError:
            raise RuntimeError("psycopg 3 is required for the PostgreSQL approval ledger.") from None
        try:
            return psycopg.connect(self._dsn, row_factory=dict_row, connect_timeout=5)
        except Exception as exc:
            raise RuntimeError(f"PostgreSQL approval ledger unavailable ({type(exc).__name__}).") from None

    def consume_once(self, approval_id: str, action_digest: str) -> bool:
        if (not isinstance(approval_id, str) or not approval_id.strip()
                or not isinstance(action_digest, str) or not self.DIGEST.fullmatch(action_digest)):
            return False
        connection = self._connect()
        try:
            cursor = connection.execute(
                "INSERT INTO consumed_approvals(approval_id,action_digest,consumed_at) "
                "VALUES(%s,%s,%s) ON CONFLICT(approval_id) DO NOTHING RETURNING approval_id",
                (approval_id, action_digest, time.time()),
            )
            row = cursor.fetchone()
            connection.commit()
            return row is not None
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def consume_once_bound(self, approval_id: str, action_digest: str,
                           permission: str, binding: ApprovalExecutionBinding) -> bool:
        if (not isinstance(approval_id, str) or not approval_id.strip()
                or not isinstance(action_digest, str) or not self.DIGEST.fullmatch(action_digest)
                or not isinstance(permission, str) or not permission.strip()
                or not isinstance(binding, ApprovalExecutionBinding)):
            return False
        connection = self._connect()
        now = time.time()
        try:
            consumed = connection.execute(
                "INSERT INTO consumed_approvals(approval_id,action_digest,consumed_at) "
                "VALUES(%s,%s,%s) ON CONFLICT(approval_id) DO NOTHING RETURNING approval_id",
                (approval_id, action_digest, now),
            ).fetchone()
            if consumed is None:
                connection.commit()
                return False
            bound = connection.execute(
                "INSERT INTO approval_execution_bindings("
                "approval_id,action_digest,permission,execution_id,task_id,workflow_id,stage_key,consumed_at"
                ") VALUES(%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING RETURNING approval_id",
                (approval_id, action_digest, permission, binding.execution_id, binding.task_id,
                 binding.workflow_id, binding.stage_key, now),
            ).fetchone()
            if bound is None:
                connection.rollback()
                return False
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_consumed_binding(self, approval_id: str) -> dict[str, Any] | None:
        if not isinstance(approval_id, str) or not approval_id.strip():
            return None
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT approval_id,action_digest,permission,execution_id,task_id,workflow_id,stage_key,consumed_at "
                "FROM approval_execution_bindings WHERE approval_id=%s",
                (approval_id,),
            ).fetchone()
            connection.commit()
            return dict(row) if row is not None else None
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
