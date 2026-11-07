-- Additive, versioned schema for uneXpected Creator Studio metadata.
-- Media bytes remain outside PostgreSQL behind an ArtifactStore.
BEGIN;
CREATE TABLE IF NOT EXISTS creator_projects (
 project_id TEXT PRIMARY KEY,title TEXT NOT NULL,topic TEXT NOT NULL,channel_profile_json TEXT NOT NULL,language TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('idea','researching','treatment_ready','storyboard_ready','authoring','render_queued','rendering','blocked','qa_failed','qa_passed','human_approved','package_ready','uploaded','scheduled','published','archived')),
 created_at DOUBLE PRECISION NOT NULL,updated_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_creator_projects_status_updated ON creator_projects(status,updated_at);
CREATE TABLE IF NOT EXISTS creator_project_versions (
 version_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES creator_projects(project_id) ON DELETE RESTRICT,
 version_no INTEGER NOT NULL CHECK(version_no>0),kind TEXT NOT NULL,content_json TEXT NOT NULL,parent_version_id TEXT,created_at DOUBLE PRECISION NOT NULL,
 UNIQUE(project_id,version_no),UNIQUE(project_id,version_id),
 FOREIGN KEY(project_id,parent_version_id) REFERENCES creator_project_versions(project_id,version_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_creator_versions_project_no ON creator_project_versions(project_id,version_no);
CREATE TABLE IF NOT EXISTS creator_project_assets (
 asset_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES creator_projects(project_id) ON DELETE RESTRICT,
 version_id TEXT NOT NULL,kind TEXT NOT NULL,storage_key TEXT NOT NULL UNIQUE,
 sha256 TEXT NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),byte_size BIGINT NOT NULL CHECK(byte_size>=0),
 mime_type TEXT NOT NULL,provenance_json TEXT NOT NULL,license_json TEXT NOT NULL,
 qa_status TEXT NOT NULL CHECK(qa_status IN ('pending','needs_review','passed','failed')),created_at DOUBLE PRECISION NOT NULL,
 FOREIGN KEY(project_id,version_id) REFERENCES creator_project_versions(project_id,version_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_creator_assets_project ON creator_project_assets(project_id,created_at);
CREATE TABLE IF NOT EXISTS creator_render_jobs (
 job_id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES creator_projects(project_id) ON DELETE RESTRICT,
 version_id TEXT NOT NULL,engine_commit TEXT NOT NULL CHECK(engine_commit ~ '^[0-9a-f]{40}$'),style_id TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('queued','blocked','running','succeeded','failed','cancelled')),
 idempotency_key TEXT NOT NULL UNIQUE,request_hash TEXT NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
 resource_limits_json TEXT NOT NULL,result_manifest_json TEXT NOT NULL,created_at DOUBLE PRECISION NOT NULL,updated_at DOUBLE PRECISION NOT NULL,
 FOREIGN KEY(project_id,version_id) REFERENCES creator_project_versions(project_id,version_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_creator_render_jobs_project_created ON creator_render_jobs(project_id,created_at);
INSERT INTO schema_migrations(version,name,applied_at) VALUES(3,'003_creator_studio.sql',EXTRACT(EPOCH FROM clock_timestamp()))
ON CONFLICT(version) DO NOTHING;
COMMIT;
