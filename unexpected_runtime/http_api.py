from __future__ import annotations
import asyncio, hmac, json, os, threading, time, math, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit, parse_qs
from .web_ui import read_index, read_asset
from . import __version__
from .coordinator import Coordinator

MAX_BODY_BYTES=64*1024
MAX_OBJECTIVE_CHARS=16000
RATE_LIMIT_PER_MINUTE=30
SOCKET_TIMEOUT_SECONDS=10
MAX_SOURCE_REF_CHARS=2048


def _safe_provider_diagnostic(provider, exc):
    """Return a bounded provider error without exposing host-stored credentials."""
    from .providers import ProviderError

    if not isinstance(exc, ProviderError):
        return f"Provider request failed ({type(exc).__name__})."
    message = " ".join(str(exc).split())
    for attribute in ("_api_key", "_token"):
        secret = getattr(provider, attribute, None) if provider is not None else None
        if isinstance(secret, str) and secret:
            message = message.replace(secret, "[redacted]")
    return (message or "Provider rejected the connection test.")[:400]


class _RateLimiter:
    def __init__(self, limit=None): self.lock=threading.Lock(); self.entries={}; self.limit=limit
    def allow(self, identity):
        now=time.monotonic()
        with self.lock:
            start,count=self.entries.get(identity,(now,0))
            if now-start>=60: start,count=now,0
            count+=1; self.entries[identity]=(start,count)
            if len(self.entries)>2000: self.entries={k:v for k,v in self.entries.items() if now-v[0]<60}
            return count<=(self.limit if self.limit is not None else RATE_LIMIT_PER_MINUTE)

