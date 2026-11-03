(() => {
  "use strict";
  const state = { token: "", agents: [], providers: [], tasks: [], skills: [], mcpTools: [], capabilities: [], workflowCatalog: null, inventoryErrors: {}, inventoryRequestId: 0, status: null, traceTaskId: null, traceCursor: 0 };
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const time = (v) => { if (!v) return "—"; const n=Number(v); const d=new Date(n>1e12?n:n*1000); return Number.isNaN(d.getTime())?String(v):d.toLocaleString(); };
  function toast(message) { const el=$("toast"); el.textContent=message; el.classList.add("show"); window.setTimeout(()=>el.classList.remove("show"),2500); }
  async function api(path, options={}) {
    const headers = new Headers(options.headers || {});
    headers.set("Authorization","Bearer "+state.token);
    if (options.body) headers.set("Content-Type","application/json");
    const response=await fetch(path,{...options,headers,cache:"no-store"});
    const type=response.headers.get("content-type")||"";
    const body=type.includes("application/json")?await response.json():await response.text();
    if (!response.ok) {
      const taskStatus = body?.result?.status;
      const taskError = body?.result?.error;
      const message = body?.error ||
        (body?.report?.failure_reason ? "Quality evaluation blocked: "+body.report.failure_reason :
        (taskStatus ? "Task "+taskStatus+(taskError ? ": "+taskError : " did not complete.") :
        ("Request failed ("+response.status+")")));
      const error = new Error(message); error.body = body; throw error;
    }
    return body;
  }
  function setConnected(ok) {
    $("connection").textContent=ok?"● Connected":"● API unavailable";
    $("connection").style.color=ok?"#59d9c1":"#ff7d8b";
    $("side-dot").className="dot "+(ok?"ok":"bad");
    $("side-health").textContent=ok?"Runtime connected":"Runtime unavailable";
  }
  function row(title, detail, meta) {
    return '<div class="list-row"><div><div class="list-title">'+esc(title)+'</div><div class="list-detail">'+esc(detail||"")+'</div></div><div class="list-meta">'+esc(meta||"")+'</div></div>';
  }
  function readiness(name,value,ok) {
    return '<div class="list-row"><div class="list-title">'+esc(name)+'</div><div class="list-meta"><span class="state '+(ok?"ok":"")+'">'+esc(value)+'</span></div></div>';
  }
  async function loadTaskTrace(taskId, after=0, append=false) {
    const panel=$("task-trace-panel");
    const button=$("trace-load-more");
    panel.hidden=false;
    $("trace-title").textContent="Task trace · "+taskId;
    if(!append)$("trace-events").textContent="Loading persisted task events…";
    try {
      const response=await api("/v1/tasks/"+encodeURIComponent(taskId)+"/events?after="+encodeURIComponent(after)+"&limit=50");
      const items=response.items||[];
      const html=items.map(item=>row("Event #"+item.event_id,item.event_type+" · "+(item.agent_id||"runtime"),time(item.ts))).join("");
      if(append)$("trace-events").insertAdjacentHTML("beforeend",html);
      else $("trace-events").innerHTML=html||'<div class="empty">No events recorded for this task yet.</div>';
      state.traceTaskId=taskId;
      state.traceCursor=response.next_cursor??after;
      button.hidden=!response.has_more;
      button.disabled=false;
    } catch(error) {
      if(!append)$("trace-events").textContent="Trace could not be loaded: "+error.message;
      button.hidden=true;
      toast(error.message);
    }
  }
  function renderTaskList(items) {
    if(!items.length){$("task-list").innerHTML='<div class="empty">No tasks recorded yet.</div>';return;}
    $("task-list").innerHTML=items.map(t=>'<div class="list-row"><div><div class="list-title">'+esc(t.objective||t.task_id)+'</div><div class="list-detail">'+esc(t.agent_id+" · "+t.status+(t.parent_task_id?" · child of "+t.parent_task_id:""))+'</div></div><div class="list-meta"><div>'+esc(time(t.created_at))+'</div><button class="button secondary trace-task" data-trace-task="'+esc(t.task_id)+'" type="button">View trace</button></div></div>').join("");
  }
  function renderAgents() {
    $("agent-grid").innerHTML=state.agents.length?state.agents.map(a=>'<article><div class="agent-id">'+esc(a.id)+'</div><h4>'+esc(a.name)+'</h4><p>'+esc(a.objective||a.capability_label||"Governed specialist role")+'</p><div class="tags"><span class="tag">'+esc(a.version||"version —")+'</span><span class="tag">'+esc(a.status||"registered")+'</span></div></article>').join(""):'<div class="empty">Agent registry unavailable.</div>';
    $("task-agent").innerHTML=state.agents.map(a=>'<option value="'+esc(a.id)+'">'+esc(a.name)+" · "+esc(a.id)+'</option>').join("");
    $("proposal-agent").innerHTML=state.agents.map(a=>'<option value="'+esc(a.id)+'">'+esc(a.name)+" · "+esc(a.id)+'</option>').join("");
  }
  function renderProviders(items) {
    state.providers=items;
    const selector=$("task-provider");
    const previous=selector.value;
    selector.innerHTML='<option value="">Default configured route</option>'+items.map(p=>'<option value="'+esc(p.id)+'" '+(!p.configured?'disabled':'')+'>'+esc(p.id)+(p.default?' · default':'')+'</option>').join("");
    if(items.some(p=>p.id===previous&&p.configured))selector.value=previous;
    const qualitySelector=$("quality-provider");
    if(qualitySelector){
      const previousQuality=qualitySelector.value;
      const verified=items.filter(p=>p.live&&p.configured&&p.verified);
      qualitySelector.innerHTML='<option value="">Select a verified live route</option>'+verified.map(p=>'<option value="'+esc(p.id)+'">'+esc(p.id)+(p.model?' · '+esc(p.model):'')+'</option>').join("");
      if(verified.some(p=>p.id===previousQuality))qualitySelector.value=previousQuality;
      $("quality-evaluation-submit").disabled=verified.length===0;
    }
    $("provider-grid").innerHTML=items.length?items.map(p=>'<article><h4>'+esc(p.name)+'</h4><p>'+esc(p.model||"Model not disclosed")+'</p>'+readiness("Configuration",p.live?(p.configured?"Configured":"Not configured"):"Built-in test mode",!p.live||p.configured)+readiness("Live verification",p.live?(p.verified?"Verified":"Not verified"):"Not applicable",!p.live||p.verified)+(p.live&&p.configured?'<button class="button secondary provider-test" data-test-provider="'+esc(p.id)+'" type="button">Test connection</button>':'<small>Mock mode · not a live provider</small>')+'</article>').join(""):'<div class="empty">No provider adapters are available.</div>';
    syncLifecycleMode();
  }
  function syncLifecycleMode() {
    const providers=state.providers||[];
    const defaultProvider=providers.find(p=>p.default);
    const selectedId=$("task-provider").value||defaultProvider?.id;
    const selectedProvider=providers.find(p=>p.id===selectedId);
    const hasConfiguredLiveProvider=Boolean(selectedProvider?.live&&selectedProvider?.configured&&selectedProvider?.verified);
    const lifecycleOption=$("task-mode").querySelector('option[value="lifecycle"]');
    lifecycleOption.disabled=!hasConfiguredLiveProvider;
    lifecycleOption.textContent=hasConfiguredLiveProvider
      ? "Full verified lifecycle"
      : "Full verified lifecycle (requires a live AI provider)";
    if(!hasConfiguredLiveProvider&&$("task-mode").value==="lifecycle")$("task-mode").value="invoke";
  }

  function renderLiveWorkflowRuns() {
    const runs=state.tasks||[];
    $("workflow-run-count").textContent=String(runs.length);
    $("workflow-run-list").innerHTML=runs.length?runs.map(task=>{
      const trace='<button class="button secondary trace-task" data-workflow-trace="'+esc(task.task_id)+'" type="button">View trace</button>';
      const status='<span class="state '+(task.status==="completed"?"ok":"")+'">'+esc(task.status||"unknown")+'</span>';
      const detail=esc(task.agent_id||"unassigned")+(task.parent_task_id?" · child of "+esc(task.parent_task_id):"")+" · "+esc(time(task.created_at));
      return '<div class="list-row"><div><div class="list-title">'+esc(task.objective||task.task_id)+'</div><div class="list-detail">'+detail+'</div></div><div class="list-meta">'+status+trace+'</div></div>';
    }).join(""):'<div class="empty">No workflow runs recorded yet. Submit a task from the command center to see its runtime trace here.</div>';
  }
  function renderWorkflowFilters(){
    const rows=(state.workflowCatalog||{}).workflows||[],categories=[...new Set(rows.map(x=>x.category).filter(Boolean))].sort(),roles=[...new Set(rows.flatMap(x=>[x.primary_agent_id,...(x.supporting_agent_ids||[])].filter(Boolean)))].sort();
    const c=$("workflow-category"),r=$("workflow-role"),oldC=c.value,oldR=r.value;
    c.innerHTML='<option value="">All categories ('+categories.length+')</option>'+categories.map(x=>'<option value="'+esc(x)+'">'+esc(x)+'</option>').join("");
    r.innerHTML='<option value="">All mapped roles ('+roles.length+')</option>'+roles.map(x=>'<option value="'+esc(x)+'">'+esc(x)+'</option>').join("");
    if(categories.includes(oldC))c.value=oldC;if(roles.includes(oldR))r.value=oldR;
  }
  function renderWorkflowCatalogue(){
    const catalog=state.workflowCatalog||{},rows=catalog.workflows||[],q=$("workflow-search").value.trim().toLowerCase(),cat=$("workflow-category").value,role=$("workflow-role").value;
    if(state.inventoryErrors.workflowCatalog){
      $("workflow-total").textContent="—";$("workflow-nav-count").textContent="!";$("workflow-filter-count").textContent="Catalogue unavailable";
      $("workflow-catalog-status").textContent="Catalogue unavailable";
      $("workflow-grid").innerHTML='<div class="empty">Workflow catalogue unavailable: '+esc(state.inventoryErrors.workflowCatalog)+'</div>';
      return;
    }
    const selected=rows.filter(x=>{const text=[x.title,x.description,x.category,x.source_path,x.primary_agent_id,...(x.supporting_agent_ids||[])].join(" ").toLowerCase(),mapped=[x.primary_agent_id,...(x.supporting_agent_ids||[])];return(!q||text.includes(q))&&(!cat||x.category===cat)&&(!role||mapped.includes(role));});
    $("workflow-total").textContent=rows.length;$("workflow-nav-count").textContent=rows.length;$("workflow-filter-count").textContent=selected.length+" of "+rows.length+" mapped candidates";
    $("workflow-catalog-status").textContent=catalog.status==="mapped_candidates_not_runnable"?"Crosswalk loaded · mapped only":"Catalogue status unknown";
    $("workflow-grid").innerHTML=selected.length?selected.map(x=>{
      const list=a=>(a||[]).map(v=>"<li>"+esc(v)+"</li>").join(""),source=String(x.source_url||""),link=source.startsWith("https://")?'<a href="'+esc(source)+'" target="_blank" rel="noopener noreferrer">Open source reference ↗</a>':"Source reference unavailable";
      return '<article class="workflow-card"><div class="workflow-card-top"><span class="category-tag">'+esc(x.category||"Uncategorised")+'</span><span class="state warning">Mapped · not runnable</span></div><h4>'+esc(x.title)+'</h4><p>'+esc(x.description||"No description supplied.")+'</p><div class="workflow-role-map"><div><small>PRIMARY ROLE</small><b>'+esc(x.primary_agent_id||"unmapped")+'</b></div><div><small>SUPPORTING ROLES</small><b>'+((x.supporting_agent_ids||[]).map(esc).join(", ")||"None")+'</b></div></div><details><summary>Inputs, procedure, deliverable & acceptance</summary><div class="workflow-detail"><b>Required inputs</b><ul>'+list(x.required_inputs)+'</ul><b>Procedure</b><ol>'+list(x.procedure_steps)+'</ol><b>Expected deliverable</b><p>'+esc(x.expected_deliverable||"Not specified")+'</p><b>Acceptance checks</b><ul>'+list(x.acceptance_checks)+'</ul><b>Safety boundary</b><p>'+esc(x.safety_boundary||"No additional safety metadata supplied")+'</p><b>External dependencies</b><p>'+esc(x.external_dependencies||"Not specified")+'</p><div>'+link+'</div><small>Source path: '+esc(x.source_path||"—")+' · Card: '+esc(x.card_path||"—")+'</small></div></details></article>';
    }).join(""):'<div class="empty">No workflow candidates match these filters.</div>';
  }
  function renderSkillsAndTools(){
    const list=state.skills||[],tools=state.mcpTools||[],caps=state.capabilities||[];
    $("skill-total").textContent=state.inventoryErrors.skills?"—":list.length;
    $("skill-nav-count").textContent=state.inventoryErrors.skills?"!":list.length;
    $("mcp-tool-total").textContent=state.inventoryErrors.mcpTools?"—":tools.length;
    $("skill-grid").innerHTML=state.inventoryErrors.skills?'<div class="empty">Skills unavailable: '+esc(state.inventoryErrors.skills)+'</div>':list.length?list.map(s=>{
      const roles=(s.agent_ids||[]).map(esc).join(", "),triggers=(s.trigger_terms||[]).map(esc).join(", ")||"Runtime policy",allowed=(s.allowed_tools||[]).map(esc).join(", ")||"No direct tool grants",resources=(s.resources||[]).map(x=>esc(x.kind)+": "+esc(x.path)).join(" · ")||"No additional resources";
      return '<article class="skill-card"><div class="workflow-card-top"><span class="category-tag">Skill v'+esc(s.version)+'</span><span class="state '+(s.status==="active"?"ok":"")+'">'+esc(s.status)+'</span></div><h4>'+esc(s.id)+'</h4><p>'+esc(s.description||"Hash-pinned reusable specialist procedure.")+'</p><div class="skill-meta"><div><small>INVOCATION MODE</small><b>'+esc(s.invocation_mode)+'</b></div><div><small>ALLOWED TOOLS</small><b>'+allowed+'</b></div></div><b>Mapped roles</b><p>'+roles+'</p><b>Activation triggers</b><p>'+triggers+'</p><b>Bundle files</b><p>'+resources+'</p><small class="hash-line">SHA-256 '+esc(s.sha256)+'<br>Source: '+esc(s.source_ref)+'</small></article>';
    }).join(""):'<div class="empty">No active Skills are available from the verified manifest.</div>';
    const manual=list.filter(x=>x.invocation_mode==="user_invocable").length;
    $("skill-policy-note").innerHTML='<b>Skill activation policy</b><p>'+manual+' of '+list.length+' active Skills are explicitly user-invocable. Automatic Skills are selected by the runtime using the objective triggers and role scope. Skills do not independently grant permissions. The loader verifies SHA-256 content and does not execute packaged scripts.</p>';
    $("mcp-tool-grid").innerHTML=state.inventoryErrors.mcpTools?'<div class="empty">MCP tool inventory unavailable: '+esc(state.inventoryErrors.mcpTools)+'</div>':tools.length?tools.map(t=>'<article class="tool-card"><div class="workflow-card-top"><span class="category-tag">MCP adapter</span><span class="state '+(t.enabled?"ok":"")+'">'+esc(t.capability_status)+'</span></div><h4>'+esc(t.name)+'</h4><p>'+esc(t.description)+'</p><div class="skill-meta"><div><small>TOOL ID</small><b>'+esc(t.tool_id)+'</b></div><div><small>CAPABILITY</small><b>'+esc(t.capability_id)+'</b></div></div><b>Allowed roles</b><p>'+((t.allowed_agent_ids||[]).map(esc).join(", ")||"None")+'</p><b>Required permissions</b><p>'+((t.required_permissions||[]).map(esc).join(", ")||"None")+'</p><small>Source: '+esc(t.source_url)+' · '+esc(t.source_publisher)+' · v'+esc(t.version)+'</small></article>').join(""):'<article class="panel empty"><b>No MCP adapters registered</b><p>The MCP gateway boundary is implemented, but no external MCP server or tool adapter is installed, enabled or authorised. The current count is zero, not simulated.</p></article>';
    $("skills-capability-list").innerHTML=caps.length?caps.map(x=>row(x.name||x.capability_id,x.description||x.source_url||"",x.status||"unknown")).join(""):'<div class="empty">No capabilities are registered. Additions require provenance, licence, role scope and permission review.</div>';
  }
  async function loadOptionalInventories() {
    const requestId=++state.inventoryRequestId;
    const results=await Promise.allSettled([
      api("/v1/skills"),api("/v1/mcp/tools"),api("/assets/workflow-catalog.json")
    ]);
    if(requestId!==state.inventoryRequestId)return;
    const [skills,mcpTools,workflowCatalog]=results;
    state.inventoryErrors={};
    const value=(result,key,fallback)=>{
      if(result.status==="fulfilled")return result.value;
      state.inventoryErrors[key]=result.reason?.message||"Request failed";
      return fallback;
    };
    const skillBody=value(skills,"skills",{items:[]});
    const toolBody=value(mcpTools,"mcpTools",{items:[]});
    state.skills=Array.isArray(skillBody.items)?skillBody.items:[];
    state.mcpTools=Array.isArray(toolBody.items)?toolBody.items:[];
    state.workflowCatalog=value(workflowCatalog,"workflowCatalog",{status:"unavailable",count:0,workflows:[]});
    renderWorkflowFilters();
    renderWorkflowCatalogue();
    renderSkillsAndTools();
  }
  async function refresh() {
    $("refresh").disabled=true;
    try {
      const [status,agents,tasks,events,providers,caps,improvements,approvals,resources,qualityRuns]=await Promise.all([
        api("/v1/status"),api("/v1/agents"),api("/v1/tasks?limit=8"),api("/v1/events?limit=8"),
        api("/v1/providers"),api("/v1/capabilities"),api("/v1/improvements"),api("/v1/approvals"),
        api("/v1/resources?limit=100"),api("/v1/quality-evaluations?limit=20")
      ]);
      state.status=status; state.agents=agents.items||[]; state.tasks=tasks.items||[]; state.capabilities=caps.items||[];
      $("metric-health").textContent=status.health?.status||"Ready";
      $("health-note").textContent=status.health?.detail||"Runtime status received";
      $("metric-agents").textContent=agents.count??state.agents.length;
      $("nav-count").textContent=agents.count??state.agents.length;
      $("version").textContent=status.version||"—";
      const provider=(providers.providers||[])[0]||{};
      $("metric-provider").textContent=provider.name||status.provider||"Unavailable";
      $("provider-note").textContent=provider.verified?"Live request verified":provider.configured?"Configured · not verified":"Not configured";
      $("readiness").innerHTML=[
        readiness("HTTP application",status.health?.status||"healthy",status.health?.ok!==false),
        readiness("Agent registry",String(agents.count??0)+" roles",agents.count===38),
        readiness("State store",status.storage?.status||"local adapter",status.storage?.healthy===true),
        readiness("Provider route",provider.verified?"verified":provider.configured?"configured only":"unavailable",provider.verified===true),
        readiness("Privileged actions",status.governance?.privileged_actions||"disabled",false)
      ].join("");
      $("recent-events").innerHTML=(events.items||[]).length?events.items.map(e=>row(e.event_type,e.agent_id||e.task_id||"",time(e.ts))).join(""):'<div class="empty">No events recorded yet.</div>';
      $("audit-events").innerHTML=$("recent-events").innerHTML;
      renderTaskList(state.tasks); renderLiveWorkflowRuns();
      $("capability-list").innerHTML=(caps.items||[]).length?caps.items.map(c=>row(c.name||c.capability_id,c.source||c.description||"",c.status||"registered")).join(""):'<div class="empty">No capabilities registered. Catalog entries do not imply live integrations.</div>';
      $("improvement-list").innerHTML=(improvements.items||[]).length?improvements.items.map(p=>row(p.proposal_id,p.agent_id+" · "+p.changes,p.status)).join(""):'<div class="empty">No improvement proposals recorded.</div>';
      $("approval-list").innerHTML=(approvals.items||[]).length?approvals.items.map(a=>row(a.approval_id,a.permission,a.status)).join(""):'<div class="empty">'+esc(approvals.message||"No pending approval records are exposed. Privileged execution remains disabled.")+'</div>';
      $("resource-list").innerHTML=(resources.items||[]).length?(resources.items||[]).map(item=>row(item.name,item.expected_benefit+" · source: "+item.source_list_url,item.adoption_status)).join(""):'<div class="empty">No resource references are indexed yet.</div>';
      $("quality-evaluation-list").innerHTML=(qualityRuns.items||[]).length?(qualityRuns.items||[]).map(item=>{
        const failures=(item.failure_classes||[]).join(", ")||item.failure_reason||"No failure class";
        return row(item.evaluation_id,item.provider_route+" · "+item.execution_mode+" · "+failures,(item.status||"unknown")+" · "+Math.round((item.score||0)*100)+"%");
      }).join(""):'<div class="empty">No AI quality evaluations recorded yet.</div>';
      $("approval-state").textContent=status.governance?.approval_authority||"Not verified";
      $("replay-state").textContent=status.governance?.replay_protection||"Not verified";
      $("recovery-state").textContent=status.storage?.recovery||"Not verified";
      $("updated").textContent="Updated "+new Date().toLocaleTimeString();
      renderAgents(); renderProviders(providers.providers||[]); setConnected(true); void loadOptionalInventories();
    } catch(error) {
      setConnected(false);
      if (error.message==="Unauthorized."||error.message==="Unauthorized") {
        $("auth-overlay").classList.remove("hidden");
        $("auth-error").textContent="The access token was rejected.";
      } else toast(error.message);
    } finally { $("refresh").disabled=false; }
  }
  function showView(name) {
    document.querySelectorAll(".view").forEach(v=>v.classList.toggle("active",v.id==="view-"+name));
    document.querySelectorAll(".nav").forEach(v=>v.classList.toggle("active",v.dataset.view===name));
    const titles={overview:"System overview",agents:"Agent registry",tasks:"Tasks & workflows",providers:"AI providers",capabilities:"Capabilities",intelligence:"Resource & AI quality",governance:"Governance",audit:"Audit & learning",workflows:"Workflow Studio",skills:"Skills & tools"};
    $("page-title").textContent=titles[name]||"System overview";
    if (name==="tasks"||name==="audit"||name==="governance"||name==="intelligence"||name==="workflows"||name==="skills") refresh();
  }
  document.querySelectorAll("[data-view]").forEach(link=>link.addEventListener("click",e=>{e.preventDefault();const name=link.dataset.view;showView(name);history.replaceState(null,"","#"+name);}));
  $("refresh").addEventListener("click",refresh);
  $("task-list").addEventListener("click",e=>{
    const button=e.target.closest("[data-trace-task]");
    if(!button)return;
    loadTaskTrace(button.dataset.traceTask,0,false);
  });
  $("trace-load-more").addEventListener("click",async()=>{
    if(!state.traceTaskId)return;
    $("trace-load-more").disabled=true;
    await loadTaskTrace(state.traceTaskId,state.traceCursor,true);
  });
  $("provider-grid").addEventListener("click",async e=>{
    const button=e.target.closest("[data-test-provider]");
    if(!button)return;
    button.disabled=true;button.textContent="Testing…";
    try {
      const result=await api("/v1/providers/test",{method:"POST",body:JSON.stringify({provider_route:button.dataset.testProvider})});
      toast(result.provider+" verified in "+result.latency_ms+" ms");
      await refresh();
    } catch(error) { toast(error.message); }
    finally { button.disabled=false;button.textContent="Test connection"; }
  });
  $("quality-evaluation-form").addEventListener("submit",async e=>{
    e.preventDefault();
    const button=$("quality-evaluation-submit");
    const route=$("quality-provider").value;
    const output=$("quality-evaluation-result");
    if(!route){output.textContent="Choose a verified live provider route first.";return;}
    button.disabled=true;output.textContent="Running the bounded read-only AI quality suite…";
    const renderReport=report=>{
      const failures=(report.failure_classes||[]).join(", ")||report.failure_reason||"No failed checks";
      output.textContent="Evaluation "+report.status+" · "+report.passed_cases+"/"+report.scenario_count+" cases passed · score "+Math.round((report.score||0)*100)+"% · "+report.execution_mode+". "+failures;
    };
    try {
      const response=await api("/v1/quality-evaluations",{method:"POST",body:JSON.stringify({provider_route:route})});
      renderReport(response.report||{status:"unknown"});
      toast("AI quality evaluation "+(response.report?.status||"finished"));
      await refresh();
    } catch(error) {
      if(error.body?.report)renderReport(error.body.report);
      else output.textContent="Evaluation could not run: "+error.message;
      toast(error.message);await refresh();
    } finally {button.disabled=false;}
  });
  $("agent-search").addEventListener("input",e=>{const q=e.target.value.toLowerCase();document.querySelectorAll("#agent-grid article").forEach(card=>card.hidden=!card.textContent.toLowerCase().includes(q));});
  $("workflow-search").addEventListener("input",renderWorkflowCatalogue);
  $("workflow-category").addEventListener("change",renderWorkflowCatalogue);
  $("workflow-role").addEventListener("change",renderWorkflowCatalogue);
  $("task-provider").addEventListener("change",syncLifecycleMode);
  $("auth-form").addEventListener("submit",async e=>{e.preventDefault();state.token=$("auth-token").value.trim();$("auth-error").textContent="";await refresh();if(state.status)$("auth-overlay").classList.add("hidden");});
  $("proposal-form").addEventListener("submit",async e=>{
    e.preventDefault();const button=$("proposal-submit");button.disabled=true;$("proposal-result").textContent="Submitting proposal for review…";
    const payload={agent_id:$("proposal-agent").value,benchmark_id:$("proposal-benchmark").value.trim(),
      candidate_instruction:$("proposal-instruction").value,changes:$("proposal-changes").value,protected_fields:[]};
    try {
      const response=await api("/v1/improvements/propose",{method:"POST",body:JSON.stringify(payload)});
      $("proposal-result").textContent="Proposal created: "+(response.proposal?.proposal_id||"recorded")+" · "+(response.proposal?.status||"pending");
      toast("Improvement proposal created");await refresh();
    } catch(error) {$("proposal-result").textContent="Proposal rejected: "+error.message;toast(error.message);}
    finally {button.disabled=false;}
  });
  $("task-form").addEventListener("submit",async e=>{
    e.preventDefault();const button=$("task-submit");button.disabled=true;$("task-result").textContent="Submitting task to the governed coordinator…";
    const payload={agent_id:$("task-agent").value,objective:$("task-objective").value.trim()};
    if($("task-provider").value)payload.provider_route=$("task-provider").value;
    try {
      const route=$("task-mode").value==="lifecycle"?"/v1/lifecycle":"/v1/invoke";
      const response=await api(route,{method:"POST",body:JSON.stringify(payload)});
      const result=response.result||{};
      $("task-result").innerHTML="<h3>"+esc(result.status||"Task returned")+"</h3><p>"+esc(result.verified_output||result.output||result.error||JSON.stringify(result))+"</p><p>Task ID: "+esc(result.task_id||"—")+"</p>";
      toast("Task response received");await refresh();
    } catch(error) {$("task-result").textContent="Task not completed: "+error.message;toast(error.message);}
    finally {button.disabled=false;}
  });
  if(location.hash){const name=location.hash.slice(1);if($("view-"+name))showView(name);}
  $("auth-overlay").classList.remove("hidden");
  window.setInterval(()=>{if(state.token)refresh();},60000);
})();