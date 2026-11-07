from __future__ import annotations
import hashlib
import json
import re
import time
import uuid
from typing import Any

class CreatorStudioError(RuntimeError):
    """Base error for Creator Studio validation and storage failures."""
class CreatorStudioNotFound(CreatorStudioError):
    pass
class CreatorStudioConflict(CreatorStudioError):
    pass

ENGINE_COMMIT = "5c05490cc55dfb54f8f4c333f0f0e79cb6500564"
VERSION_KINDS = {"brief","research","treatment","storyboard","source_bundle","narration","captions","qa_report","platform_package"}
ASSET_KINDS = {"storyboard_image","video_master","audio_master","subtitle_file","thumbnail","source_bundle","qa_report","poster","platform_package"}
MIME_TYPES = {"image/png","image/jpeg","image/webp","video/mp4","audio/wav","audio/mpeg","text/vtt","text/plain","application/json"}
PROJECT_TRANSITIONS = {
 "idea":{"researching","archived"},"researching":{"treatment_ready","idea","archived"},
 "treatment_ready":{"storyboard_ready","authoring","researching"},"storyboard_ready":{"authoring","treatment_ready"},
 "authoring":{"render_queued","treatment_ready"},"render_queued":{"rendering","blocked","authoring"},
 "rendering":{"blocked","qa_failed","qa_passed"},"blocked":{"render_queued","authoring","archived"},
 "qa_failed":{"authoring","render_queued"},"qa_passed":{"human_approved","authoring"},
 "human_approved":{"package_ready","authoring"},"package_ready":{"uploaded","authoring"},
 "uploaded":{"scheduled","published"},"scheduled":{"published"},"published":set(),"archived":set()
}

