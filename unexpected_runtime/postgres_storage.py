from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator
from urllib.parse import urlsplit
from .postgres_idempotency import PostgresIdempotencyMixin
import json
import time
import uuid


class PostgresStorageError(RuntimeError):
    pass


class PostgresStateStore(PostgresIdempotencyMixin):
    """PostgreSQL implementation of the runtime StateStore contract.

    The schema is managed by checked-in migrations. This class never creates,
    drops, or silently repairs production tables.
    """

    backend = "postgres"

    def __init__(self, dsn: str, *, connect_factory: Callable[[], Any] | None = None,
                 validate_schema: bool = True):
        parsed = urlsplit(str(dsn or "").strip())
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
            raise PostgresStorageError("A valid PostgreSQL DATABASE_URL is required.")
        self._dsn = str(dsn).strip()
        self._connect_factory = connect_factory
        if validate_schema:
            try:
                with self._session() as connection:
                    row = connection.execute(
                        "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
                    ).fetchone()
                    if not row or int(row["version"]) < 2:
                        raise PostgresStorageError("PostgreSQL v8 migrations are not initialized; migration 002 is required.")
            except PostgresStorageError:
                raise
            except Exception as exc:
                raise PostgresStorageError(
                    f"PostgreSQL schema check failed ({type(exc).__name__}); no local fallback was used."
                ) from None

    def _connect(self):
        if self._connect_factory is not None:
            return self._connect_factory()
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError:
            raise PostgresStorageError("psycopg 3 is required for PostgreSQL storage.") from None
        try:
            return psycopg.connect(self._dsn, row_factory=dict_row, connect_timeout=5)
        except Exception as exc:
            raise PostgresStorageError(
                f"PostgreSQL connection failed ({type(exc).__name__}); credentials were not disclosed."
            ) from None

    @contextmanager
    def _session(self) -> Iterator[Any]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            try:
                connection.rollback()
            finally:
                raise
        finally:
            connection.close()

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @staticmethod
    def _bounded(limit: int, maximum: int = 1000) -> int:
        return max(1, min(int(limit), maximum))

    def close(self):
        return None

    def check_health(self) -> bool:
        with self._session() as connection:
            row = connection.execute("SELECT 1 AS ok").fetchone()
            return bool(row and row.get("ok") == 1)

    def log_event(self, event_type: str, task_id: str | None = None,
                  agent_id: str | None = None, payload: dict[str, Any] | None = None):
        with self._session() as connection:
            connection.execute(
                "INSERT INTO events(ts,task_id,agent_id,event_type,payload_json) VALUES(%s,%s,%s,%s,%s)",
                (time.time(), task_id, agent_id, event_type, self._dump(payload or {})),
            )

    def events(self, limit: int = 100):
        with self._session() as connection:
            rows = connection.execute(
                "SELECT event_id,ts,task_id,agent_id,event_type,payload_json FROM events ORDER BY event_id DESC LIMIT %s",
                (self._bounded(limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_task_events(self, task_id: str, *, after_event_id: int = 0, limit: int = 100):
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id must be a non-empty string.")
        if isinstance(after_event_id, bool) or not isinstance(after_event_id, int) or after_event_id < 0:
            raise ValueError("after_event_id must be a non-negative integer.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 201:
            raise ValueError("limit must be an integer between 1 and 201.")
        with self._session() as connection:
            rows = connection.execute(
                "SELECT event_id,ts,task_id,agent_id,event_type,payload_json FROM events "
                "WHERE task_id=%s AND event_id>%s ORDER BY event_id ASC LIMIT %s",
                (task_id, after_event_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def enqueue(self, request):
        payload = {
            "task_id": request.task_id, "agent_id": request.agent_id,
            "objective": request.objective, "inputs": request.inputs,
            "required_permissions": list(request.required_permissions),
            "deadline_seconds": request.deadline_seconds, "max_steps": request.max_steps,
            "idempotency_key": request.idempotency_key, "source_refs": list(request.source_refs),
            "provider_route": getattr(request, "provider_route", None),
            "requested_skill_ids": list(getattr(request, "requested_skill_ids", ())),
            "parent_task_id": getattr(request, "parent_task_id", None),
            "created_at": request.created_at,
        }
        now = time.time()
        with self._session() as connection:
            connection.execute(
                "INSERT INTO tasks(task_id,agent_id,status,payload_json,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s)",
                (request.task_id, request.agent_id, "queued", self._dump(payload), now, now),
            )
            connection.execute(
                "INSERT INTO events(ts,task_id,agent_id,event_type,payload_json) VALUES(%s,%s,%s,%s,%s)",
                (now, request.task_id, request.agent_id, "task_queued",
                 self._dump({"objective": request.objective[:160]})),
            )

    def get_task(self, task_id: str):
        with self._session() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE task_id=%s", (task_id,)).fetchone()
        return dict(row) if row else None

    def mark_task(self, task_id: str, status: str, result: dict[str, Any] | None = None) -> bool:
        with self._session() as connection:
            cursor = connection.execute(
                "UPDATE tasks SET status=%s,result_json=%s,updated_at=%s "
                "WHERE task_id=%s AND status NOT IN ('completed','failed','cancelled','timeout')",
                (status, self._dump(result) if result is not None else None, time.time(), task_id),
            )
        return cursor.rowcount == 1
    def mark_task_timeout(self, task_id: str, result: dict[str, Any]) -> bool:
        with self._session() as connection:
            cursor = connection.execute(
                "UPDATE tasks SET status='timeout',result_json=%s,updated_at=%s WHERE task_id=%s AND status!='completed'",
                (self._dump(result), time.time(), task_id),
            )
        return cursor.rowcount == 1

    def claim_next(self):
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE status='queued' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
            ).fetchone()
            if not row:
                return None
            cursor = connection.execute(
                "UPDATE tasks SET status='running',updated_at=%s WHERE task_id=%s AND status='queued'",
                (time.time(), row["task_id"]),
            )
            if cursor.rowcount != 1:
                return None
            result = dict(row)
            result["status"] = "running"
            return result

    def set_memory(self, agent_id: str, key: str, value: Any):
        with self._session() as connection:
            connection.execute(
                "INSERT INTO agent_memory(agent_id,key,value_json,updated_at) VALUES(%s,%s,%s,%s) "
                "ON CONFLICT(agent_id,key) DO UPDATE SET value_json=EXCLUDED.value_json,updated_at=EXCLUDED.updated_at",
                (agent_id, key, self._dump(value), time.time()),
            )

    def get_memory(self, agent_id: str, key: str, default=None):
        with self._session() as connection:
            row = connection.execute(
                "SELECT value_json FROM agent_memory WHERE agent_id=%s AND key=%s", (agent_id, key)
            ).fetchone()
        return json.loads(row["value_json"]) if row else default

    def memory_keys(self, agent_id: str):
        with self._session() as connection:
            rows = connection.execute(
                "SELECT key FROM agent_memory WHERE agent_id=%s ORDER BY key", (agent_id,)
            ).fetchall()
        return [row["key"] for row in rows]

    def get_idempotent(self, key: str, request_hash: str):
        with self._session() as connection:
            row = connection.execute(
                "SELECT request_hash,result_json FROM idempotency WHERE idempotency_key=%s", (key,)
            ).fetchone()
        if not row:
            return None
        if row["request_hash"] != request_hash:
            raise ValueError("Idempotency key reused with a different request payload.")
        return json.loads(row["result_json"])

    def set_idempotent(self, key: str, request_hash: str, result: dict[str, Any]):
        with self._session() as connection:
            connection.execute(
                "INSERT INTO idempotency(idempotency_key,request_hash,result_json,created_at) VALUES(%s,%s,%s,%s) "
                "ON CONFLICT(idempotency_key) DO NOTHING",
                (key, request_hash, self._dump(result), time.time()),
            )

    def add_knowledge(self, source: str, content: str):
        knowledge_id = str(uuid.uuid4())
        with self._session() as connection:
            connection.execute(
                "INSERT INTO shared_knowledge(knowledge_id,source,content,trust_status,created_at) VALUES(%s,%s,%s,%s,%s)",
                (knowledge_id, source, content, "pending", time.time()),
            )
            connection.execute(
                "INSERT INTO events(ts,event_type,payload_json) VALUES(%s,%s,%s)",
                (time.time(), "knowledge_pending", self._dump({"knowledge_id": knowledge_id, "source": source})),
            )
        return knowledge_id

    def approve_knowledge(self, knowledge_id: str, approved_by: str):
        if not approved_by:
            raise PermissionError("Shared knowledge requires a verified reviewer identity.")
        with self._session() as connection:
            cursor = connection.execute(
                "UPDATE shared_knowledge SET trust_status='approved',reviewed_by=%s WHERE knowledge_id=%s",
                (approved_by, knowledge_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Unknown shared knowledge record: {knowledge_id}")
            connection.execute(
                "INSERT INTO events(ts,event_type,payload_json) VALUES(%s,%s,%s)",
                (time.time(), "knowledge_approved",
                 self._dump({"knowledge_id": knowledge_id, "approved_by": approved_by})),
            )

    def query_knowledge(self, limit: int = 20):
        with self._session() as connection:
            rows = connection.execute(
                "SELECT knowledge_id,source,content,reviewed_by,created_at FROM shared_knowledge "
                "WHERE trust_status='approved' ORDER BY created_at DESC LIMIT %s",
                (self._bounded(limit, 100),),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_outcome(self, agent_id: str, task_id: str | None, success: bool,
                       feedback: str, provenance: list[str]):
        outcome_id = str(uuid.uuid4())
        now = time.time()
        with self._session() as connection:
            connection.execute(
                "INSERT INTO outcomes(outcome_id,agent_id,task_id,success,feedback,provenance_json,created_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (outcome_id, agent_id, task_id, int(success), feedback, self._dump(provenance), now),
            )
            connection.execute(
                "INSERT INTO events(ts,task_id,agent_id,event_type,payload_json) VALUES(%s,%s,%s,%s,%s)",
                (now, task_id, agent_id, "outcome_recorded",
                 self._dump({"outcome_id": outcome_id, "success": success, "feedback": feedback[:160]})),
            )
        return outcome_id

    def set_baseline(self, agent_id: str, benchmark_id: str, report: dict[str, Any], *,
                     active_version: str | None = None, instruction_sha256: str | None = None,
                     report_sha256: str | None = None):
        with self._session() as connection:
            connection.execute(
                "INSERT INTO baselines(agent_id,benchmark_id,report_json,created_at,active_version,instruction_sha256,report_sha256) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(agent_id,benchmark_id) DO UPDATE SET "
                "report_json=EXCLUDED.report_json,created_at=EXCLUDED.created_at,active_version=EXCLUDED.active_version,"
                "instruction_sha256=EXCLUDED.instruction_sha256,report_sha256=EXCLUDED.report_sha256",
                (agent_id, benchmark_id, self._dump(report), time.time(), active_version,
                 instruction_sha256, report_sha256),
            )

    def get_baseline(self, agent_id: str, benchmark_id: str):
        with self._session() as connection:
            row = connection.execute(
                "SELECT report_json FROM baselines WHERE agent_id=%s AND benchmark_id=%s",
                (agent_id, benchmark_id),
            ).fetchone()
        return json.loads(row["report_json"]) if row else None

    def get_baseline_evidence(self, agent_id: str, benchmark_id: str):
        with self._session() as connection:
            row = connection.execute(
                "SELECT active_version,instruction_sha256,report_sha256 FROM baselines "
                "WHERE agent_id=%s AND benchmark_id=%s", (agent_id, benchmark_id)
            ).fetchone()
        return dict(row) if row else None

    def save_proposal(self, proposal: dict[str, Any]):
        now = time.time()
        with self._session() as connection:
            connection.execute(
                "INSERT INTO proposals(proposal_id,agent_id,base_version,candidate_version,candidate_instruction,changes,"
                "protected_change,benchmark_id,status,evaluation_json,created_at,protected_fields_json,evaluation_context_json) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (proposal["proposal_id"], proposal["agent_id"], proposal["base_version"],
                 proposal["candidate_version"], proposal["candidate_instruction"], proposal["changes"],
                 int(proposal["protected_change"]), proposal["benchmark_id"], proposal["status"],
                 self._dump(proposal["evaluation"]) if proposal.get("evaluation") else None, now,
                 self._dump(proposal.get("protected_fields", [])),
                 self._dump(proposal.get("evaluation_context", {}))),
            )
            connection.execute(
                "INSERT INTO events(ts,agent_id,event_type,payload_json) VALUES(%s,%s,%s,%s)",
                (now, proposal["agent_id"], "improvement_proposed",
                 self._dump({"proposal_id": proposal["proposal_id"], "base_version": proposal["base_version"],
                             "candidate_version": proposal["candidate_version"],
                             "protected_change": proposal["protected_change"]})),
            )

    def get_proposal(self, proposal_id: str):
        with self._session() as connection:
            row = connection.execute("SELECT * FROM proposals WHERE proposal_id=%s", (proposal_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["protected_change"] = bool(item["protected_change"])
        item["evaluation"] = json.loads(item.pop("evaluation_json")) if item.get("evaluation_json") else None
        item["protected_fields"] = json.loads(item.pop("protected_fields_json") or "[]")
        item["evaluation_context"] = json.loads(item.pop("evaluation_context_json") or "{}")
        return item

    def list_proposals(self, limit: int = 100):
        bounded = self._bounded(limit, 200)
        with self._session() as connection:
            rows = connection.execute(
                "SELECT * FROM proposals ORDER BY created_at DESC LIMIT %s", (bounded,)
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["protected_change"] = bool(item["protected_change"])
            item["evaluation"] = json.loads(item.pop("evaluation_json")) if item.get("evaluation_json") else None
            item["protected_fields"] = json.loads(item.pop("protected_fields_json") or "[]")
            item["evaluation_context"] = json.loads(item.pop("evaluation_context_json") or "{}")
            item.pop("candidate_instruction", None)
            return_item = item
            items.append(return_item)
        return items

    def update_proposal(self, proposal_id: str, status: str, evaluation: dict[str, Any] | None = None):
        with self._session() as connection:
            connection.execute(
                "UPDATE proposals SET status=%s,evaluation_json=%s WHERE proposal_id=%s",
                (status, self._dump(evaluation) if evaluation else None, proposal_id),
            )
            connection.execute(
                "INSERT INTO events(ts,event_type,payload_json) VALUES(%s,%s,%s)",
                (time.time(), "improvement_" + status,
                 self._dump({"proposal_id": proposal_id, "evaluation": evaluation or {}})),
            )

    def ensure_base_version(self, agent_id: str, version: str, instruction: str):
        with self._session() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (agent_id,))
            row = connection.execute(
                "SELECT version FROM agent_versions WHERE agent_id=%s AND active=1 FOR UPDATE",
                (agent_id,),
            ).fetchone()
            if not row:
                connection.execute(
                    "INSERT INTO agent_versions(agent_id,version,instruction,change_log,active,created_at) "
                    "VALUES(%s,%s,%s,%s,0,%s) ON CONFLICT(agent_id,version) DO NOTHING",
                    (agent_id, version, instruction, "baseline", time.time()),
                )
                connection.execute("UPDATE agent_versions SET active=1 WHERE agent_id=%s AND version=%s",
                                   (agent_id, version))

    def active_version(self, agent_id: str, default_version: str, default_instruction: str):
        self.ensure_base_version(agent_id, default_version, default_instruction)
        with self._session() as connection:
            row = connection.execute(
                "SELECT version,instruction FROM agent_versions WHERE agent_id=%s AND active=1",
                (agent_id,),
            ).fetchone()
        if not row:
            raise PostgresStorageError("No active agent version is available.")
        return dict(row)

    def promote_version(self, agent_id: str, version: str, instruction: str, change_log: str):
        with self._session() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (agent_id,))
            connection.execute("UPDATE agent_versions SET active=0 WHERE agent_id=%s", (agent_id,))
            connection.execute(
                "INSERT INTO agent_versions(agent_id,version,instruction,change_log,active,created_at) "
                "VALUES(%s,%s,%s,%s,1,%s) ON CONFLICT(agent_id,version) DO UPDATE SET "
                "instruction=EXCLUDED.instruction,change_log=EXCLUDED.change_log,active=1",
                (agent_id, version, instruction, change_log, time.time()),
            )
            connection.execute(
                "INSERT INTO events(ts,agent_id,event_type,payload_json) VALUES(%s,%s,%s,%s)",
                (time.time(), agent_id, "version_promoted",
                 self._dump({"version": version, "change_log": change_log})),
            )

    def rollback_version(self, agent_id: str, target_version: str, reason: str):
        with self._session() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (agent_id,))
            row = connection.execute(
                "SELECT 1 FROM agent_versions WHERE agent_id=%s AND version=%s",
                (agent_id, target_version),
            ).fetchone()
            if not row:
                raise ValueError(f"Unknown rollback target version {target_version}")
            connection.execute("UPDATE agent_versions SET active=0 WHERE agent_id=%s", (agent_id,))
            connection.execute(
                "UPDATE agent_versions SET active=1 WHERE agent_id=%s AND version=%s",
                (agent_id, target_version),
            )
            connection.execute(
                "INSERT INTO events(ts,agent_id,event_type,payload_json) VALUES(%s,%s,%s,%s)",
                (time.time(), agent_id, "version_rollback",
                 self._dump({"target_version": target_version, "reason": reason})),
            )

    def versions(self, agent_id: str):
        with self._session() as connection:
            rows = connection.execute(
                "SELECT version,change_log,active,created_at FROM agent_versions WHERE agent_id=%s ORDER BY created_at",
                (agent_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_capability(self, record: dict[str, Any]):
        now = time.time()
        with self._session() as connection:
            connection.execute(
                "INSERT INTO capabilities(capability_id,status,record_json,created_at,updated_at) VALUES(%s,%s,%s,%s,%s)",
                (record["capability_id"], record["status"], self._dump(record), now, now),
            )

    def get_capability(self, capability_id: str):
        with self._session() as connection:
            row = connection.execute(
                "SELECT record_json FROM capabilities WHERE capability_id=%s", (capability_id,)
            ).fetchone()
        return json.loads(row["record_json"]) if row else None

    def list_capabilities(self, status: str | None = None):
        with self._session() as connection:
            if status is None:
                rows = connection.execute(
                    "SELECT record_json FROM capabilities ORDER BY created_at,capability_id"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT record_json FROM capabilities WHERE status=%s ORDER BY created_at,capability_id",
                    (status,),
                ).fetchall()
        return [json.loads(row["record_json"]) for row in rows]

    def update_capability(self, record: dict[str, Any], expected_status: str) -> bool:
        with self._session() as connection:
            cursor = connection.execute(
                "UPDATE capabilities SET status=%s,record_json=%s,updated_at=%s WHERE capability_id=%s AND status=%s",
                (record["status"], self._dump(record), time.time(), record["capability_id"], expected_status),
            )
        return cursor.rowcount == 1

    def list_tasks(self, limit: int = 100):
        with self._session() as connection:
            rows = connection.execute(
                "SELECT task_id,agent_id,status,payload_json,result_json,created_at,updated_at "
                "FROM tasks ORDER BY created_at DESC LIMIT %s",
                (self._bounded(limit, 200),),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            payload = json.loads(item.pop("payload_json") or "{}")
            item["objective"] = payload.get("objective", "")
            item["inputs"] = payload.get("inputs", {})
            item["source_refs"] = payload.get("source_refs", [])
            item["provider_route"] = payload.get("provider_route")
            item["requested_skill_ids"] = payload.get("requested_skill_ids", [])
            item["parent_task_id"] = payload.get("parent_task_id")
            item["result"] = json.loads(item.pop("result_json")) if item.get("result_json") else None
            items.append(item)
        return items
    def creator_schema_ready(self):
        with self._session() as c:
            row=c.execute("SELECT version FROM schema_migrations WHERE version>=3 ORDER BY version DESC LIMIT 1").fetchone()
        return bool(row and int(row["version"])>=3)

    @staticmethod
    def _creator_project_row(row):
        if not row:return None
        item=dict(row);item["channel_profile"]=json.loads(item.pop("channel_profile_json"));return item
    @staticmethod
    def _creator_version_row(row):
        if not row:return None
        item=dict(row);item["content"]=json.loads(item.pop("content_json"));return item
    @staticmethod
    def _creator_asset_row(row):
        if not row:return None
        item=dict(row);item["provenance"]=json.loads(item.pop("provenance_json"));item["license"]=json.loads(item.pop("license_json"));return item
    @staticmethod
    def _creator_render_job_row(row):
        if not row:return None
        item=dict(row);item["resource_limits"]=json.loads(item.pop("resource_limits_json"));item["result_manifest"]=json.loads(item.pop("result_manifest_json"));return item

    def create_creator_project(self,project,actor):
        now=time.time()
        with self._session() as c:
            c.execute("INSERT INTO creator_projects(project_id,title,topic,channel_profile_json,language,status,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                (project["project_id"],project["title"],project["topic"],self._dump(project["channel_profile"]),project["language"],"idea",now,now))
            c.execute("INSERT INTO events(ts,event_type,payload_json) VALUES(%s,%s,%s)",(now,"creator_project_created",self._dump({"project_id":project["project_id"],"actor":actor})))
        return self.get_creator_project(project["project_id"])
    def get_creator_project(self,project_id):
        with self._session() as c:row=c.execute("SELECT * FROM creator_projects WHERE project_id=%s",(project_id,)).fetchone()
        return self._creator_project_row(row)
    def list_creator_projects(self,limit=50):
        with self._session() as c:rows=c.execute("SELECT * FROM creator_projects ORDER BY updated_at DESC,project_id LIMIT %s",(self._bounded(limit,200),)).fetchall()
        return [self._creator_project_row(row) for row in rows]
    def transition_creator_project(self,project_id,expected_status,next_status,actor,evidence):
        now=time.time()
        with self._session() as c:
            cur=c.execute("UPDATE creator_projects SET status=%s,updated_at=%s WHERE project_id=%s AND status=%s",(next_status,now,project_id,expected_status))
            if cur.rowcount!=1:return None
            c.execute("INSERT INTO events(ts,event_type,payload_json) VALUES(%s,%s,%s)",(now,"creator_project_transition",self._dump({"project_id":project_id,"from":expected_status,"to":next_status,"actor":actor,"evidence":evidence})))
            row=c.execute("SELECT * FROM creator_projects WHERE project_id=%s",(project_id,)).fetchone()
        return self._creator_project_row(row)
    def create_creator_version(self,project_id,version_id,kind,content,parent_version_id,actor):
        now=time.time()
        with self._session() as c:
            project=c.execute("SELECT project_id FROM creator_projects WHERE project_id=%s FOR UPDATE",(project_id,)).fetchone()
            if not project:raise ValueError("Unknown creator project.")
            if parent_version_id and not c.execute("SELECT 1 FROM creator_project_versions WHERE project_id=%s AND version_id=%s",(project_id,parent_version_id)).fetchone():raise ValueError("Parent version does not belong to this project.")
            row=c.execute("SELECT COALESCE(MAX(version_no),0)+1 AS next_version FROM creator_project_versions WHERE project_id=%s",(project_id,)).fetchone()
            no=int(row["next_version"])
            c.execute("INSERT INTO creator_project_versions(version_id,project_id,version_no,kind,content_json,parent_version_id,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s)",(version_id,project_id,no,kind,self._dump(content),parent_version_id,now))
            c.execute("INSERT INTO events(ts,event_type,payload_json) VALUES(%s,%s,%s)",(now,"creator_version_created",self._dump({"project_id":project_id,"version_id":version_id,"version_no":no,"kind":kind,"actor":actor})))
            row=c.execute("SELECT * FROM creator_project_versions WHERE version_id=%s",(version_id,)).fetchone()
        return self._creator_version_row(row)
    def list_creator_versions(self,project_id):
        with self._session() as c:rows=c.execute("SELECT * FROM creator_project_versions WHERE project_id=%s ORDER BY version_no",(project_id,)).fetchall()
        return [self._creator_version_row(row) for row in rows]
    def create_creator_asset(self,asset):
        with self._session() as c:
            c.execute("INSERT INTO creator_project_assets(asset_id,project_id,version_id,kind,storage_key,sha256,byte_size,mime_type,provenance_json,license_json,qa_status,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (asset["asset_id"],asset["project_id"],asset["version_id"],asset["kind"],asset["storage_key"],asset["sha256"],asset["byte_size"],asset["mime_type"],self._dump(asset["provenance"]),self._dump(asset["license"]),asset["qa_status"],time.time()))
            row=c.execute("SELECT * FROM creator_project_assets WHERE asset_id=%s",(asset["asset_id"],)).fetchone()
        return self._creator_asset_row(row)
    def list_creator_assets(self,project_id,version_id=None):
        with self._session() as c:
            if version_id:rows=c.execute("SELECT * FROM creator_project_assets WHERE project_id=%s AND version_id=%s ORDER BY created_at,asset_id",(project_id,version_id)).fetchall()
            else:rows=c.execute("SELECT * FROM creator_project_assets WHERE project_id=%s ORDER BY created_at,asset_id",(project_id,)).fetchall()
        return [self._creator_asset_row(row) for row in rows]
    def create_creator_render_job(self,job):
        with self._session() as c:
            cur=c.execute("INSERT INTO creator_render_jobs(job_id,project_id,version_id,engine_commit,style_id,status,idempotency_key,request_hash,resource_limits_json,result_manifest_json,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(idempotency_key) DO NOTHING RETURNING job_id",
                (job["job_id"],job["project_id"],job["version_id"],job["engine_commit"],job["style_id"],job["status"],job["idempotency_key"],job["request_hash"],self._dump(job["resource_limits"]),self._dump(job["result_manifest"]),job["created_at"],job["updated_at"]))
            inserted=cur.rowcount==1
            row=c.execute("SELECT * FROM creator_render_jobs WHERE idempotency_key=%s",(job["idempotency_key"],)).fetchone()
            if not row:raise ValueError("Render job could not be stored.")
            if row["request_hash"]!=job["request_hash"]:raise ValueError("Idempotency key reused for a different render request.")
            result=self._creator_render_job_row(row);result["idempotent_replay"]=not inserted
        return result
    def get_creator_render_job(self,job_id):
        with self._session() as c:row=c.execute("SELECT * FROM creator_render_jobs WHERE job_id=%s",(job_id,)).fetchone()
        return self._creator_render_job_row(row)
    def list_creator_render_jobs(self,project_id,limit=50):
        with self._session() as c:rows=c.execute("SELECT * FROM creator_render_jobs WHERE project_id=%s ORDER BY created_at DESC LIMIT %s",(project_id,self._bounded(limit,200))).fetchall()
        return [self._creator_render_job_row(row) for row in rows]
    def transition_creator_render_job(self,job_id,expected_status,next_status,result_manifest):
        now=time.time()
        with self._session() as c:
            cur=c.execute("UPDATE creator_render_jobs SET status=%s,result_manifest_json=%s,updated_at=%s WHERE job_id=%s AND status=%s",(next_status,self._dump(result_manifest),now,job_id,expected_status))
            if cur.rowcount!=1:return None
            c.execute("INSERT INTO events(ts,event_type,payload_json) VALUES(%s,%s,%s)",(now,"creator_render_job_transition",self._dump({"job_id":job_id,"from":expected_status,"to":next_status})))
            row=c.execute("SELECT * FROM creator_render_jobs WHERE job_id=%s",(job_id,)).fetchone()
        return self._creator_render_job_row(row)
