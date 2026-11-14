from __future__ import annotations
from pathlib import Path
from typing import Any
import sqlite3, json, time, uuid
from contextlib import contextmanager

class StateStore:
    def __init__(self, path: str | Path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self._init()
    def _connect(self):
        c=sqlite3.connect(self.path,timeout=10); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
    @contextmanager
    def _session(self):
        c=self._connect()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback(); raise
        finally:
            c.close()
    def _init(self):
        with self._session() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS tasks(task_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL, result_json TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON tasks(status,created_at);
            CREATE TABLE IF NOT EXISTS events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, task_id TEXT, agent_id TEXT, event_type TEXT NOT NULL, payload_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS agent_memory(agent_id TEXT NOT NULL, key TEXT NOT NULL, value_json TEXT NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY(agent_id,key));
            CREATE TABLE IF NOT EXISTS shared_knowledge(knowledge_id TEXT PRIMARY KEY, source TEXT NOT NULL, content TEXT NOT NULL, trust_status TEXT NOT NULL, reviewed_by TEXT, created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS idempotency(idempotency_key TEXT PRIMARY KEY, request_hash TEXT NOT NULL, result_json TEXT NOT NULL, created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS idempotency_claims(idempotency_key TEXT PRIMARY KEY, request_hash TEXT NOT NULL, task_id TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('running','completed','failed')), result_json TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS workflow_checkpoints(
                workflow_id TEXT PRIMARY KEY,
                request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
                checkpoint_version INTEGER NOT NULL CHECK(checkpoint_version>0),
                revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0),
                status TEXT NOT NULL CHECK(status IN ('running','completed','interrupted','blocked')),
                current_stage TEXT,state_json TEXT NOT NULL,
                created_at REAL NOT NULL,updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_checkpoints_status_updated
                ON workflow_checkpoints(status,updated_at);
            CREATE TABLE IF NOT EXISTS workflow_stage_checkpoints(
                workflow_id TEXT NOT NULL REFERENCES workflow_checkpoints(workflow_id) ON DELETE RESTRICT,
                stage_key TEXT NOT NULL,stage_index INTEGER NOT NULL CHECK(stage_index>0),
                request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
                status TEXT NOT NULL CHECK(status IN ('started','completed','interrupted','failed')),
                attempt_token TEXT NOT NULL,task_id TEXT,result_json TEXT,
                created_at REAL NOT NULL,updated_at REAL NOT NULL,
                PRIMARY KEY(workflow_id,stage_key),UNIQUE(workflow_id,stage_index)
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_stage_checkpoints_status_updated
                ON workflow_stage_checkpoints(status,updated_at);

            CREATE INDEX IF NOT EXISTS idx_idempotency_claims_state_updated ON idempotency_claims(state,updated_at);
            CREATE TABLE IF NOT EXISTS outcomes(outcome_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, task_id TEXT, success INTEGER NOT NULL, feedback TEXT NOT NULL, provenance_json TEXT NOT NULL, created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS proposals(proposal_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, base_version TEXT NOT NULL, candidate_version TEXT NOT NULL, candidate_instruction TEXT NOT NULL, changes TEXT NOT NULL, protected_change INTEGER NOT NULL, benchmark_id TEXT NOT NULL, status TEXT NOT NULL, evaluation_json TEXT, created_at REAL NOT NULL, protected_fields_json TEXT NOT NULL DEFAULT '[]', evaluation_context_json TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS agent_versions(agent_id TEXT NOT NULL, version TEXT NOT NULL, instruction TEXT NOT NULL, change_log TEXT NOT NULL, active INTEGER NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(agent_id,version));
            CREATE TABLE IF NOT EXISTS baselines(agent_id TEXT NOT NULL, benchmark_id TEXT NOT NULL, report_json TEXT NOT NULL, created_at REAL NOT NULL, active_version TEXT, instruction_sha256 TEXT, report_sha256 TEXT, PRIMARY KEY(agent_id,benchmark_id));
            CREATE TABLE IF NOT EXISTS capabilities(capability_id TEXT PRIMARY KEY, status TEXT NOT NULL, record_json TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_capabilities_status_updated ON capabilities(status,updated_at);

            CREATE TABLE IF NOT EXISTS creator_projects (
                project_id TEXT PRIMARY KEY,title TEXT NOT NULL,topic TEXT NOT NULL,
                channel_profile_json TEXT NOT NULL,language TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('idea','researching','treatment_ready','storyboard_ready','authoring','render_queued','rendering','blocked','qa_failed','qa_passed','human_approved','package_ready','uploaded','scheduled','published','archived')),
                created_at REAL NOT NULL,updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_creator_projects_status_updated ON creator_projects(status,updated_at);
            CREATE TABLE IF NOT EXISTS creator_project_versions (
                version_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES creator_projects(project_id) ON DELETE RESTRICT,
                version_no INTEGER NOT NULL CHECK(version_no>0),kind TEXT NOT NULL,content_json TEXT NOT NULL,
                parent_version_id TEXT,created_at REAL NOT NULL,
                UNIQUE(project_id,version_no),UNIQUE(project_id,version_id),
                FOREIGN KEY(project_id,parent_version_id) REFERENCES creator_project_versions(project_id,version_id) ON DELETE RESTRICT
            );
            CREATE INDEX IF NOT EXISTS idx_creator_versions_project_no ON creator_project_versions(project_id,version_no);
            CREATE TABLE IF NOT EXISTS creator_project_assets (
                asset_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES creator_projects(project_id) ON DELETE RESTRICT,
                version_id TEXT NOT NULL,kind TEXT NOT NULL,storage_key TEXT NOT NULL UNIQUE,
                sha256 TEXT NOT NULL CHECK(length(sha256)=64),byte_size INTEGER NOT NULL CHECK(byte_size>=0),
                mime_type TEXT NOT NULL,provenance_json TEXT NOT NULL,license_json TEXT NOT NULL,
                qa_status TEXT NOT NULL CHECK(qa_status IN ('pending','needs_review','passed','failed')),created_at REAL NOT NULL,
                FOREIGN KEY(project_id,version_id) REFERENCES creator_project_versions(project_id,version_id) ON DELETE RESTRICT
            );
            CREATE INDEX IF NOT EXISTS idx_creator_assets_project ON creator_project_assets(project_id,created_at);
            CREATE TABLE IF NOT EXISTS creator_render_jobs (
                job_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES creator_projects(project_id) ON DELETE RESTRICT,
                version_id TEXT NOT NULL,engine_commit TEXT NOT NULL CHECK(length(engine_commit)=40),style_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('queued','blocked','running','succeeded','failed','cancelled')),
                idempotency_key TEXT NOT NULL UNIQUE,request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
                resource_limits_json TEXT NOT NULL,result_manifest_json TEXT NOT NULL,
                created_at REAL NOT NULL,updated_at REAL NOT NULL,
                FOREIGN KEY(project_id,version_id) REFERENCES creator_project_versions(project_id,version_id) ON DELETE RESTRICT
            );
            CREATE INDEX IF NOT EXISTS idx_creator_render_jobs_project_created ON creator_render_jobs(project_id,created_at);
            """)
            baseline_columns={row['name'] for row in c.execute('PRAGMA table_info(baselines)').fetchall()}
            for column, declaration in (('active_version','TEXT'),('instruction_sha256','TEXT'),('report_sha256','TEXT')):
                if column not in baseline_columns:
                    c.execute(f'ALTER TABLE baselines ADD COLUMN {column} {declaration}')
            proposal_columns={row['name'] for row in c.execute('PRAGMA table_info(proposals)').fetchall()}
            if 'protected_fields_json' not in proposal_columns:
                c.execute("ALTER TABLE proposals ADD COLUMN protected_fields_json TEXT NOT NULL DEFAULT '[]'")
            if 'evaluation_context_json' not in proposal_columns:
                c.execute("ALTER TABLE proposals ADD COLUMN evaluation_context_json TEXT NOT NULL DEFAULT '{}'")
    def log_event(self,event_type:str,task_id:str|None=None,agent_id:str|None=None,payload:dict[str,Any]|None=None):
        with self._session() as c: c.execute('INSERT INTO events(ts,task_id,agent_id,event_type,payload_json) VALUES(?,?,?,?,?)',(time.time(),task_id,agent_id,event_type,json.dumps(payload or {},ensure_ascii=False)))
    def events(self,limit:int=100):
        with self._session() as c: rows=c.execute('SELECT * FROM events ORDER BY event_id DESC LIMIT ?',(max(1,min(limit,1000)),)).fetchall()
        return [dict(r) for r in rows]

    def list_task_events(self, task_id: str, *, after_event_id: int = 0, limit: int = 100):
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id must be a non-empty string.")
        if isinstance(after_event_id, bool) or not isinstance(after_event_id, int) or after_event_id < 0:
            raise ValueError("after_event_id must be a non-negative integer.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 201:
            raise ValueError("limit must be an integer between 1 and 201.")
        with self._session() as c:
            rows = c.execute(
                'SELECT event_id,ts,task_id,agent_id,event_type,payload_json FROM events '
                'WHERE task_id=? AND event_id>? ORDER BY event_id ASC LIMIT ?',
                (task_id, after_event_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]
    def enqueue(self,request):
        payload={'task_id':request.task_id,'agent_id':request.agent_id,'objective':request.objective,'inputs':request.inputs,'required_permissions':list(request.required_permissions),'deadline_seconds':request.deadline_seconds,'max_steps':request.max_steps,'idempotency_key':request.idempotency_key,'source_refs':list(request.source_refs),'provider_route':request.provider_route,'requested_skill_ids':list(request.requested_skill_ids),'parent_task_id':request.parent_task_id,'created_at':request.created_at}
        now=time.time()
        with self._session() as c: c.execute('INSERT INTO tasks(task_id,agent_id,status,payload_json,created_at,updated_at) VALUES(?,?,?,?,?,?)',(request.task_id,request.agent_id,'queued',json.dumps(payload,ensure_ascii=False),now,now))
        self.log_event('task_queued',request.task_id,request.agent_id,{'objective':request.objective[:160]})
    def get_task(self,task_id:str):
        with self._session() as c: row=c.execute('SELECT * FROM tasks WHERE task_id=?',(task_id,)).fetchone()
        return dict(row) if row else None
    def mark_task(self,task_id:str,status:str,result:dict[str,Any]|None=None) -> bool:
        with self._session() as c:
            cur=c.execute("UPDATE tasks SET status=?,result_json=?,updated_at=? WHERE task_id=? AND status NOT IN ('completed','failed','cancelled','timeout')",
                          (status,json.dumps(result,ensure_ascii=False) if result is not None else None,time.time(),task_id))
        return cur.rowcount == 1
    def mark_task_timeout(self,task_id:str,result:dict[str,Any])->bool:
        with self._session() as c:
            cur=c.execute("UPDATE tasks SET status='timeout',result_json=?,updated_at=? WHERE task_id=? AND status!='completed'",
                          (json.dumps(result,ensure_ascii=False),time.time(),task_id))
        return cur.rowcount==1
    def claim_next(self):
        with self._session() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute("SELECT * FROM tasks WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if not row: c.commit(); return None
            c.execute("UPDATE tasks SET status='running',updated_at=? WHERE task_id=? AND status='queued'",(time.time(),row['task_id']))
            c.commit(); return dict(row)

    @staticmethod
    def _validate_workflow_hash(value: str, field: str) -> None:
        if (not isinstance(value, str) or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)):
            raise ValueError(f"{field} must be a 64-character lowercase SHA-256 hex string.")

    @staticmethod
    def _decode_workflow_checkpoint(row):
        item = dict(row)
        item["state"] = json.loads(item.pop("state_json"))
        return item

    @staticmethod
    def _decode_workflow_stage(row):
        item = dict(row)
        raw = item.pop("result_json")
        item["result"] = json.loads(raw) if raw else None
        return item

    def create_workflow_checkpoint(self, workflow_id: str, request_hash: str,
                                   checkpoint_version: int, state: dict[str, Any]):
        if not isinstance(workflow_id, str) or not workflow_id.strip():
            raise ValueError("workflow_id must be a non-empty string.")
        self._validate_workflow_hash(request_hash, "request_hash")
        if isinstance(checkpoint_version, bool) or not isinstance(checkpoint_version, int) or checkpoint_version < 1:
            raise ValueError("checkpoint_version must be a positive integer.")
        if not isinstance(state, dict):
            raise TypeError("state must be a dictionary.")
        state_json = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        now = time.time()
        with self._session() as c:
            c.execute(
                "INSERT OR IGNORE INTO workflow_checkpoints"
                "(workflow_id,request_hash,checkpoint_version,revision,status,current_stage,state_json,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (workflow_id, request_hash, checkpoint_version, 0, "running", None, state_json, now, now),
            )
            row = c.execute(
                "SELECT * FROM workflow_checkpoints WHERE workflow_id=?", (workflow_id,)
            ).fetchone()
        if not row:
            raise RuntimeError("Workflow checkpoint could not be read after creation.")
        if row["request_hash"] != request_hash or int(row["checkpoint_version"]) != checkpoint_version:
            raise ValueError("Workflow ID already belongs to a different request or checkpoint version.")
        return self._decode_workflow_checkpoint(row)

    def get_workflow_checkpoint(self, workflow_id: str):
        if not isinstance(workflow_id, str) or not workflow_id.strip():
            raise ValueError("workflow_id must be a non-empty string.")
        with self._session() as c:
            row = c.execute(
                "SELECT * FROM workflow_checkpoints WHERE workflow_id=?", (workflow_id,)
            ).fetchone()
        return self._decode_workflow_checkpoint(row) if row else None

    def save_workflow_checkpoint(self, workflow_id: str, expected_revision: int,
                                 status: str, current_stage: str | None,
                                 state: dict[str, Any]) -> bool:
        allowed = {"running", "completed", "interrupted", "blocked"}
        if status not in allowed:
            raise ValueError("Unsupported workflow checkpoint status.")
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
            raise ValueError("expected_revision must be a non-negative integer.")
        if current_stage is not None and (not isinstance(current_stage, str) or not current_stage.strip()):
            raise ValueError("current_stage must be a non-empty string or None.")
        if not isinstance(state, dict):
            raise TypeError("state must be a dictionary.")
        state_json = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self._session() as c:
            cursor = c.execute(
                "UPDATE workflow_checkpoints SET status=?,current_stage=?,state_json=?,"
                "revision=revision+1,updated_at=? WHERE workflow_id=? AND revision=? AND status='running'",
                (status, current_stage, state_json, time.time(), workflow_id, expected_revision),
            )
        return cursor.rowcount == 1

    def begin_workflow_stage(self, workflow_id: str, stage_key: str, stage_index: int,
                             request_hash: str, attempt_token: str):
        if not isinstance(workflow_id, str) or not workflow_id.strip():
            raise ValueError("workflow_id must be a non-empty string.")
        if not isinstance(stage_key, str) or not stage_key.strip():
            raise ValueError("stage_key must be a non-empty string.")
        if isinstance(stage_index, bool) or not isinstance(stage_index, int) or stage_index < 1:
            raise ValueError("stage_index must be a positive integer.")
        self._validate_workflow_hash(request_hash, "request_hash")
        if not isinstance(attempt_token, str) or not attempt_token.strip():
            raise ValueError("attempt_token must be a non-empty string.")
        now = time.time()
        with self._session() as c:
            parent = c.execute(
                "SELECT status FROM workflow_checkpoints WHERE workflow_id=?", (workflow_id,)
            ).fetchone()
            if not parent:
                raise KeyError("Workflow checkpoint does not exist.")
            if parent["status"] != "running":
                raise ValueError("Only a running workflow can start a stage.")
            index_owner = c.execute(
                "SELECT stage_key FROM workflow_stage_checkpoints WHERE workflow_id=? AND stage_index=?",
                (workflow_id, stage_index),
            ).fetchone()
            if index_owner and index_owner["stage_key"] != stage_key:
                raise ValueError("Workflow stage index is already assigned to another stage key.")
            cursor = c.execute(
                "INSERT OR IGNORE INTO workflow_stage_checkpoints"
                "(workflow_id,stage_key,stage_index,request_hash,status,attempt_token,task_id,result_json,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (workflow_id, stage_key, stage_index, request_hash, "started", attempt_token, None, None, now, now),
            )
            row = c.execute(
                "SELECT * FROM workflow_stage_checkpoints WHERE workflow_id=? AND stage_key=?",
                (workflow_id, stage_key),
            ).fetchone()
        if not row:
            raise RuntimeError("Workflow stage checkpoint could not be read after acquisition.")
        if row["request_hash"] != request_hash or int(row["stage_index"]) != stage_index:
            raise ValueError("Workflow stage key already belongs to a different request or index.")
        result = self._decode_workflow_stage(row)
        result["can_execute"] = cursor.rowcount == 1
        return result

    def complete_workflow_stage(self, workflow_id: str, stage_key: str,
                                attempt_token: str, task_id: str | None,
                                result: dict[str, Any]) -> bool:
        if not isinstance(result, dict):
            raise TypeError("result must be a dictionary.")
        if not isinstance(attempt_token, str) or not attempt_token.strip():
            raise ValueError("attempt_token must be a non-empty string.")
        result_json = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self._session() as c:
            cursor = c.execute(
                "UPDATE workflow_stage_checkpoints SET status='completed',task_id=?,result_json=?,updated_at=? "
                "WHERE workflow_id=? AND stage_key=? AND status='started' AND attempt_token=?",
                (task_id, result_json, time.time(), workflow_id, stage_key, attempt_token),
            )
        return cursor.rowcount == 1

    def list_workflow_stages(self, workflow_id: str):
        if not isinstance(workflow_id, str) or not workflow_id.strip():
            raise ValueError("workflow_id must be a non-empty string.")
        with self._session() as c:
            rows = c.execute(
                "SELECT * FROM workflow_stage_checkpoints WHERE workflow_id=? ORDER BY stage_index",
                (workflow_id,),
            ).fetchall()
        return [self._decode_workflow_stage(row) for row in rows]

    def set_memory(self,agent_id:str,key:str,value:Any):
        with self._session() as c: c.execute('INSERT INTO agent_memory(agent_id,key,value_json,updated_at) VALUES(?,?,?,?) ON CONFLICT(agent_id,key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at',(agent_id,key,json.dumps(value,ensure_ascii=False),time.time()))
    def get_memory(self,agent_id:str,key:str,default=None):
        with self._session() as c: row=c.execute('SELECT value_json FROM agent_memory WHERE agent_id=? AND key=?',(agent_id,key)).fetchone()
        return json.loads(row['value_json']) if row else default
    def memory_keys(self,agent_id:str):
        with self._session() as c: return [r['key'] for r in c.execute('SELECT key FROM agent_memory WHERE agent_id=?',(agent_id,)).fetchall()]
    def get_idempotent(self,key:str,request_hash:str):
        with self._session() as c: row=c.execute('SELECT request_hash,result_json FROM idempotency WHERE idempotency_key=?',(key,)).fetchone()
        if not row: return None
        if row['request_hash']!=request_hash: raise ValueError('Idempotency key reused with a different request payload.')
        return json.loads(row['result_json'])
    def set_idempotent(self,key:str,request_hash:str,result:dict[str,Any]):
        with self._session() as c: c.execute('INSERT OR IGNORE INTO idempotency(idempotency_key,request_hash,result_json,created_at) VALUES(?,?,?,?)',(key,request_hash,json.dumps(result,ensure_ascii=False),time.time()))
    def claim_idempotency(self,key:str,request_hash:str,task_id:str,lease_seconds:float=660.0):
        now=time.time()
        with self._session() as c:
            cur=c.execute("INSERT OR IGNORE INTO idempotency_claims(idempotency_key,request_hash,task_id,state,result_json,created_at,updated_at) VALUES(?,?,?,'running',NULL,?,?)",(key,request_hash,task_id,now,now))
            if cur.rowcount==1: return {'state':'claimed','task_id':task_id}
            row=c.execute('SELECT request_hash,task_id,state,result_json,updated_at FROM idempotency_claims WHERE idempotency_key=?',(key,)).fetchone()
            if not row: raise RuntimeError('Idempotency claim disappeared during acquisition.')
            if row['request_hash']!=request_hash: raise ValueError('Idempotency key reused with a different request payload.')
            if row['state']=='running' and now-float(row['updated_at'])>lease_seconds:
                c.execute("UPDATE idempotency_claims SET task_id=?,state='running',result_json=NULL,updated_at=? WHERE idempotency_key=? AND state='running' AND updated_at=?",(task_id,now,key,row['updated_at']))
                check=c.execute('SELECT task_id,state,result_json FROM idempotency_claims WHERE idempotency_key=?',(key,)).fetchone()
                if check['task_id']==task_id: return {'state':'claimed','task_id':task_id}
                return {'state':'running','task_id':check['task_id']}
            return {'state':row['state'],'task_id':row['task_id'],'result':json.loads(row['result_json']) if row['result_json'] else None}

    def get_idempotency_claim(self, key: str):
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key must be a non-empty string.")
        with self._session() as c:
            row = c.execute(
                "SELECT idempotency_key,request_hash,task_id,state,result_json,created_at,updated_at "
                "FROM idempotency_claims WHERE idempotency_key=?",
                (key,),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        raw = item.pop("result_json")
        item["result"] = json.loads(raw) if raw else None
        return item

    def complete_idempotency(self,key:str,task_id:str,result:dict[str,Any])->bool:
        with self._session() as c:
            cur=c.execute("UPDATE idempotency_claims SET state='completed',result_json=?,updated_at=? WHERE idempotency_key=? AND task_id=? AND state='running'",(json.dumps(result,ensure_ascii=False),time.time(),key,task_id))
        return cur.rowcount==1

    def fail_idempotency(self,key:str,task_id:str,result:dict[str,Any])->bool:
        with self._session() as c:
            cur=c.execute("UPDATE idempotency_claims SET state='failed',result_json=?,updated_at=? WHERE idempotency_key=? AND task_id=? AND state='running'",(json.dumps(result,ensure_ascii=False),time.time(),key,task_id))
        return cur.rowcount==1
    def add_knowledge(self,source:str,content:str):
        kid=str(uuid.uuid4())
        with self._session() as c: c.execute('INSERT INTO shared_knowledge(knowledge_id,source,content,trust_status,created_at) VALUES(?,?,?,?,?)',(kid,source,content,'pending',time.time()))
        self.log_event('knowledge_pending',agent_id=None,payload={'knowledge_id':kid,'source':source})
        return kid
    def approve_knowledge(self,kid:str,approved_by:str):
        if not approved_by: raise PermissionError('Shared knowledge requires a verified reviewer identity.')
        with self._session() as c:
            cur=c.execute("UPDATE shared_knowledge SET trust_status='approved',reviewed_by=? WHERE knowledge_id=?",(approved_by,kid))
        if cur.rowcount!=1: raise ValueError(f'Unknown shared knowledge record: {kid}')
        self.log_event('knowledge_approved',payload={'knowledge_id':kid,'approved_by':approved_by})
    def query_knowledge(self,limit:int=20):
        with self._session() as c: rows=c.execute("SELECT knowledge_id,source,content,reviewed_by,created_at FROM shared_knowledge WHERE trust_status='approved' ORDER BY created_at DESC LIMIT ?",(max(1,min(limit,100)),)).fetchall()
        return [dict(r) for r in rows]
    def record_outcome(self,agent_id:str,task_id:str|None,success:bool,feedback:str,provenance:list[str]):
        oid=str(uuid.uuid4())
        with self._session() as c: c.execute('INSERT INTO outcomes VALUES(?,?,?,?,?,?,?)',(oid,agent_id,task_id,int(success),feedback,json.dumps(provenance),time.time()))
        self.log_event('outcome_recorded',task_id,agent_id,{'outcome_id':oid,'success':success,'feedback':feedback[:160]})
        return oid
    def set_baseline(self,agent_id:str,benchmark_id:str,report:dict[str,Any], *, active_version:str|None=None, instruction_sha256:str|None=None, report_sha256:str|None=None):
        with self._session() as c:
            c.execute('INSERT OR REPLACE INTO baselines(agent_id,benchmark_id,report_json,created_at,active_version,instruction_sha256,report_sha256) VALUES(?,?,?,?,?,?,?)',
                      (agent_id,benchmark_id,json.dumps(report,sort_keys=True,ensure_ascii=False),time.time(),active_version,instruction_sha256,report_sha256))
    def get_baseline(self,agent_id:str,benchmark_id:str):
        with self._session() as c: row=c.execute('SELECT report_json FROM baselines WHERE agent_id=? AND benchmark_id=?',(agent_id,benchmark_id)).fetchone()
        return json.loads(row['report_json']) if row else None
    def get_baseline_evidence(self,agent_id:str,benchmark_id:str):
        with self._session() as c: row=c.execute('SELECT active_version,instruction_sha256,report_sha256 FROM baselines WHERE agent_id=? AND benchmark_id=?',(agent_id,benchmark_id)).fetchone()
        return dict(row) if row else None
    def save_proposal(self,p:dict[str,Any]):
        with self._session() as c:
            c.execute('INSERT INTO proposals(proposal_id,agent_id,base_version,candidate_version,candidate_instruction,changes,protected_change,benchmark_id,status,evaluation_json,created_at,protected_fields_json,evaluation_context_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (p['proposal_id'],p['agent_id'],p['base_version'],p['candidate_version'],p['candidate_instruction'],p['changes'],int(p['protected_change']),p['benchmark_id'],p['status'],json.dumps(p.get('evaluation')) if p.get('evaluation') else None,time.time(),json.dumps(p.get('protected_fields',[])),json.dumps(p.get('evaluation_context',{}),sort_keys=True)))
        self.log_event('improvement_proposed',agent_id=p['agent_id'],payload={'proposal_id':p['proposal_id'],'base_version':p['base_version'],'candidate_version':p['candidate_version'],'protected_change':p['protected_change']})
    def get_proposal(self,pid:str):
        with self._session() as c: row=c.execute('SELECT * FROM proposals WHERE proposal_id=?',(pid,)).fetchone()
        if not row: return None
        d=dict(row); d['protected_change']=bool(d['protected_change']); d['evaluation']=json.loads(d['evaluation_json']) if d['evaluation_json'] else None; d['protected_fields']=json.loads(d.get('protected_fields_json') or '[]'); d['evaluation_context']=json.loads(d.get('evaluation_context_json') or '{}'); return d
    def update_proposal(self,pid:str,status:str,evaluation:dict[str,Any]|None=None):
        with self._session() as c: c.execute('UPDATE proposals SET status=?,evaluation_json=? WHERE proposal_id=?',(status,json.dumps(evaluation) if evaluation else None,pid))
        self.log_event('improvement_'+status,payload={'proposal_id':pid,'evaluation':evaluation or {}})
    def ensure_base_version(self,agent_id:str,version:str,instruction:str):
        with self._session() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT 1 FROM agent_versions WHERE agent_id=? AND version=?',(agent_id,version)).fetchone()
            if not row:
                c.execute('UPDATE agent_versions SET active=0 WHERE agent_id=?',(agent_id,))
                c.execute('INSERT INTO agent_versions(agent_id,version,instruction,change_log,active,created_at) VALUES(?,?,?,?,?,?)',(agent_id,version,instruction,'baseline',1,time.time()))
    def active_version(self,agent_id:str,default_version:str,default_instruction:str):
        self.ensure_base_version(agent_id,default_version,default_instruction)
        with self._session() as c: row=c.execute('SELECT version,instruction FROM agent_versions WHERE agent_id=? AND active=1',(agent_id,)).fetchone()
        return dict(row)
    def promote_version(self,agent_id:str,version:str,instruction:str,change_log:str):
        with self._session() as c:
            c.execute('UPDATE agent_versions SET active=0 WHERE agent_id=?',(agent_id,))
            c.execute('INSERT INTO agent_versions(agent_id,version,instruction,change_log,active,created_at) VALUES(?,?,?,?,?,?)',(agent_id,version,instruction,change_log,1,time.time()))
        self.log_event('version_promoted',agent_id=agent_id,payload={'version':version,'change_log':change_log})
    def rollback_version(self,agent_id:str,target_version:str,reason:str):
        with self._session() as c:
            row=c.execute('SELECT 1 FROM agent_versions WHERE agent_id=? AND version=?',(agent_id,target_version)).fetchone()
            if not row: raise ValueError(f'Unknown rollback target version {target_version}')
            c.execute('UPDATE agent_versions SET active=0 WHERE agent_id=?',(agent_id,))
            c.execute('UPDATE agent_versions SET active=1 WHERE agent_id=? AND version=?',(agent_id,target_version))
        self.log_event('version_rollback',agent_id=agent_id,payload={'target_version':target_version,'reason':reason})
    def versions(self,agent_id:str):
        with self._session() as c: rows=c.execute('SELECT version,change_log,active,created_at FROM agent_versions WHERE agent_id=? ORDER BY created_at',(agent_id,)).fetchall()
        return [dict(r) for r in rows]

    def save_capability(self,record:dict[str,Any]):
        now=time.time()
        with self._session() as c:
            c.execute('INSERT INTO capabilities(capability_id,status,record_json,created_at,updated_at) VALUES(?,?,?,?,?)',
                      (record['capability_id'],record['status'],json.dumps(record,ensure_ascii=False,sort_keys=True),now,now))
    def get_capability(self,capability_id:str):
        with self._session() as c: row=c.execute('SELECT record_json FROM capabilities WHERE capability_id=?',(capability_id,)).fetchone()
        return json.loads(row['record_json']) if row else None
    def list_capabilities(self,status:str|None=None):
        with self._session() as c:
            if status is None: rows=c.execute('SELECT record_json FROM capabilities ORDER BY created_at,capability_id').fetchall()
            else: rows=c.execute('SELECT record_json FROM capabilities WHERE status=? ORDER BY created_at,capability_id',(status,)).fetchall()
        return [json.loads(row['record_json']) for row in rows]
    def update_capability(self,record:dict[str,Any],expected_status:str)->bool:
        with self._session() as c:
            cur=c.execute('UPDATE capabilities SET status=?,record_json=?,updated_at=? WHERE capability_id=? AND status=?',
                          (record['status'],json.dumps(record,ensure_ascii=False,sort_keys=True),time.time(),record['capability_id'],expected_status))
        return cur.rowcount==1
    def list_tasks(self,limit:int=100):
        bounded=max(1,min(int(limit),200))
        with self._session() as c:
            rows=c.execute('SELECT task_id,agent_id,status,payload_json,result_json,created_at,updated_at FROM tasks ORDER BY created_at DESC LIMIT ?',(bounded,)).fetchall()
        items=[]
        for row in rows:
            item=dict(row)
            payload=json.loads(item.pop('payload_json') or '{}')
            item['objective']=payload.get('objective','')
            item['inputs']=payload.get('inputs',{})
            item['source_refs']=payload.get('source_refs',[])
            item['provider_route']=payload.get('provider_route')
            item['requested_skill_ids']=payload.get('requested_skill_ids',[])
            item['parent_task_id']=payload.get('parent_task_id')
            item['result']=json.loads(item.pop('result_json')) if item.get('result_json') else None
            items.append(item)
        return items

    def list_proposals(self,limit:int=100):
        bounded=max(1,min(int(limit),200))
        with self._session() as c:
            rows=c.execute('SELECT proposal_id,agent_id,base_version,candidate_version,changes,protected_change,benchmark_id,status,evaluation_json,created_at,protected_fields_json,evaluation_context_json FROM proposals ORDER BY created_at DESC LIMIT ?',(bounded,)).fetchall()
        items=[]
        for row in rows:
            item=dict(row)
            item['protected_change']=bool(item['protected_change'])
            item['evaluation']=json.loads(item.pop('evaluation_json')) if item.get('evaluation_json') else None
            item['protected_fields']=json.loads(item.pop('protected_fields_json') or '[]')
            item['evaluation_context']=json.loads(item.pop('evaluation_context_json') or '{}')
            items.append(item)
        return items

    @staticmethod
    def _creator_project_row(row):
        if not row: return None
        item=dict(row); item["channel_profile"]=json.loads(item.pop("channel_profile_json")); return item

    @staticmethod
    def _creator_version_row(row):
        if not row: return None
        item=dict(row); item["content"]=json.loads(item.pop("content_json")); return item

    @staticmethod
    def _creator_asset_row(row):
        if not row: return None
        item=dict(row); item["provenance"]=json.loads(item.pop("provenance_json")); item["license"]=json.loads(item.pop("license_json")); return item

    @staticmethod
    def _creator_render_job_row(row):
        if not row: return None
        item=dict(row); item["resource_limits"]=json.loads(item.pop("resource_limits_json")); item["result_manifest"]=json.loads(item.pop("result_manifest_json")); return item

    def create_creator_project(self,project,actor):
        now=time.time()
        with self._session() as c:
            c.execute("INSERT INTO creator_projects(project_id,title,topic,channel_profile_json,language,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (project["project_id"],project["title"],project["topic"],json.dumps(project["channel_profile"],ensure_ascii=False,sort_keys=True),project["language"],"idea",now,now))
            c.execute("INSERT INTO events(ts,event_type,payload_json) VALUES(?,?,?)",(now,"creator_project_created",json.dumps({"project_id":project["project_id"],"actor":actor},ensure_ascii=False,sort_keys=True)))
        return self.get_creator_project(project["project_id"])

    def get_creator_project(self,project_id):
        with self._session() as c: row=c.execute("SELECT * FROM creator_projects WHERE project_id=?",(project_id,)).fetchone()
        return self._creator_project_row(row)

    def list_creator_projects(self,limit=50):
        bounded=max(1,min(int(limit),200))
        with self._session() as c: rows=c.execute("SELECT * FROM creator_projects ORDER BY updated_at DESC,project_id LIMIT ?",(bounded,)).fetchall()
        return [self._creator_project_row(row) for row in rows]

    def transition_creator_project(self,project_id,expected_status,next_status,actor,evidence):
        now=time.time()
        with self._session() as c:
            cur=c.execute("UPDATE creator_projects SET status=?,updated_at=? WHERE project_id=? AND status=?",(next_status,now,project_id,expected_status))
            if cur.rowcount!=1:return None
            c.execute("INSERT INTO events(ts,event_type,payload_json) VALUES(?,?,?)",(now,"creator_project_transition",json.dumps({"project_id":project_id,"from":expected_status,"to":next_status,"actor":actor,"evidence":evidence},ensure_ascii=False,sort_keys=True)))
            row=c.execute("SELECT * FROM creator_projects WHERE project_id=?",(project_id,)).fetchone()
        return self._creator_project_row(row)

    def create_creator_version(self,project_id,version_id,kind,content,parent_version_id,actor):
        now=time.time()
        with self._session() as c:
            c.execute("BEGIN IMMEDIATE")
            if not c.execute("SELECT 1 FROM creator_projects WHERE project_id=?",(project_id,)).fetchone():raise ValueError("Unknown creator project.")
            if parent_version_id and not c.execute("SELECT 1 FROM creator_project_versions WHERE project_id=? AND version_id=?",(project_id,parent_version_id)).fetchone():raise ValueError("Parent version does not belong to this project.")
            row=c.execute("SELECT COALESCE(MAX(version_no),0)+1 AS next_version FROM creator_project_versions WHERE project_id=?",(project_id,)).fetchone()
            version_no=int(row["next_version"])
            c.execute("INSERT INTO creator_project_versions(version_id,project_id,version_no,kind,content_json,parent_version_id,created_at) VALUES(?,?,?,?,?,?,?)",(version_id,project_id,version_no,kind,json.dumps(content,ensure_ascii=False,sort_keys=True,allow_nan=False),parent_version_id,now))
            c.execute("INSERT INTO events(ts,event_type,payload_json) VALUES(?,?,?)",(now,"creator_version_created",json.dumps({"project_id":project_id,"version_id":version_id,"version_no":version_no,"kind":kind,"actor":actor},ensure_ascii=False,sort_keys=True)))
            result=c.execute("SELECT * FROM creator_project_versions WHERE version_id=?",(version_id,)).fetchone()
        return self._creator_version_row(result)

    def list_creator_versions(self,project_id):
        with self._session() as c: rows=c.execute("SELECT * FROM creator_project_versions WHERE project_id=? ORDER BY version_no",(project_id,)).fetchall()
        return [self._creator_version_row(row) for row in rows]

    def create_creator_asset(self,asset):
        with self._session() as c:
            c.execute("INSERT INTO creator_project_assets(asset_id,project_id,version_id,kind,storage_key,sha256,byte_size,mime_type,provenance_json,license_json,qa_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(asset["asset_id"],asset["project_id"],asset["version_id"],asset["kind"],asset["storage_key"],asset["sha256"],asset["byte_size"],asset["mime_type"],json.dumps(asset["provenance"],ensure_ascii=False,sort_keys=True),json.dumps(asset["license"],ensure_ascii=False,sort_keys=True),asset["qa_status"],time.time()))
            row=c.execute("SELECT * FROM creator_project_assets WHERE asset_id=?",(asset["asset_id"],)).fetchone()
        return self._creator_asset_row(row)

    def list_creator_assets(self,project_id,version_id=None):
        with self._session() as c:
            if version_id: rows=c.execute("SELECT * FROM creator_project_assets WHERE project_id=? AND version_id=? ORDER BY created_at,asset_id",(project_id,version_id)).fetchall()
            else: rows=c.execute("SELECT * FROM creator_project_assets WHERE project_id=? ORDER BY created_at,asset_id",(project_id,)).fetchall()
        return [self._creator_asset_row(row) for row in rows]

    def create_creator_render_job(self,job):
        with self._session() as c:
            cur=c.execute("INSERT OR IGNORE INTO creator_render_jobs(job_id,project_id,version_id,engine_commit,style_id,status,idempotency_key,request_hash,resource_limits_json,result_manifest_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(job["job_id"],job["project_id"],job["version_id"],job["engine_commit"],job["style_id"],job["status"],job["idempotency_key"],job["request_hash"],json.dumps(job["resource_limits"],ensure_ascii=False,sort_keys=True),json.dumps(job["result_manifest"],ensure_ascii=False,sort_keys=True),job["created_at"],job["updated_at"]))
            row=c.execute("SELECT * FROM creator_render_jobs WHERE idempotency_key=?",(job["idempotency_key"],)).fetchone()
            if not row:raise ValueError("Render job could not be stored.")
            if row["request_hash"]!=job["request_hash"]:raise ValueError("Idempotency key reused for a different render request.")
            result=self._creator_render_job_row(row); result["idempotent_replay"]=cur.rowcount==0
        return result

    def get_creator_render_job(self,job_id):
        with self._session() as c: row=c.execute("SELECT * FROM creator_render_jobs WHERE job_id=?",(job_id,)).fetchone()
        return self._creator_render_job_row(row)

    def list_creator_render_jobs(self,project_id,limit=50):
        bounded=max(1,min(int(limit),200))
        with self._session() as c: rows=c.execute("SELECT * FROM creator_render_jobs WHERE project_id=? ORDER BY created_at DESC LIMIT ?",(project_id,bounded)).fetchall()
        return [self._creator_render_job_row(row) for row in rows]

    def transition_creator_render_job(self,job_id,expected_status,next_status,result_manifest):
        now=time.time()
        with self._session() as c:
            cur=c.execute("UPDATE creator_render_jobs SET status=?,result_manifest_json=?,updated_at=? WHERE job_id=? AND status=?",(next_status,json.dumps(result_manifest,ensure_ascii=False,sort_keys=True),now,job_id,expected_status))
            if cur.rowcount!=1:return None
            c.execute("INSERT INTO events(ts,event_type,payload_json) VALUES(?,?,?)",(now,"creator_render_job_transition",json.dumps({"job_id":job_id,"from":expected_status,"to":next_status},ensure_ascii=False,sort_keys=True)))
            row=c.execute("SELECT * FROM creator_render_jobs WHERE job_id=?",(job_id,)).fetchone()
        return self._creator_render_job_row(row)