class CreatorStudioService:
    """Creator project metadata on the shared uneXpected state store."""
    def __init__(self,store,artifact_store=None,render_dispatcher=None):
        self.store=store; self.artifact_store=artifact_store; self.render_dispatcher=render_dispatcher
        if getattr(store,"backend","sqlite")=="postgres":
            ready=getattr(store,"creator_schema_ready",None)
            if not callable(ready) or not ready(): raise CreatorStudioError("Creator Studio PostgreSQL migration 003 is required.")

    @staticmethod
    def _actor(actor):
        if not isinstance(actor,str) or not actor.strip() or len(actor)>120: raise CreatorStudioError("A bounded actor identifier is required.")
        return actor.strip()

    @staticmethod
    def _json(value,maximum=2_000_000):
        try: encoded=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)
        except (TypeError,ValueError) as exc: raise CreatorStudioError("Content must be finite JSON data.") from exc
        if len(encoded.encode("utf-8"))>maximum: raise CreatorStudioError("Content exceeds the configured size limit.")
        return encoded

    def create_project(self,payload,actor):
        actor=self._actor(actor)
        if not isinstance(payload,dict): raise CreatorStudioError("Project payload must be an object.")
        title,topic,language=payload.get("title"),payload.get("topic"),payload.get("language"); channels=payload.get("channel_profile")
        if not isinstance(title,str) or not title.strip() or len(title.strip())>180: raise CreatorStudioError("Project title must contain 1 to 180 characters.")
        if not isinstance(topic,str) or not topic.strip() or len(topic.strip())>600: raise CreatorStudioError("Project topic must contain 1 to 600 characters.")
        if not isinstance(language,str) or not language.strip() or len(language.strip())>48: raise CreatorStudioError("Project language must contain 1 to 48 characters.")
        if not isinstance(channels,dict) or not channels or set(channels)-{"youtube","tiktok"}: raise CreatorStudioError("Only YouTube and TikTok channel profiles are active.")
        if not all(isinstance(v,dict) for v in channels.values()): raise CreatorStudioError("Each channel profile must be a JSON object.")
        self._json(channels,12_000)
        project={"project_id":str(uuid.uuid4()),"title":title.strip(),"topic":topic.strip(),"channel_profile":channels,"language":language.strip()}
        return self.store.create_creator_project(project,actor)

    def get_project(self,project_id):
        project=self.store.get_creator_project(project_id)
        if not project: raise CreatorStudioNotFound("Creator Studio project was not found.")
        return project

    def list_projects(self,limit=50):
        if isinstance(limit,bool) or not isinstance(limit,int): raise CreatorStudioError("Project list limit must be an integer.")
        return self.store.list_creator_projects(max(1,min(limit,200)))

    def save_version(self,project_id,kind,content,parent_version_id,actor):
        actor=self._actor(actor); self.get_project(project_id)
        if kind not in VERSION_KINDS or not isinstance(content,dict): raise CreatorStudioError("Unsupported version kind or non-object content.")
        self._json(content)
        if parent_version_id and parent_version_id not in {v["version_id"] for v in self.store.list_creator_versions(project_id)}:
            raise CreatorStudioNotFound("Parent version does not belong to this project.")
        try: return self.store.create_creator_version(project_id,str(uuid.uuid4()),kind,content,parent_version_id,actor)
        except ValueError as exc: raise CreatorStudioNotFound(str(exc)) from exc

    def list_versions(self,project_id):
        self.get_project(project_id); return self.store.list_creator_versions(project_id)

    def register_asset(self,asset,*,content_bytes):
        if self.artifact_store is None: raise CreatorStudioError("An approved ArtifactStore is required for asset registration.")
        if not isinstance(asset,dict) or not isinstance(content_bytes,bytes): raise CreatorStudioError("Asset metadata and bytes are required.")
        project=self.get_project(asset.get("project_id"))
        if asset.get("version_id") not in {v["version_id"] for v in self.store.list_creator_versions(project["project_id"])}:
            raise CreatorStudioNotFound("Asset version does not belong to this project.")
        kind,mime,key=asset.get("kind"),asset.get("mime_type"),asset.get("storage_key")
        if kind not in ASSET_KINDS or mime not in MIME_TYPES: raise CreatorStudioError("Asset kind or MIME type is not permitted.")
        if not isinstance(key,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,255}",key) or any(x in {"",".",".."} for x in key.split("/")):
            raise CreatorStudioError("Asset storage key is unsafe.")
        if len(content_bytes)>100_000_000: raise CreatorStudioError("Asset exceeds the 100 MB registration limit.")
        digest=hashlib.sha256(content_bytes).hexdigest()
        if asset.get("sha256")!=digest or asset.get("byte_size")!=len(content_bytes): raise CreatorStudioError("Asset checksum or byte size verification failed.")
        provenance,license_info=asset.get("provenance",{}),asset.get("license",{})
        if not isinstance(provenance,dict) or not isinstance(license_info,dict): raise CreatorStudioError("Asset provenance and licence must be JSON objects.")
        self._json(provenance,12_000); self._json(license_info,12_000)
        qa=asset.get("qa_status","pending")
        if qa not in {"pending","needs_review","passed","failed"}: raise CreatorStudioError("Invalid asset QA status.")
        self.artifact_store.put(key,content_bytes)
        record={"asset_id":str(uuid.uuid4()),"project_id":project["project_id"],"version_id":asset["version_id"],"kind":kind,"storage_key":key,
                "sha256":digest,"byte_size":len(content_bytes),"mime_type":mime,"provenance":provenance,"license":license_info,"qa_status":qa}
        try: return self.store.create_creator_asset(record)
        except Exception:
            delete=getattr(self.artifact_store,"delete",None)
            if callable(delete): delete(key)
            raise

    def create_render_job(self,job):
        if not isinstance(job,dict): raise CreatorStudioError("Render job must be an object.")
        project=self.get_project(job.get("project_id")); version=job.get("version_id")
        if version not in {v["version_id"] for v in self.store.list_creator_versions(project["project_id"])}: raise CreatorStudioNotFound("Render job version does not belong to this project.")
        if job.get("engine_commit")!=ENGINE_COMMIT: raise CreatorStudioError("Render jobs must use the pinned Opuscar commit.")
        style=job.get("style_id")
        if not isinstance(style,str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}",style): raise CreatorStudioError("A bounded style identifier is required.")
        key=job.get("idempotency_key")
        if not isinstance(key,str) or not 8<=len(key)<=128 or not re.fullmatch(r"[A-Za-z0-9._:-]+",key): raise CreatorStudioError("Render idempotency key must be 8 to 128 safe characters.")
        request=job.get("request",{})
        if not isinstance(request,dict): raise CreatorStudioError("Render request must be an object.")
        self._json(request,256_000); raw=job.get("resource_limits",{})
        if not isinstance(raw,dict) or set(raw)-{"cpu_seconds","memory_mb","wall_time_seconds"}: raise CreatorStudioError("Unsupported render resource limit.")
        limits={"cpu_seconds":raw.get("cpu_seconds",60),"memory_mb":raw.get("memory_mb",512),"wall_time_seconds":raw.get("wall_time_seconds",90)}
        for field,low,high in (("cpu_seconds",1,600),("memory_mb",256,4096),("wall_time_seconds",1,1800)):
            value=limits[field]
            if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high: raise CreatorStudioError(f"Render {field} is outside the permitted range.")
        canonical={"project_id":project["project_id"],"version_id":version,"engine_commit":ENGINE_COMMIT,"style_id":style,"request":request,"resource_limits":limits}
        digest=hashlib.sha256(self._json(canonical,300_000).encode("utf-8")).hexdigest(); now=time.time()
        record={"job_id":str(uuid.uuid4()),"project_id":project["project_id"],"version_id":version,"engine_commit":ENGINE_COMMIT,"style_id":style,
                "status":"blocked","idempotency_key":key,"request_hash":digest,"resource_limits":limits,
                "result_manifest":{"status":"blocked","code":"renderer_unavailable"},"created_at":now,"updated_at":now}
        try: return self.store.create_creator_render_job(record)
        except ValueError as exc: raise CreatorStudioConflict(str(exc)) from exc

    def get_render_job(self,job_id):
        job=self.store.get_creator_render_job(job_id)
        if not job: raise CreatorStudioNotFound("Creator Studio render job was not found.")
        return job

    def get_project_detail(self,project_id,limit=50):
        project=self.get_project(project_id)
        bounded=max(1,min(int(limit),200))
        return {"project":project,
                "versions":self.store.list_creator_versions(project_id),
                "assets":self.store.list_creator_assets(project_id),
                "render_jobs":self.store.list_creator_render_jobs(project_id,bounded)}

    def recover_interrupted_jobs(self):
        # Startup recovery never re-runs work. It only blocks orphaned worker leases.
        recovered=[]
        for project in self.store.list_creator_projects(200):
            for job in self.store.list_creator_render_jobs(project["project_id"],200):
                if job.get("status") not in {"queued","rendering"}:
                    continue
                manifest={"status":"blocked","code":"worker_lease_lost",
                          "recovery":"startup_recovery_did_not_retry",
                          "previous_status":job["status"],"recovered_at":time.time()}
                updated=self.store.transition_creator_render_job(
                    job["job_id"],job["status"],"blocked",manifest
                )
                if updated:
                    recovered.append(updated["job_id"])
        return {"recovered_count":len(recovered),"job_ids":recovered}

    def transition_project(self,project_id,expected_status,next_status,actor,evidence):
        actor=self._actor(actor); self.get_project(project_id)
        if next_status not in PROJECT_TRANSITIONS.get(expected_status,set()): raise CreatorStudioError(f"Project transition {expected_status!r} -> {next_status!r} is not allowed.")
        if not isinstance(evidence,dict): raise CreatorStudioError("Transition evidence must be an object.")
        self._json(evidence,16_000)
        if next_status in {"uploaded","scheduled","published"} and not evidence.get("provider_evidence"): raise CreatorStudioError("External state requires provider evidence.")
        updated=self.store.transition_creator_project(project_id,expected_status,next_status,actor,evidence)
        if not updated: raise CreatorStudioConflict("Project status changed; refresh before retrying.")
        return updated

__all__=["CreatorStudioService","CreatorStudioError","CreatorStudioNotFound","CreatorStudioConflict","ENGINE_COMMIT","PROJECT_TRANSITIONS"]
