from __future__ import annotations
import re
class CreatorPlatformPackageError(ValueError): pass
class CreatorPlatformPackager:
 """Creates YouTube and TikTok metadata manifests only; it cannot upload or publish."""
 @staticmethod
 def _text(value,limit):
  if not isinstance(value,str): raise CreatorPlatformPackageError("Project metadata must be text.")
  return re.sub(r"\s+"," ",value).strip()[:limit]
 def build_both(self,project,asset,qa):
  if not all(isinstance(x,dict) for x in (project,asset,qa)): raise CreatorPlatformPackageError("Project, asset and QA records are required.")
  if qa.get("status")!="passed": raise CreatorPlatformPackageError("Packages require passing encoded-media QA.")
  if asset.get("mime_type")!="video/mp4" or not re.fullmatch(r"[0-9a-f]{64}",str(asset.get("sha256",""))): raise CreatorPlatformPackageError("A checksummed MP4 asset is required.")
  media=qa.get("media") or {}
  if (media.get("width"),media.get("height"))!=(1080,1920) or media.get("duration_seconds",0)<=0: raise CreatorPlatformPackageError("A QA-passed vertical master is required.")
  title=self._text(project.get("title"),100);topic=self._text(project.get("topic"),600);language=self._text(project.get("language"),48)
  if not title or not topic or not language: raise CreatorPlatformPackageError("Title, topic and language are required.")
  tags=list(dict.fromkeys(["shorts","video","creatorstudio"]+[re.sub(r"[^a-z0-9]","",w.lower()) for w in topic.split() if len(w)>3]))[:12]
  common={"filename":"master.mp4","sha256":asset["sha256"],"mime_type":"video/mp4","aspect_ratio":"9:16","width":1080,"height":1920,"duration_seconds":media["duration_seconds"]}
  youtube={"status":"ready_for_review","platform":"youtube","metadata":{"title":title,"description":f"{topic}\n\nLanguage: {language}\n\nCreated with uneXpected Creator Studio."[:5000],"tags":tags,"format":"Shorts","language":language},"video":common,"qa_sha256":qa.get("sha256"),"uploads_enabled":False,"publication_status":"not_uploaded"}
  hashtags=" ".join("#"+x for x in tags[:6])
  tiktok={"status":"ready_for_review","platform":"tiktok","metadata":{"caption":(f"{title} — {topic} "+hashtags)[:2200],"hashtags":["#"+x for x in tags[:6]],"language":language,"cover_frame_seconds":min(1.0,float(media["duration_seconds"])/2)},"video":common,"qa_sha256":qa.get("sha256"),"uploads_enabled":False,"publication_status":"not_uploaded"}
  return {"youtube":youtube,"tiktok":tiktok}
__all__=["CreatorPlatformPackager","CreatorPlatformPackageError"]
