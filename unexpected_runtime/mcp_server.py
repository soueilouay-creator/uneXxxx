from __future__ import annotations
import json
from typing import Any
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from . import __version__
from .permissions import PRIVILEGED
MAX_LIMIT=50
MAX_DEADLINE=120.0
def _obj(value:Any)->dict[str,Any]:
    if isinstance(value,dict): return value
    try:
        parsed=json.loads(value) if isinstance(value,str) else {}
        return parsed if isinstance(parsed,dict) else {}
    except (TypeError,ValueError): return {}
def _task(row:dict[str,Any],with_result:bool=False)->dict[str,Any]:
    item=dict(row); payload=_obj(item.pop("payload_json",None)); raw=item.pop("result_json",None)
    item["objective"]=payload.get("objective",""); item["provider_route"]=payload.get("provider_route")
    if with_result:
        item["inputs"]=payload.get("inputs",{})
        try: item["result"]=json.loads(raw) if raw else None
        except (TypeError,ValueError): item["result"]=None
    return item
def _live_route(active,route:str|None)->str:
    router=active.provider
    if hasattr(router,"resolve"):
        selected=route or getattr(router,"default_route",None); provider=router.resolve(selected)
    else: selected,provider=route,router
    name=getattr(provider,"name",type(provider).__name__ if provider else "unavailable")
    if provider is None or name=="deterministic-mock" or not getattr(provider,"configured",True) or not getattr(provider,"verified",False):
        raise ToolError("MCP execution requires a configured, verified live provider route; mock and unverified routes are blocked.")
    return selected
