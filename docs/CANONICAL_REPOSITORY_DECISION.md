# Canonical Repository Decision

**Decision date:** 2026-11-06  
**Status:** Owner-approved direction; code review and hosted cutover remain pending.  
**Canonical repository:** `soueilouay-creator/uneXxxx`  
**Canonical v8.1 review branch:** `feat/v8-architecture-freeze-sales-workflow`  
**Related review:** PR #4

## Decision

The owner has approved `soueilouay-creator/uneXxxx` as the sole canonical repository for uneXpected v8 and later v8.1 work. Once PR #4 is reviewed and merged, `main` in this repository is the source of truth for the v8 command center, runtime, role registry, Skills, tests and deployment definition.

The older `soueilouay-creator/uneXpected-` repository is retained as frozen legacy and rollback reference material during migration. It is not a second canonical v8 development line. Do not delete, archive, rewrite, or otherwise mutate it as part of this decision. The separate `uneXpected-ai-studio` repository and service remain legacy/reference material and are also untouched.

This decision does not claim that the hosted service has already changed repositories, that PR #4 has merged, or that a deployment has succeeded.

## Current hosted binding (read-only inspection, 2026-11-06)

The Render service `unexpected-v8-command-center` (`srv-dbk8217b9u1s73ftauig`) is still configured with:

- Repository: `soueilouay-creator/uneXpected-`
- Branch: `feat/unified-v8-foundation`
- Auto-deploy: disabled
- Health-check path: `/health`
- Latest recorded deployment: `dep-dbke4je7bikc73feu3rg`, commit `d1b54ae0e520ff0e701e2584f46d523c2348f6f0`

The repository `uneXxxx` contains the newer v8.1 command center, architecture freeze and industrial-maintenance-sales Skill. Its PR #4 branch passed GitHub Actions run `42264871134` (260 tests, one optional legacy-fixture skip, Docker and container smoke checks). This is CI evidence, not hosted deployment evidence.

The checked-in `uneXxxx/render.yaml` is a declarative service definition; it does not rebind an existing Render service by itself. The connected Render MCP tools expose inspection and deploy operations but not the source-rebinding operation. Render's public Update Service API (`PATCH /v1/services/{serviceId}`) and current CLI also support updating `repo` and `branch`. In this session, no local Render CLI is installed and no `RENDER_API_KEY` is configured, so that API mutation is not available through the current execution host. No source switch, deployment, environment update, database mutation or service creation was performed for this decision.

## Controlled cutover procedure

1. Complete review of PR #4 and merge the approved v8.1 baseline to `uneXxxx/main`. Re-run and verify CI on the exact resulting main commit.
2. Review the complete deployment diff, Docker build context, Render settings and all required non-secret configuration. Keep `autoDeploy=false`.
3. In Render, change the existing service's source repository to `soueilouay-creator/uneXxxx` and select the reviewed commit/branch. Preserve the existing service ID, service settings, domain, health path, plan and instance count. Do not create a parallel production service as a shortcut.
4. Preserve the existing secret values in Render without copying them into Git, chat or logs. Confirm the effective storage target and migrations using non-secret evidence before deploying. Do not replace `DATABASE_URL`, runtime bearer tokens or provider keys as part of a repository-source change.
5. Before the first production deployment, confirm an independent backup/export of the populated runtime database and a tested restore into an isolated target. The earlier test-branch copy rehearsal is not a substitute for a real backup restore.
6. Trigger one controlled manual deploy only after the reviewed cutover plan and rollback target are ready. Verify the exact deployed commit, `/health`, authenticated API, PostgreSQL read/write across independent connections, fresh non-mock provider invocation, audit persistence and the seven-stage lifecycle. Keep external customer messages, public publishing, payments and privileged tools disabled.
7. Record the deploy ID, commit SHA, health/API results, storage branch identity (without connection strings), provider/model provenance and rollback result. Do not call the service verified merely because Render reports it as not suspended.

## Rollback

Keep the old repository, its deploy history and the pre-cutover deployment available. If the new deployment fails any health, authentication, provider, storage or lifecycle gate, stop further writes and restore the previous repository/branch binding on the same service, then manually redeploy the last known-good commit. Verify the health and persisted state after rollback. Do not delete the old repository or retire legacy services until a separately reviewed end-to-end replacement and recovery proof exists.

## Approval boundary

The owner approved the canonical repository direction and replacement of the old repository as the intended source for the existing Render service. That approval does not authorize unrelated infrastructure changes, new services, production data changes, credential rotation, enabling auto-deploy, destructive cleanup, customer outreach or public publication. A production deploy remains a separate controlled step after the cutover plan and backup/rollback gates have been evidenced.
