from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from .coordinator import Coordinator
from .models import RuntimeErrorBase
from .resource_intelligence import ResourceRegistry
from .quality_evaluation import QualityEvaluationRunner

def main(argv=None):
    p=argparse.ArgumentParser(prog='uneXpected-v7'); sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('status'); sub.add_parser('list')
    local_ai=sub.add_parser('local-ai'); local_ai.add_argument('action',choices=('hardware','preflight','status','start','stop')); local_ai.add_argument('--service')
    media=sub.add_parser('local-media'); media.add_argument('action',choices=('preflight',)); media.add_argument('--probe-service',action='store_true')
    run=sub.add_parser('run'); run.add_argument('agent_id'); run.add_argument('--objective',required=True); run.add_argument('--inputs',default='{}'); run.add_argument('--idempotency-key'); run.add_argument('--deadline',type=float,default=30.0)
    lifecycle=sub.add_parser('lifecycle'); lifecycle.add_argument('agent_id'); lifecycle.add_argument('--objective',required=True); lifecycle.add_argument('--inputs',default='{}'); lifecycle.add_argument('--max-corrections',type=int,default=1); lifecycle.add_argument('--max-improvements',type=int,default=3); lifecycle.add_argument('--deadline',type=float,default=60.0)
    chain=sub.add_parser('chain'); chain.add_argument('agents',nargs='+'); chain.add_argument('--objective',required=True); chain.add_argument('--inputs',default='{}'); chain.add_argument('--max-handoffs',type=int,default=4)
    graph=sub.add_parser('graph'); graph.add_argument('--graph-json',required=True); graph.add_argument('--max-nodes',type=int,default=20)
    resources=sub.add_parser('resources'); resources.add_argument('--category'); resources.add_argument('--status'); resources.add_argument('--validate',action='store_true')
    quality=sub.add_parser('quality-eval'); quality.add_argument('--provider-route'); quality.add_argument('--scenario',action='append',dest='scenario_ids')
    sub.add_parser('eval')
    args=p.parse_args(argv); exit_code=0
    if args.cmd=='local-ai':
        from .local_ai_supervisor import LocalAISupervisor
        supervisor=LocalAISupervisor(model_root=os.getenv('UNEXPECTED_MODEL_ROOT','./models'),
            registry_path=os.getenv('UNEXPECTED_MODEL_REGISTRY',str(Path(__file__).resolve().parent.parent/'local_ai'/'model_registry.json')))
        if args.action=='hardware': out=supervisor.preflight()['hardware']
        elif args.action=='preflight': out=supervisor.preflight()
        elif args.action=='status': out=supervisor.status()
        elif args.action=='start': out=supervisor.start(args.service)
        else: out=supervisor.stop(args.service)
        print(json.dumps(out,indent=2,ensure_ascii=False))
        return 0 if args.action in {'hardware','preflight','status'} else (0 if all(x.get('status') in {'running','already_running','stopped'} for x in out.get('services',[])) else 3)
    if args.cmd=='local-media':
        from .local_media import LocalMediaPipeline
        out=LocalMediaPipeline.from_environment().preflight(probe_service=args.probe_service)
        print(json.dumps(out,indent=2,ensure_ascii=False))
        return 0 if out.get('ready') else 3
    c=Coordinator()
    try:
        if args.cmd=='status': out=c.status()
        elif args.cmd=='resources':
            registry=ResourceRegistry()
            out=registry.validate() if args.validate else {'summary':registry.summary(),'items':registry.list_resources(category=args.category,status=args.status)}
        elif args.cmd=='quality-eval':
            out=QualityEvaluationRunner(c).run(provider_route=args.provider_route,scenario_ids=args.scenario_ids)
            exit_code=0 if out.get('status')=='passed' else 3
        elif args.cmd=='list': out={'count':len(c.registry),'agents':c.list_agents()}
        elif args.cmd=='run': out=c.invoke(args.agent_id,args.objective,json.loads(args.inputs),idempotency_key=args.idempotency_key,deadline_seconds=args.deadline).to_dict()
        elif args.cmd=='lifecycle':
            out=c.run_lifecycle(args.agent_id,args.objective,json.loads(args.inputs),max_corrections=args.max_corrections,max_improvements=args.max_improvements,deadline_seconds=args.deadline).to_dict()
            exit_code=0 if out.get('status')=='delivered' and out.get('delivered') is True else 3
        elif args.cmd=='chain': out={'results':[r.to_dict() for r in c.run_chain(args.agents,args.objective,json.loads(args.inputs),max_handoffs=args.max_handoffs)]}
        elif args.cmd=='graph': out={'results':c.run_graph(json.loads(args.graph_json),max_nodes=args.max_nodes)}
        else:
            from .benchmark import BenchmarkRunner
            out=BenchmarkRunner().run().to_dict()
        print(json.dumps(out,indent=2,ensure_ascii=False)); return exit_code
    except Exception as e:
        print(json.dumps({'error':type(e).__name__,'message':str(e)}),file=sys.stderr); return 2
    finally: c.close()
if __name__=='__main__': raise SystemExit(main())