def build_mcp_server(active):
    server=MCPServer(name="uneXpected v8",title="uneXpected Command Center",
      description="Governed access to the hosted uneXpected v8 runtime.",
      instructions="Use live runtime and persisted records. Execution tools create internal tasks only. External contact, publishing, booking, quotes, payments and external writes are not exposed.",
      version=__version__,subscriptions=False)
    @server.tool(description="Return safe runtime health, role count, storage and provider metadata. Never returns credentials.",structured_output=True)
    def runtime_status()->dict[str,Any]:
        store,provider=active.store,active.provider
        try: healthy=bool(store.check_health()) if callable(getattr(store,"check_health",None)) else True
        except Exception: healthy=False
        status=active.status()
        return {"version":__version__,"registered_agents":len(active.registry),"health":"ready" if healthy else "degraded",
          "storage_backend":"postgres" if type(store).__name__.lower().startswith("postgres") else "sqlite-local",
          "storage_healthy":healthy,"provider":getattr(provider,"name",type(provider).__name__),
          "default_provider":getattr(provider,"default_route",None),"provider_configured":bool(getattr(provider,"configured",True)),
          "approval_authority":status.get("approval_verifier","not configured"),"privileged_actions":"disabled","external_connectors":"not configured"}
    @server.tool(description="List the canonical specialist-role registry.",structured_output=True)
    def list_agents()->dict[str,Any]:
        items=active.list_agents(); return {"count":len(items),"items":items}
    @server.tool(description="List recent persisted task metadata without raw inputs or results.",structured_output=True)
    def list_tasks(limit:int=25)->dict[str,Any]:
        if isinstance(limit,bool) or not isinstance(limit,int): raise ToolError("limit must be an integer.")
        rows=active.store.list_tasks(max(1,min(limit,MAX_LIMIT)))
        return {"count":len(rows),"items":[_task(row) for row in rows]}
    @server.tool(description="Read one persisted task by exact task ID, including result.",structured_output=True)
    def get_task(task_id:str)->dict[str,Any]:
        if not isinstance(task_id,str) or not task_id.strip() or len(task_id)>128: raise ToolError("A valid task_id is required.")
        row=active.store.get_task(task_id)
        if not row: raise ToolError("Unknown task_id.")
        return {"task":_task(row,True)}
    @server.tool(description="Read bounded persisted event history for one task.",structured_output=True)
    def get_task_events(task_id:str,after_event_id:int=0,limit:int=50)->dict[str,Any]:
        if not isinstance(task_id,str) or not task_id.strip() or len(task_id)>128: raise ToolError("A valid task_id is required.")
        if isinstance(after_event_id,bool) or not isinstance(after_event_id,int) or after_event_id<0 or isinstance(limit,bool) or not isinstance(limit,int):
            raise ToolError("Invalid event cursor or limit.")
        if not active.store.get_task(task_id): raise ToolError("Unknown task_id.")
        bounded=max(1,min(limit,MAX_LIMIT)); rows=active.store.list_task_events(task_id,after_event_id=after_event_id,limit=bounded+1)
        items=[]
        for row in rows[:bounded]:
            item=dict(row); item["payload"]=_obj(item.pop("payload_json",None)); items.append(item)
        return {"task_id":task_id,"count":len(items),"items":items,"next_cursor":items[-1]["event_id"] if items else after_event_id,"has_more":len(rows)>bounded}
    @server.tool(description="Run a bounded internal agent task. Requires verified live provider; no external write tools.",structured_output=True)
    def run_task(agent_id:str,objective:str,inputs:dict[str,Any]|None=None,provider_route:str|None=None,deadline_seconds:float=60.0,max_steps:int=6)->dict[str,Any]:
        if not isinstance(agent_id,str) or not agent_id.strip(): raise ToolError("agent_id is required.")
        if not isinstance(objective,str) or not objective.strip() or len(objective)>16000: raise ToolError("Invalid objective.")
        if inputs is not None and not isinstance(inputs,dict): raise ToolError("inputs must be a JSON object.")
        if isinstance(deadline_seconds,bool) or not isinstance(deadline_seconds,(int,float)) or not 0<float(deadline_seconds)<=MAX_DEADLINE or isinstance(max_steps,bool) or not isinstance(max_steps,int) or not 1<=max_steps<=12:
            raise ToolError("Task deadline or step limit is outside permitted bounds.")
        try: spec=active.registry.get(agent_id)
        except Exception: raise ToolError("Unknown agent_id.") from None
        if set(spec.allowed_permissions)&PRIVILEGED: raise ToolError("This role has privileged scopes and cannot be invoked through remote MCP.")
        selected=_live_route(active,provider_route)
        result=active.invoke(agent_id,objective,inputs=inputs or {},deadline_seconds=float(deadline_seconds),max_steps=max_steps,provider_route=selected)
        return {"result":result.to_dict()}
    @server.tool(description="Run an internal draft-only industrial-maintenance sales workflow. Never contact prospects or perform external actions.",structured_output=True)
    def run_sales_workflow(objective:str,inputs:dict[str,Any]|None=None,provider_route:str|None=None,deadline_seconds:float=90.0,max_corrections:int=0,max_improvements:int=1)->dict[str,Any]:
        if not isinstance(objective,str) or not objective.strip() or len(objective)>12000: raise ToolError("Invalid objective.")
        if inputs is not None and not isinstance(inputs,dict): raise ToolError("inputs must be a JSON object.")
        if isinstance(deadline_seconds,bool) or not isinstance(deadline_seconds,(int,float)) or not 0<float(deadline_seconds)<=MAX_DEADLINE or isinstance(max_corrections,bool) or not isinstance(max_corrections,int) or not 0<=max_corrections<=1 or isinstance(max_improvements,bool) or not isinstance(max_improvements,int) or not 1<=max_improvements<=2:
            raise ToolError("Sales workflow limits are outside permitted bounds.")
        spec=active.registry.get("sales-intel")
        if set(spec.allowed_permissions)&PRIVILEGED: raise ToolError("Sales role has privileged scopes and cannot be invoked remotely.")
        selected=_live_route(active,provider_route); safe_inputs=dict(inputs or {})
        safe_inputs["remote_mcp_execution_policy"]={"mode":"internal-draft-only","external_actions":"disabled",
          "never":["email/call/DM/form submission","publishing","meeting booking","quotes/payments","external-system writes"],
          "facts":"Use supplied facts only and label unknowns as discovery questions."}
        result=active.run_lifecycle("sales-intel",objective,safe_inputs,max_corrections=max_corrections,max_improvements=max_improvements,deadline_seconds=float(deadline_seconds),provider_route=selected)
        return {"result":result.to_dict()}
    app=server.streamable_http_app(streamable_http_path="/mcp",json_response=True,stateless_http=True,max_request_body_size=64*1024,
      transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*","localhost:*","unexpected-v8-command-center.onrender.com","unexpected-v8-command-center.onrender.com:*"],allowed_origins=[]),
      host="127.0.0.1")
    return server,app
