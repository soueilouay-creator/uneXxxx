from __future__ import annotations

from typing import Any
import json
import time


class PostgresIdempotencyMixin:
    """Transactional claim/replay operations; requires the v8 migration 002 table."""

    def claim_idempotency(self, key: str, request_hash: str, task_id: str, lease_seconds: float = 660.0):
        now = time.time()
        with self._session() as connection:
            cursor = connection.execute(
                "INSERT INTO idempotency_claims(idempotency_key,request_hash,task_id,state,result_json,created_at,updated_at) "
                "VALUES(%s,%s,%s,'running',NULL,%s,%s) ON CONFLICT(idempotency_key) DO NOTHING RETURNING idempotency_key",
                (key, request_hash, task_id, now, now),
            )
            if cursor.fetchone() is not None:
                return {"state": "claimed", "task_id": task_id}
            row = connection.execute(
                "SELECT request_hash,task_id,state,result_json,updated_at FROM idempotency_claims "
                "WHERE idempotency_key=%s FOR UPDATE", (key,)
            ).fetchone()
            if not row:
                raise RuntimeError("Idempotency claim disappeared during acquisition.")
            if row["request_hash"] != request_hash:
                raise ValueError("Idempotency key reused with a different request payload.")
            if row["state"] == "running" and now - float(row["updated_at"]) > float(lease_seconds):
                cursor = connection.execute(
                    "UPDATE idempotency_claims SET task_id=%s,state='running',result_json=NULL,updated_at=%s "
                    "WHERE idempotency_key=%s AND state='running' AND updated_at=%s RETURNING task_id",
                    (task_id, now, key, row["updated_at"]),
                )
                if cursor.fetchone() is not None:
                    return {"state": "claimed", "task_id": task_id}
                row = connection.execute(
                    "SELECT task_id,state,result_json FROM idempotency_claims WHERE idempotency_key=%s",
                    (key,),
                ).fetchone()
            return {"state": row["state"], "task_id": row["task_id"],
                    "result": json.loads(row["result_json"]) if row.get("result_json") else None}

    def complete_idempotency(self, key: str, task_id: str, result: dict[str, Any]) -> bool:
        with self._session() as connection:
            cursor = connection.execute(
                "UPDATE idempotency_claims SET state='completed',result_json=%s,updated_at=%s "
                "WHERE idempotency_key=%s AND task_id=%s AND state='running'",
                (self._dump(result), time.time(), key, task_id),
            )
        return cursor.rowcount == 1

    def fail_idempotency(self, key: str, task_id: str, result: dict[str, Any]) -> bool:
        with self._session() as connection:
            cursor = connection.execute(
                "UPDATE idempotency_claims SET state='failed',result_json=%s,updated_at=%s "
                "WHERE idempotency_key=%s AND task_id=%s AND state='running'",
                (self._dump(result), time.time(), key, task_id),
            )
        return cursor.rowcount == 1