def create_server(*, coordinator=None, api_token=None, host="127.0.0.1", port=0):
    active=coordinator or Coordinator()
    token=(os.getenv("UNEXPECTED_RUNTIME_API_TOKEN","") if api_token is None else str(api_token or "")).strip()
    limiter=_RateLimiter()
    lifecycle_limiter=_RateLimiter(limit=3)
    quality_limiter=_RateLimiter(limit=3)
    android_video_limiter=_RateLimiter(limit=2)
    # Reserve one task-pool worker for ordinary /v1/invoke requests.
    lifecycle_slots=threading.BoundedSemaphore(max(1, active.max_workers - 1))
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(SOCKET_TIMEOUT_SECONDS)
            super().setup()
        server_version="uneXpectedRuntime/8"; sys_version=""
        def log_message(self, fmt, *args): return
        def send_json(self, code, obj):
            data=json.dumps(obj,ensure_ascii=False).encode()
            self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Content-Length",str(len(data))); self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff"); self.send_header("Referrer-Policy","no-referrer")
            self.end_headers(); self.wfile.write(data)
        def send_bytes(self, code, data, content_type):
            self.send_response(code)
            self.send_header("Content-Type",content_type)
            self.send_header("Content-Length",str(len(data)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Referrer-Policy","no-referrer")
            self.send_header("Content-Security-Policy","default-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; object-src 'none'")
            self.end_headers()
            self.wfile.write(data)
        @staticmethod
        def bounded_limit(query, default=50):
            try: value=int((query.get("limit") or [str(default)])[0])
            except (TypeError,ValueError): value=default
            return max(1,min(value,200))
        @staticmethod
        def event_items(rows):
            items=[]
            for row in rows:
                item=dict(row)
                raw=item.pop("payload_json",None)
                try: item["payload"]=json.loads(raw) if raw else {}
                except (TypeError,ValueError): item["payload"]={}
                items.append(item)
            return items
        def authorize(self):
            if len(token)<32 or not token.isascii():
                self.send_json(503,{"error":"Runtime API is locked."}); return False
            supplied = self.headers.get("Authorization", "")
            try:
                supplied_bytes = supplied.encode("ascii")
                expected_bytes = ("Bearer " + token).encode("ascii")
            except UnicodeEncodeError:
                self.send_json(401,{"error":"Unauthorized."}); return False
            if not hmac.compare_digest(supplied_bytes, expected_bytes):
                self.send_json(401,{"error":"Unauthorized."}); return False
            return True
        def read_body(self):
            raw_length=self.headers.get("Content-Length")
            if raw_length is None:
                self.send_json(411,{"error":"Content-Length is required."}); return None
            try: length=int(raw_length)
            except ValueError: self.send_json(400,{"error":"Invalid Content-Length."}); return None
            if length<0: self.send_json(400,{"error":"Invalid Content-Length."}); return None
            if length>MAX_BODY_BYTES: self.send_json(413,{"error":"Request body too large."}); return None
            try: obj=json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError,json.JSONDecodeError): self.send_json(400,{"error":"Body must be valid UTF-8 JSON."}); return None
            if not isinstance(obj,dict): self.send_json(400,{"error":"Body must be a JSON object."}); return None
            return obj
        def handle_mcp_post(self):
            if not self.authorize():
                return
            if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
                return self.send_json(400, {"error": "MCP requests must use application/json."})
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                return self.send_json(411, {"error": "Content-Length is required."})
            try:
                length = int(raw_length)
            except ValueError:
                return self.send_json(400, {"error": "Invalid Content-Length."})
            if length < 0:
                return self.send_json(400, {"error": "Invalid Content-Length."})
            if length > MAX_BODY_BYTES:
                return self.send_json(413, {"error": "MCP request body too large."})
            try:
                body = self.rfile.read(length)
            except OSError:
                return
            if len(body) != length:
                return self.send_json(400, {"error": "Incomplete MCP request body."})
            from .mcp_server import build_mcp_server
            try:
                server, app = build_mcp_server(active)
                headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in self.headers.items()]
                proto = self.headers.get("X-Forwarded-Proto", "http").split(",", 1)[0].strip()
                scope = {
                    "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
                    "http_version": self.request_version.replace("HTTP/", ""), "method": "POST",
                    "scheme": proto if proto in {"http", "https"} else "https",
                    "path": "/mcp", "raw_path": b"/mcp",
                    "query_string": urlsplit(self.path).query.encode("ascii", errors="ignore"),
                    "root_path": "", "headers": headers, "client": self.client_address,
                    "server": self.server.server_address, "state": {},
                }
                messages, received = [], False
                async def receive():
                    nonlocal received
                    if not received:
                        received = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    return {"type": "http.disconnect"}
                async def send(message):
                    messages.append(message)
                async def dispatch():
                    async with server.session_manager.run():
                        await app(scope, receive, send)
                asyncio.run(dispatch())
                start = next((m for m in messages if m.get("type") == "http.response.start"), None)
                if start is None:
                    return self.send_json(502, {"error": "MCP transport returned no HTTP response."})
                response_body = b"".join(m.get("body", b"") for m in messages if m.get("type") == "http.response.body")
                self.send_response(int(start.get("status", 500)))
                has_length = False
                for name, value in start.get("headers", []):
                    if name.lower() == b"content-length":
                        has_length = True
                    self.send_header(name.decode("latin-1"), value.decode("latin-1"))
                if not has_length:
                    self.send_header("Content-Length", str(len(response_body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                if response_body:
                    self.wfile.write(response_body)
            except OSError:
                return
            except Exception:
                return self.send_json(500, {"error": "MCP request failed."})

        def do_GET(self):
            parsed=urlsplit(self.path)
            path=parsed.path
            if path=="/":
                try: return self.send_bytes(200,read_index(),"text/html; charset=utf-8")
                except OSError: return self.send_json(503,{"error":"Command center assets are unavailable."})
            if path.startswith("/assets/"):
                asset=read_asset(path[len("/assets/"):])
                if asset is None: return self.send_json(404,{"error":"Not found."})
                data,mime=asset
                return self.send_bytes(200,data,mime+("; charset=utf-8" if mime.startswith(("text/","application/javascript")) else ""))
            if path=="/health":
                provider=getattr(active,"provider",None)
                store=getattr(active,"store",None)
                try: storage_healthy=bool(store.check_health()) if callable(getattr(store,"check_health",None)) else True
                except Exception: storage_healthy=False
                return self.send_json(200 if storage_healthy else 503,{"ok":storage_healthy,"service":"uneXpected command center","version":__version__,
                    "storage":"ready" if storage_healthy else "unavailable",
                    "provider":getattr(provider,"name",type(provider).__name__ if provider else "unavailable"),
                    "provider_configured":bool(getattr(provider,"configured",True)),
                    "authentication_configured":len(token)>=32,"privileged_actions":"fail-closed"})
            if path=="/mobile" or path.startswith("/mobile/"):
                return self.send_json(404,{"error":"Not found."})
            if not path.startswith("/v1/"): return self.send_json(404,{"error":"Not found."})
            if not self.authorize(): return
            query=parse_qs(parsed.query)
            limit=self.bounded_limit(query)
            android_video_file=re.fullmatch(r"/v1/creator/android-videos/([0-9a-f]{32})/file",path)
            android_video_detail=re.fullmatch(r"/v1/creator/android-videos/([0-9a-f]{32})",path)
            if path=="/v1/creator/android-lite/status":
                from .android_lite_video import AndroidLiteVideoCreator
                return self.send_json(200,{"preflight":AndroidLiteVideoCreator.from_environment().preflight()})
            if android_video_file or android_video_detail:
                from .android_lite_video import AndroidLiteVideoCreator, AndroidLiteVideoError
                creator=AndroidLiteVideoCreator.from_environment()
                video_id=(android_video_file or android_video_detail).group(1)
                try:
                    if android_video_file:
                        return self.send_bytes(200,creator.read_video(video_id),"video/mp4")
                    return self.send_json(200,{"video":creator.get_video(video_id)})
                except AndroidLiteVideoError:
                    return self.send_json(404,{"error":"Android Lite video was not found or failed checksum verification."})
            if path=="/v1/status":
                raw=active.status()
                provider=getattr(active,"provider",None)
                store=getattr(active,"store",None)
                backend="postgres" if type(store).__name__.lower().startswith("postgres") else "sqlite-local"
                try: storage_healthy=bool(store.check_health()) if callable(getattr(store,"check_health",None)) else True
                except Exception: storage_healthy=False
                return self.send_json(200,{
                    "version":__version__,
                    "health":{"ok":storage_healthy,"status":"ready" if storage_healthy else "degraded","detail":"HTTP application and coordinator are responding." if storage_healthy else "Shared state store is unavailable."},
                    "ecosystem_version":raw.get("ecosystem_version"),
                    "registered_agents":len(active.registry),
                    "provider":getattr(provider,"name",type(provider).__name__ if provider else "unavailable"),
                    "mode":raw.get("mode"),
                    "max_workers":raw.get("max_workers"),
                    "max_retries":raw.get("max_retries"),
                    "storage":{"backend":backend,"status":"ready" if storage_healthy else "unavailable","healthy":storage_healthy,"recovery":"not verified"},
                    "governance":{"privileged_actions":"disabled","approval_authority":"not verified","replay_protection":"not verified"},
                    "approval_verifier_configured":bool(getattr(active,"approval_verifier",None))
                })
            if path=="/v1/creator/status":
                from .creator_studio import ENGINE_COMMIT
                service=getattr(active,"creator_studio",None)
                dispatcher=getattr(service,"render_dispatcher",None) if service else None
                enabled=bool(getattr(dispatcher,"enabled",False))
                return self.send_json(200,{
                    "engine":"lemo-opuscar","engine_commit":ENGINE_COMMIT,"upstream_license":"MIT",
                    "renderer_configured":enabled,
                    "renderer_status":"enabled" if enabled else "blocked",
                    "artifact_storage_configured":bool(getattr(service,"artifact_store",None)) if service else False,
                    "publishing_enabled":False
                })
            if path=="/v1/creator/projects":
                items=active.creator_studio.list_projects(limit)
                return self.send_json(200,{"count":len(items),"items":items})
            project_detail=re.fullmatch(r"/v1/creator/projects/([0-9a-fA-F-]{36})",path)
            if project_detail:
                try:
                    return self.send_json(200,active.creator_studio.get_project_detail(project_detail.group(1),limit))
                except Exception as exc:
                    from .creator_studio import CreatorStudioNotFound
                    if isinstance(exc,CreatorStudioNotFound):
                        return self.send_json(404,{"error":"Creator Studio project was not found."})
                    return self.send_json(400,{"error":"Could not retrieve Creator Studio project."})
            render_detail=re.fullmatch(r"/v1/creator/render-jobs/([A-Za-z0-9._:-]{8,128})",path)
            if render_detail:
                try:
                    job=active.creator_studio.get_render_job(render_detail.group(1))
                    return self.send_json(200,{"job":job,"progress":job.get("result_manifest") or {}})
                except Exception as exc:
                    from .creator_studio import CreatorStudioNotFound
                    if isinstance(exc,CreatorStudioNotFound):
                        return self.send_json(404,{"error":"Creator Studio render job was not found."})
                    return self.send_json(400,{"error":"Could not retrieve Creator Studio render job."})
            if path=="/v1/skills":
                items=[skill.public_dict() for skill in active.skills.list()]
                return self.send_json(200,{"count":len(items),"items":items})
            if path=="/v1/agents":
                items=active.list_agents()
                return self.send_json(200,{"count":len(items),"items":items})
            if path=="/v1/tasks":
                items=active.store.list_tasks(limit)
                return self.send_json(200,{"count":len(items),"items":items})
            if path=="/v1/events":
                task_filter=(query.get("task_id") or [None])[0]
                rows=active.store.events(200 if task_filter else limit)
                items=self.event_items(rows)
                if task_filter: items=[item for item in items if item.get("task_id")==task_filter]
                return self.send_json(200,{"count":len(items),"items":items})
            if path.startswith("/v1/tasks/") and path.endswith("/events"):
                task_id=path[len("/v1/tasks/"):-len("/events")].strip("/")
                if not task_id or "/" in task_id:
                    return self.send_json(404,{"error":"Not found."})
                if not active.store.get_task(task_id):
                    return self.send_json(404,{"error":"Unknown task."})
                after_values=query.get("after",["0"])
                if len(after_values)!=1:
                    return self.send_json(400,{"error":"after must be a single non-negative event cursor."})
                try:
                    after_event_id=int(after_values[0])
                except (TypeError,ValueError):
                    return self.send_json(400,{"error":"after must be a single non-negative event cursor."})
                if after_event_id<0:
                    return self.send_json(400,{"error":"after must be a non-negative event cursor."})
                page_limit=self.bounded_limit(query,default=50)
                try:
                    rows=active.store.list_task_events(task_id,after_event_id=after_event_id,limit=page_limit+1)
                except (TypeError,ValueError):
                    return self.send_json(400,{"error":"Invalid task event cursor or page size."})
                has_more=len(rows)>page_limit
                items=self.event_items(rows[:page_limit])
                next_cursor=items[-1]["event_id"] if items else after_event_id
                return self.send_json(200,{"task_id":task_id,"count":len(items),"items":items,
                                           "next_cursor":next_cursor,"has_more":has_more})
            if path.startswith("/v1/tasks/"):
                task_id=path[len("/v1/tasks/"):]
                if not task_id or "/" in task_id: return self.send_json(404,{"error":"Not found."})
                row=active.store.get_task(task_id)
                if not row: return self.send_json(404,{"error":"Unknown task."})
                item=dict(row)
                try: payload=json.loads(item.pop("payload_json") or "{}")
                except (TypeError,ValueError): payload={}
                raw_result=item.pop("result_json",None)
                try: result=json.loads(raw_result) if raw_result else None
                except (TypeError,ValueError): result=None
                item.update({"objective":payload.get("objective",""),"inputs":payload.get("inputs",{}),
                             "source_refs":payload.get("source_refs",[]),"provider_route":payload.get("provider_route"),
                             "requested_skill_ids":payload.get("requested_skill_ids",[]),
                             "parent_task_id":payload.get("parent_task_id"),
                             "result":result})
                return self.send_json(200,{"task":item})
            if path=="/v1/resources":
                from .resource_intelligence import ResourceRegistry
                registry=ResourceRegistry()
                items=registry.list_resources(
                    category=(query.get("category") or [None])[0],
                    status=(query.get("status") or [None])[0],
                )
                summary=registry.summary()
                return self.send_json(200,{"count":len(items[:limit]),"summary":summary,"items":items[:limit]})
            if path=="/v1/quality-evaluations":
                reports=[]
                for row in active.store.events(1000):
                    if row.get("event_type")!="quality_evaluation_report":
                        continue
                    try:
                        payload=json.loads(row.get("payload_json") or "{}")
                    except (TypeError,ValueError):
                        continue
                    if isinstance(payload,dict) and payload.get("evaluation_id"):
                        reports.append(payload)
                return self.send_json(200,{"count":len(reports[:limit]),"items":reports[:limit]})
            if path=="/v1/capabilities":
                items=active.store.list_capabilities()
                return self.send_json(200,{"count":len(items),"items":items})
            if path=="/v1/mcp/tools":
                items=active.mcp_gateway.list_tools()
                return self.send_json(200,{"count":len(items),"items":items})
            if path=="/v1/improvements":
                items=active.store.list_proposals(limit)
                return self.send_json(200,{"count":len(items),"items":items})
            if path.startswith("/v1/improvements/"):
                proposal_id=path[len("/v1/improvements/"):]
                if not proposal_id or "/" in proposal_id: return self.send_json(404,{"error":"Not found."})
                proposal=active.store.get_proposal(proposal_id)
                if not proposal: return self.send_json(404,{"error":"Unknown improvement proposal."})
                proposal.pop("candidate_instruction",None)
                return self.send_json(200,{"proposal":proposal})
            if path=="/v1/providers":
                provider=getattr(active,"provider",None)
                if hasattr(provider,"status"):
                    items=provider.status()
                elif provider is not None:
                    items=[{"id":"default","name":getattr(provider,"name",type(provider).__name__),
                            "configured":bool(getattr(provider,"configured",True)),
                            "verified":bool(getattr(provider,"verified",False)),
                            "model":getattr(provider,"model",None),"default":True,"live":True}]
                else:
                    items=[]
                return self.send_json(200,{"providers":items})
            if path=="/v1/approvals":
                return self.send_json(200,{"count":0,"items":[],"message":"No pending approval records are exposed. Privileged execution remains disabled."})
            return self.send_json(404,{"error":"Not found."})
        def do_POST(self):
            route=urlsplit(self.path).path
            if route == "/mcp":
                return self.handle_mcp_post()
            creator_match=re.fullmatch(r"/v1/creator/projects/([0-9a-fA-F-]{36})/(versions|render-jobs|produce)",route)
            is_creator_project=route=="/v1/creator/projects"
            is_creator_version=bool(creator_match and creator_match.group(2)=="versions")
            is_creator_render=bool(creator_match and creator_match.group(2)=="render-jobs")
            is_creator_produce=bool(creator_match and creator_match.group(2)=="produce")
            is_creator=is_creator_project or is_creator_version or is_creator_render or is_creator_produce
            is_android_video=route=="/v1/creator/android-videos"
            if route not in {"/v1/invoke", "/v1/lifecycle", "/v1/providers/test", "/v1/improvements/propose", "/v1/quality-evaluations", "/v1/subagents/run"} and not is_creator and not is_android_video: return self.send_json(404,{"error":"Not found."})
            is_lifecycle=route=="/v1/lifecycle"
            is_provider_test=route=="/v1/providers/test"
            is_improvement_propose=route=="/v1/improvements/propose"
            is_quality_evaluation=route=="/v1/quality-evaluations"
            is_subagents_run=route=="/v1/subagents/run"
            if not self.authorize(): return
            identity=self.client_address[0] if self.client_address else "unknown"
            active_limiter=android_video_limiter if is_android_video else (lifecycle_limiter if is_lifecycle else (quality_limiter if is_quality_evaluation else limiter))
            if not active_limiter.allow(identity): return self.send_json(429,{"error":"Request rate limit exceeded."})
            body=self.read_body()
            if body is None: return
            if is_android_video:
                allowed={"title","script","format","narration"}
                if set(body)-allowed:
                    return self.send_json(400,{"error":"Unsupported Android Lite video fields."})
                try:
                    from .android_lite_video import AndroidLiteVideoCreator, AndroidLiteVideoError
                    creator=AndroidLiteVideoCreator.from_environment()
                    video=creator.render(
                        body.get("title"),body.get("script"),
                        video_format=body.get("format","vertical"),
                        narration=body.get("narration","auto"),
                    )
                    return self.send_json(201,{"video":video})
                except AndroidLiteVideoError as exc:
                    return self.send_json(409,{"blocked":True,"error":str(exc)})
                except Exception as exc:
                    return self.send_json(500,{"error":"Android Lite video rendering failed ("+type(exc).__name__+")."})
            if is_creator_project:
                allowed={"title","topic","language","channel_profile"}
                if set(body)-allowed: return self.send_json(400,{"error":"Unsupported Creator Studio project fields."})
                try:
                    project=active.creator_studio.create_project(body,actor="command-center-api")
                    return self.send_json(201,{"project":project})
                except Exception as exc:
                    from .creator_studio import CreatorStudioError
                    if isinstance(exc,CreatorStudioError): return self.send_json(400,{"error":str(exc)})
                    return self.send_json(500,{"error":"Creator Studio project creation failed."})
            if is_creator_produce:
                allowed={"resume"}
                if set(body)-allowed or ("resume" in body and not isinstance(body["resume"], bool)):
                    return self.send_json(400,{"error":"Creator Team accepts only a boolean resume field."})
                if os.getenv("UNEXPECTED_AI_MODE", "standard").strip().lower() not in {"local_only", "local-only"}:
                    return self.send_json(409,{"blocked":True,"error":"Creator Team requires UNEXPECTED_AI_MODE=local_only."})
                try:
                    result=active.creator_team.run(creator_match.group(1),actor="command-center-api",
                                                   resume=body.get("resume",True))
                    return self.send_json(200,{"result":result})
                except Exception as exc:
                    from .creator_team import CreatorTeamError
                    if isinstance(exc,CreatorTeamError):
                        return self.send_json(409,{"blocked":True,"error":str(exc)})
                    return self.send_json(500,{"error":"Local Creator Team execution failed."})
            if is_creator_version:
                allowed={"kind","content","parent_version_id"}
                if set(body)-allowed: return self.send_json(400,{"error":"Unsupported Creator Studio version fields."})
                if not isinstance(body.get("kind"),str) or not isinstance(body.get("content"),dict):
                    return self.send_json(400,{"error":"kind and object content are required."})
                try:
                    version=active.creator_studio.save_version(creator_match.group(1),body["kind"],body["content"],
                        body.get("parent_version_id"),actor="command-center-api")
                    return self.send_json(201,{"version":version})
                except Exception as exc:
                    from .creator_studio import CreatorStudioNotFound,CreatorStudioError
                    if isinstance(exc,CreatorStudioNotFound): return self.send_json(404,{"error":str(exc)})
                    if isinstance(exc,CreatorStudioError): return self.send_json(400,{"error":str(exc)})
                    return self.send_json(500,{"error":"Creator Studio version save failed."})
            if is_creator_render:
                allowed={"version_id","style_id","idempotency_key","resource_limits","request"}
                if set(body)-allowed: return self.send_json(400,{"error":"Unsupported Creator Studio render fields."})
                for field in ("version_id","style_id","idempotency_key"):
                    if not isinstance(body.get(field),str) or not body[field].strip():
                        return self.send_json(400,{"error":field+" is required."})
                try:
                    from .creator_studio import ENGINE_COMMIT
                    job=active.creator_studio.create_render_job({
                        "project_id":creator_match.group(1),"version_id":body["version_id"],
                        "engine_commit":ENGINE_COMMIT,"style_id":body["style_id"],
                        "idempotency_key":body["idempotency_key"],
                        "resource_limits":body.get("resource_limits",{}),"request":body.get("request",{})})
                    if job.get("status")=="blocked":
                        return self.send_json(503,{"blocked":True,"reason":"renderer_unavailable",
                            "job":job,"progress":job.get("result_manifest") or {}})
                    return self.send_json(202,{"job":job,"progress":job.get("result_manifest") or {}})
                except Exception as exc:
                    from .creator_studio import CreatorStudioConflict,CreatorStudioNotFound,CreatorStudioError
                    if isinstance(exc,CreatorStudioConflict): return self.send_json(409,{"error":str(exc)})
                    if isinstance(exc,CreatorStudioNotFound): return self.send_json(404,{"error":str(exc)})
                    if isinstance(exc,CreatorStudioError): return self.send_json(400,{"error":str(exc)})
                    return self.send_json(500,{"error":"Creator Studio render request failed."})

            if is_subagents_run:
                allowed={"parent_task_id","parent_agent_id","children","max_depth"}
                if set(body)-allowed:
                    return self.send_json(400,{"error":"Unsupported subagent delegation fields."})
                parent_task_id=body.get("parent_task_id")
                parent_agent_id=body.get("parent_agent_id")
                children=body.get("children")
                max_depth=body.get("max_depth",2)
                if (not isinstance(parent_task_id,str) or not parent_task_id.strip()
                        or not isinstance(parent_agent_id,str) or not parent_agent_id.strip()
                        or not isinstance(children,list) or len(children)>3
                        or isinstance(max_depth,bool) or not isinstance(max_depth,int)):
                    return self.send_json(400,{"error":"Invalid subagent delegation request."})
                try:
                    result=active.run_subagents(parent_task_id=parent_task_id,
                                                parent_agent_id=parent_agent_id,
                                                children=children,max_depth=max_depth)
                    return self.send_json(200,{"result":result})
                except Exception as exc:
                    return self.send_json(400,{"error":f"Subagent delegation rejected ({type(exc).__name__})."})
            if is_quality_evaluation:
                allowed_quality={"provider_route","scenario_ids"}
                if set(body)-allowed_quality:
                    return self.send_json(400,{"error":"Unsupported quality evaluation fields."})
                provider_route=body.get("provider_route")
                scenario_ids=body.get("scenario_ids")
                if not isinstance(provider_route,str) or not provider_route.strip():
                    return self.send_json(400,{"error":"An explicit provider_route is required."})
                if scenario_ids is not None and (
                    not isinstance(scenario_ids,list) or len(scenario_ids)>8
                    or any(not isinstance(item,str) or not item for item in scenario_ids)
                ):
                    return self.send_json(400,{"error":"scenario_ids must be a list of at most 8 non-empty IDs."})
                try:
                    from .quality_evaluation import QualityEvaluationRunner, QualityEvaluationError
                    report=QualityEvaluationRunner(active).run(provider_route=provider_route.strip(),scenario_ids=scenario_ids)
                    status_code=409 if report.get("status")=="blocked" else 200
                    return self.send_json(status_code,{"report":report})
                except QualityEvaluationError as exc:
                    return self.send_json(400,{"error":str(exc)})
                except Exception as exc:
                    return self.send_json(500,{"error":f"Quality evaluation failed ({type(exc).__name__})."})
            if is_improvement_propose:
                allowed_proposal={"agent_id","candidate_instruction","changes","benchmark_id","protected_fields"}
                if set(body)-allowed_proposal: return self.send_json(400,{"error":"Unsupported proposal fields."})
                agent=body.get("agent_id")
                candidate=body.get("candidate_instruction")
                changes=body.get("changes")
                benchmark=body.get("benchmark_id")
                protected_fields=body.get("protected_fields",[])
                if (not isinstance(agent,str) or not agent.strip() or not isinstance(candidate,str)
                        or not candidate.strip() or len(candidate)>20000
                        or not isinstance(changes,str) or not changes.strip() or len(changes)>5000
                        or not isinstance(benchmark,str) or not benchmark.strip()
                        or not isinstance(protected_fields,list) or len(protected_fields)>16
                        or any(not isinstance(item,str) for item in protected_fields)):
                    return self.send_json(400,{"error":"Invalid improvement proposal fields."})
                try:
                    from .improvement import ImprovementGovernor
                    governor=ImprovementGovernor(active)
                    proposal_id=governor.propose(agent.strip(),candidate,changes,benchmark.strip(),protected_fields)
                    proposal=active.store.get_proposal(proposal_id)
                    if proposal: proposal.pop("candidate_instruction",None)
                    return self.send_json(201,{"proposal":proposal})
                except Exception as exc:
                    return self.send_json(400,{"error":f"Proposal rejected ({type(exc).__name__})."})
            if is_provider_test:
                if set(body)!={"provider_route"} or not isinstance(body.get("provider_route"),str):
                    return self.send_json(400,{"error":"provider_route is required."})
                provider = None
                response_status = 200
                response_body = None
                try:
                    provider=active.provider.resolve(body["provider_route"]) if hasattr(active.provider,"resolve") else None
                    if provider is None or getattr(provider,"name","")=="deterministic-mock":
                        response_status = 400
                        response_body = {"ok":False,"error":"Mock is test-only and cannot be live-verified."}
                    else:
                        started=time.monotonic()
                        provider.generate(system_prompt="You are performing a bounded provider connectivity check.",
                                          user_prompt="Reply with exactly: uneXpected provider connection verified.",
                                          agent_id="system-health",task_id="provider-test",timeout=10.0)
                        elapsed_ms=round((time.monotonic()-started)*1000,2)
                        if hasattr(active.provider,"mark_success"): active.provider.mark_success(body["provider_route"])
                        elif hasattr(provider,"verified"): provider.verified=True
                        active.store.log_event("provider_verified",payload={"route":body["provider_route"],
                            "provider":getattr(provider,"name",type(provider).__name__),
                            "model":getattr(provider,"model",None),"latency_ms":elapsed_ms})
                        response_body = {"ok":True,"provider_route":body["provider_route"],
                            "provider":getattr(provider,"name",type(provider).__name__),
                            "model":getattr(provider,"model",None),"latency_ms":elapsed_ms,"verified":True}
                except Exception as exc:
                    diagnostic = _safe_provider_diagnostic(provider, exc)
                    active.store.log_event("provider_test_failed",payload={"route":body.get("provider_route"),
                        "error_type":type(exc).__name__,"diagnostic":diagnostic})
                    response_status = 502
                    response_body = {"ok":False,"error":diagnostic}

                # Provider success is established above and audited independently
                # of the client connection. A dropped response must not relabel
                # a completed provider call as a provider failure.
                try:
                    return self.send_json(response_status,response_body)
                except OSError:
                    return
            allowed=({"agent_id","objective","inputs","deadline_seconds","max_corrections","max_improvements","provider_route","workflow_id"}
                     if is_lifecycle else
                     {"agent_id","objective","inputs","deadline_seconds","max_steps","idempotency_key","source_refs","provider_route","skill_ids"})
            if set(body)-allowed: return self.send_json(400,{"error":"Unsupported fields; privileged actions are not exposed."})
            provider_route=body.get("provider_route")
            if provider_route is not None and not isinstance(provider_route,str): return self.send_json(400,{"error":"provider_route must be a string."})
            if provider_route is not None:
                try: active.provider.resolve(provider_route)
                except Exception: return self.send_json(400,{"error":"Requested provider route is unavailable."})
            agent=body.get("agent_id"); objective=body.get("objective"); inputs=body.get("inputs",{})
            deadline=body.get("deadline_seconds",60.0 if is_lifecycle else 195.0)
            steps=body.get("max_steps",6)
            idem=body.get("idempotency_key"); refs=body.get("source_refs",[])
            skill_ids=body.get("skill_ids",[])
            corrections=body.get("max_corrections",1)
            improvements=body.get("max_improvements",3)
            workflow_id=body.get("workflow_id")
            if not isinstance(agent,str) or not agent.strip() or not isinstance(objective,str) or not objective.strip():
                return self.send_json(400,{"error":"agent_id and objective are required."})
            if len(objective)>MAX_OBJECTIVE_CHARS: return self.send_json(413,{"error":"Objective too large."})
            if (not isinstance(inputs,dict) or isinstance(deadline,bool) or not isinstance(deadline,(int,float))
                    or (not is_lifecycle and (isinstance(steps,bool) or not isinstance(steps,int)))
                    or (is_lifecycle and (isinstance(corrections,bool) or not isinstance(corrections,int)
                                       or isinstance(improvements,bool) or not isinstance(improvements,int)))):
                return self.send_json(400,{"error":"Invalid inputs, deadline or workflow limits."})
            if not math.isfinite(float(deadline)) or not 0 < float(deadline) <= 600:
                return self.send_json(400,{"error":"deadline_seconds must be finite and between 0 and 600."})
            if is_lifecycle and float(deadline) > 120:
                return self.send_json(400,{"error":"Lifecycle per-stage deadline must not exceed 120 seconds."})
            if is_lifecycle:
                if workflow_id is not None and (
                    not isinstance(workflow_id, str) or not workflow_id.strip()
                    or len(workflow_id) > 128 or any(ord(char) < 32 for char in workflow_id)
                ):
                    return self.send_json(400,{"error":"workflow_id must be a non-empty string of at most 128 safe characters."})
                if not 0 <= corrections <= 2:
                    return self.send_json(400,{"error":"max_corrections must be between 0 and 2 for the HTTP workflow endpoint."})
                if not 1 <= improvements <= 5:
                    return self.send_json(400,{"error":"max_improvements must be between 1 and 5 for the HTTP workflow endpoint."})
            else:
                if not 1 <= steps <= 12:
                    return self.send_json(400,{"error":"max_steps must be between 1 and 12."})
                if idem is not None and (not isinstance(idem,str) or len(idem)>128): return self.send_json(400,{"error":"Invalid idempotency key."})
                if not isinstance(refs,list) or len(refs)>32 or any(not isinstance(x,str) or not x or len(x)>MAX_SOURCE_REF_CHARS for x in refs): return self.send_json(400,{"error":"Invalid source_refs."})
                if (not isinstance(skill_ids,list) or len(skill_ids)>4
                        or any(not isinstance(x,str) or not x.strip() or len(x)>128 for x in skill_ids)
                        or len(set(skill_ids))!=len(skill_ids)):
                    return self.send_json(400,{"error":"skill_ids must be a list of at most 4 unique non-empty skill IDs."})
            try:
                if is_lifecycle:
                    provider_router = getattr(active, "provider", None)
                    selected_provider = (
                        provider_router.resolve(provider_route)
                        if hasattr(provider_router, "resolve") else provider_router
                    )
                    if getattr(selected_provider, "name", "") == "deterministic-mock":
                        return self.send_json(409, {
                            "error": (
                                "Full verified lifecycle requires a configured live AI provider; "
                                "deterministic mock only verifies runtime plumbing. Use Single governed "
                                "invocation for a runtime test or configure and verify a live provider."
                            )
                        })
                    if not bool(getattr(selected_provider, "verified", False)):
                        return self.send_json(409, {
                            "error": (
                                "Full verified lifecycle requires the selected live AI provider to pass "
                                "the Test connection check before lifecycle execution."
                            )
                        })
                    if active.max_workers < 2 or not lifecycle_slots.acquire(blocking=False):
                        return self.send_json(503,{"error":"Lifecycle capacity exhausted."})
                    try:
                        result=active.run_lifecycle(agent.strip(),objective,inputs,
                                                    deadline_seconds=float(deadline),
                                                    max_corrections=corrections,
                                                    max_improvements=improvements,
                                                    provider_route=provider_route,
                                                    workflow_id=workflow_id).to_dict()
                    finally:
                        lifecycle_slots.release()
                    success=result.get("status")=="delivered" and result.get("delivered") is True
                else:
                    result=active.invoke(agent.strip(),objective,inputs,deadline_seconds=float(deadline),
                                         max_steps=steps,idempotency_key=idem,source_refs=tuple(refs),
                                         provider_route=provider_route,
                                         requested_skill_ids=tuple(skill_ids)).to_dict()
                    success=result.get("status")=="completed"
                return self.send_json(200 if success else 502,{"result":result})
            except Exception as exc: return self.send_json(400,{"error":f"Task rejected or failed ({type(exc).__name__})."})
    server=ThreadingHTTPServer((host,int(port)),Handler)
    server.daemon_threads=True; server.allow_reuse_address=True; server.coordinator=active; server.owns_coordinator=coordinator is None
    return server

def main():
    server=create_server(host=os.getenv("UNEXPECTED_RUNTIME_BIND_HOST","0.0.0.0"),port=int(os.getenv("PORT",os.getenv("UNEXPECTED_RUNTIME_PORT","10000"))))
    try: server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt: return 0
    finally:
        server.shutdown(); server.server_close()
        if server.owns_coordinator: server.coordinator.close()
    return 0

if __name__=="__main__": raise SystemExit(main())
