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
            CREATE INDEX IF NOT EXISTS idx_idempotency_claims_state_updated ON idempotency_claims(state,updated_at);
            CREATE TABLE IF NOT EXISTS outcomes(outcome_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, task_id TEXT, success INTEGER NOT NULL, feedback TEXT NOT NULL, provenance_json TEXT NOT NULL, created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS proposals(proposal_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, base_version TEXT NOT NULL, candidate_version TEXT NOT NULL, candidate_instruction TEXT NOT NULL, changes TEXT NOT NULL, protected_change INTEGER NOT NULL, benchmark_id TEXT NOT NULL, status TEXT NOT NULL, evaluation_json TEXT, created_at REAL NOT NULL, protected_fields_json TEXT NOT NULL DEFAULT '[]', evaluation_context_json TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS agent_versions(agent_id TEXT NOT NULL, version TEXT NOT NULL, instruction TEXT NOT NULL, change_log TEXT NOT NULL, active INTEGER NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(agent_id,version));
            CREATE TABLE IF NOT EXISTS baselines(agent_id TEXT NOT NULL, benchmark_id TEXT NOT NULL, report_json TEXT NOT NULL, created_at REAL NOT NULL, active_version TEXT, instruction_sha256 TEXT, report_sha256 TEXT, PRIMARY KEY(agent_id,benchmark_id));
            CREATE TABLE IF NOT EXISTS capabilities(capability_id TEXT PRIMARY KEY, status TEXT NOT NULL, record_json TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_capabilities_status_updated ON capabilities(status,updated_at);
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
