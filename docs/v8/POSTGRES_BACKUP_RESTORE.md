# PostgreSQL backup and restore runbook

**Scope:** operator-controlled logical backups for uneXpected V8 PostgreSQL data. This runbook does not authorize a production restore, database replacement, service restart, or deployment.

## Create a backup

Use an approved secure shell on a trusted machine. Configure the PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE and TLS-related PG* variables from the database provider's secret manager. Do not put passwords in command arguments, commit them to a file, or paste connection strings into chat. Disable shell tracing before handling environment variables.

```sh
set +x
umask 077
: "${PGHOST:?PGHOST is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGDATABASE:?PGDATABASE is required}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/uneXpected-backups}"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/uneXpected-$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump --format=custom --no-owner --no-acl --dbname="$PGDATABASE" --file="$BACKUP_FILE"
chmod 600 "$BACKUP_FILE"
sha256sum "$BACKUP_FILE" > "$BACKUP_FILE.sha256"
pg_restore --list "$BACKUP_FILE" >/dev/null
sha256sum --check "$BACKUP_FILE.sha256"
```

Treat a non-zero exit from any command as a failed backup. Keep the archive and checksum together. Copy both to an encrypted, access-controlled location separate from the database host and verify the uploaded checksum. The repository does not currently configure an off-site backup destination, retention policy, or scheduled backup job; those must be provided and operationally verified before production disaster-recovery readiness can be claimed.

## Restore to a separate empty database

Create a fresh recovery database or isolated provider branch. Never restore over the populated source database and never use pg_restore --clean for this procedure. Configure the PG* environment variables for the recovery target, not the source.

```sh
set +x
: "${PGDATABASE:?PGDATABASE must name the separate empty recovery database}"
sha256sum --check "/secure/path/uneXpected-backup.dump.sha256"
pg_restore --exit-on-error --single-transaction --no-owner --no-acl --dbname="$PGDATABASE" "/secure/path/uneXpected-backup.dump"
```

A restore error aborts the single transaction; leave the source untouched. After a successful restore, verify the newest schema_migrations.version is 7, check key row counts and representative task, event, memory, approval and workflow records, then run the read-only application health and authenticated API smoke checks against the recovery target. Record the archive hash, source/target identifiers, restore timestamp, migration version, row-count comparison and operator sign-off. Do not promote or redirect production traffic as part of this drill.

## What CI verifies

The PostgreSQL 16 full runtime CI job and PostgreSQL 17 targeted release-proof job create disposable source and target databases, apply migrations 001–007, seed representative runtime records, create a custom-format pg_dump archive using a client matched to the server major version, validate it with pg_restore --list, restore it into a separate empty database, and compare every public base-table row count plus exact task/event/memory/approval/probe read-backs. Both temporary databases are dropped after each test. The PostgreSQL 17 job also repeats approval concurrency, abrupt-process recovery and positive pause/resume tests to match the current Neon project major version.

This proves the logical archive/restore path against the CI PostgreSQL image. It does **not** prove that a production Neon snapshot exists, that backups are scheduled or retained, that archives are stored off-site, or that a production RPO/RTO has been met. Those operational controls remain release blockers until configured and tested under a separately approved production recovery exercise.
