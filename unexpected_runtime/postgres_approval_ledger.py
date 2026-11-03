from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlsplit


class PostgresApprovalLedger:
    """Atomically consume a GitHub approval exactly once in PostgreSQL."""

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
        if not isinstance(approval_id, str) or not approval_id or not isinstance(action_digest, str) or len(action_digest) != 64:
            return False
        connection = self._connect()
        try:
            cursor = connection.execute(
                "INSERT INTO consumed_approvals(approval_id,action_digest,consumed_at) "
                "VALUES(%s,%s,EXTRACT(EPOCH FROM clock_timestamp())) "
                "ON CONFLICT(approval_id) DO NOTHING RETURNING approval_id",
                (approval_id, action_digest),
            )
            row = cursor.fetchone()
            connection.commit()
            return row is not None
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
