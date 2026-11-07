from __future__ import annotations
import re
class CreatorPlatformPackageError(ValueError): pass
class CreatorPlatformPackager:
 """Creates separate platform metadata manifests; no credentials or publishing code."""
 @staticmethod
 def _text(v,n):
  if not isinstance(v,str): raise CreatorPlatformPackageError("Project metadata must be text.")
  return re.sub(r"\s+"," ",v).strip()[:n]
 def build_both(self,project,asset,qa):
  if not all(isinstance(x,dict) for x in (project,asset,qa)): raise CreatorPlatformPackageError("Project, asset and QA records are required.")
  if qa.get("status")!="passed": raise CreatorPlatformPackageError("Packages require passing encoded-media QA.")
  if asset.get("mime_type")!="video/mp4" or not re.fullmatch(r"[0-9a-f]{64}",str(asset.get("sha256",""))): raise CreatorPlatformPackageError("A checksummed MP4 asset is required.")
  m=qa.get("media") or {}
  if (m.get("width"),m.get("height"))!=(1080,1920) or m.get("duration_seconds",0)<=0: raise CreatorPlatformPackageError("A QA-passed vertical master is required.")
  title=self._text(project.get("title"),100);topic=self._text(project.get("topic"),600);lang=self._text(project.get("language"),48)
  if not title or not topic or not lang: raise CreatorPlatformPackageError("Title, topic and language are required.")
  tags=list(dict.fromkeys(["shorts","video","creatorstudio"]+[re.sub(r"[^a-z0-9]","",x.lower()) for x in topic.split() if len(x)>3]))[:12]
  video={"filename":"master.mp4","sha256":asset["sha256"],"mime_type":"video/mp4","aspect_ratio":"9:16","width":1080,"height":1920,"duration_seconds":m["duration_seconds"]}
  yt={"status":"ready_for_review","platform":"youtube","metadata":{"title":title,"description":f"{topic}\n\nLanguage: {lang}\n\nCreated with uneXpected Creator Studio."[:5000],"tags":tags,"format":"Shorts","language":lang},"video":video,"qa_sha256":qa.get("sha256"),"uploads_enabled":False,"publication_status":"not_uploaded"}
  hashtags=" ".join("#"+x for x in tags[:6])
  tt={"status":"ready_for_review","platform":"tiktok","metadata":{"caption":(f"{title} — {topic} "+hashtags)[:2200],"hashtags":["#"+x for x in tags[:6]],"language":lang,"cover_frame_seconds":min(1.0,float(m["duration_seconds"])/2)},"video":video,"qa_sha256":qa.get("sha256"),"uploads_enabled":False,"publication_status":"not_uploaded"}
  return {"youtube":yt,"tiktok":tt}
__all__=["CreatorPlatformPackager","CreatorPlatformPackageError"]
