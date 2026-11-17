from __future__ import annotations
import hashlib, os, shutil, subprocess, tempfile, unittest, uuid
from pathlib import Path
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = Path(__file__).resolve().parents[1]

def _libpq_env(dsn: str) -> tuple[dict[str, str], str]:
    options = conninfo_to_dict(dsn)
    mapping = {
        "host": "PGHOST", "hostaddr": "PGHOSTADDR", "port": "PGPORT",
        "user": "PGUSER", "password": "PGPASSWORD", "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT", "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY", "connect_timeout": "PGCONNECT_TIMEOUT",
        "application_name": "PGAPPNAME",
    }
    environment = os.environ.copy()
    for source, target in mapping.items():
        if options.get(source) is not None:
            environment[target] = str(options[source])
    database = options.get("dbname")
    if not database:
        raise ValueError("The PostgreSQL test DSN must name a database.")
    return environment, str(database)

class PostgreSQLBackupRestoreDrillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get("TEST_POSTGRES_DSN")
        if not cls.dsn:
            raise unittest.SkipTest("TEST_POSTGRES_DSN is not configured.")
        if not shutil.which("pg_dump") or not shutil.which("pg_restore"):
            raise AssertionError("CI must install pg_dump and pg_restore before this drill.")

    def test_custom_archive_restores_migrations_and_all_public_table_rows(self):
        suffix = uuid.uuid4().hex[:16]
        source_name = "unexpected_backup_source_" + suffix
        target_name = "unexpected_backup_restore_" + suffix
        admin_dsn = make_conninfo(self.dsn, dbname="postgres")
        source_dsn = make_conninfo(self.dsn, dbname=source_name)
        target_dsn = make_conninfo(self.dsn, dbname=target_name)
        created_databases = []
        with tempfile.TemporaryDirectory(prefix="unexpected-pg-backup-") as directory:
            archive = Path(directory) / "runtime.dump"
            try:
                with psycopg.connect(admin_dsn, autocommit=True) as admin:
                    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(source_name)))
                    created_databases.append(source_name)
                with psycopg.connect(source_dsn, autocommit=True) as source:
                    for migration in sorted((ROOT / "migrations").glob("*.sql")):
                        source.execute(migration.read_text(encoding="utf-8"), prepare=False)
                    source.execute(
                        "INSERT INTO tasks(task_id,agent_id,status,payload_json,result_json,created_at,updated_at) "
                        "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                        ("backup-restore-task", "orchestrator", "completed",
                         '{"objective":"preserve backup data"}', '{"status":"completed"}', 10.0, 11.0),
                    )
                    source.execute(
                        "INSERT INTO events(ts,task_id,agent_id,event_type,payload_json) "
                        "VALUES(%s,%s,%s,%s,%s)",
                        (12.0, "backup-restore-task", "orchestrator", "backup_restore_probe", '{"retained":true}'),
                    )
                    source.execute(
                        "INSERT INTO agent_memory(agent_id,key,value_json,updated_at) "
                        "VALUES(%s,%s,%s,%s)",
                        ("orchestrator", "backup-restore-probe", '{"memory":"retained"}', 13.0),
                    )
                    source.execute(
                        "INSERT INTO consumed_approvals(approval_id,action_digest,consumed_at) "
                        "VALUES(%s,%s,%s)",
                        ("backup-restore-approval", "a" * 64, 14.0),
                    )
                    source.execute(
                        "CREATE TABLE backup_restore_probe("
                        "probe_id TEXT PRIMARY KEY, marker TEXT NOT NULL, payload JSONB NOT NULL)"
                    )
                    source.execute(
                        "INSERT INTO backup_restore_probe(probe_id,marker,payload) VALUES(%s,%s,%s::jsonb)",
                        ("restore-readback", "v8-restore-ok", '{"migrations":7,"preserved":true}'),
                    )

                env, source_db = _libpq_env(source_dsn)
                dumped = subprocess.run(
                    ["pg_dump", "--format=custom", "--no-owner", "--no-acl",
                     "--dbname", source_db, "--file", str(archive)],
                    env=env, capture_output=True, text=True, timeout=90, check=False,
                )
                self.assertEqual(dumped.returncode, 0, msg=dumped.stderr[-3000:])
                self.assertTrue(archive.is_file())
                self.assertGreater(archive.stat().st_size, 0)
                self.assertEqual(len(hashlib.sha256(archive.read_bytes()).hexdigest()), 64)
                os.chmod(archive, 0o600)
                listed = subprocess.run(
                    ["pg_restore", "--list", str(archive)],
                    env=env, capture_output=True, text=True, timeout=30, check=False,
                )
                self.assertEqual(listed.returncode, 0, msg=listed.stderr[-3000:])
                self.assertIn("TABLE DATA", listed.stdout)

                with psycopg.connect(admin_dsn, autocommit=True) as admin:
                    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_name)))
                    created_databases.append(target_name)
                restore_env, target_db = _libpq_env(target_dsn)
                restored = subprocess.run(
                    ["pg_restore", "--exit-on-error", "--single-transaction",
                     "--no-owner", "--no-acl", "--dbname", target_db, str(archive)],
                    env=restore_env, capture_output=True, text=True, timeout=120, check=False,
                )
                self.assertEqual(restored.returncode, 0, msg=restored.stderr[-5000:])

                def table_counts(dsn):
                    with psycopg.connect(dsn) as connection:
                        names = connection.execute(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
                        ).fetchall()
                        return {
                            name: connection.execute(
                                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(name))
                            ).fetchone()[0] for (name,) in names
                        }
                self.assertEqual(table_counts(target_dsn), table_counts(source_dsn))
                with psycopg.connect(target_dsn) as restored_db:
                    self.assertEqual(restored_db.execute(
                        "SELECT max(version) FROM schema_migrations").fetchone()[0], 7)
                    self.assertEqual(restored_db.execute(
                        "SELECT payload_json,result_json FROM tasks WHERE task_id=%s",
                        ("backup-restore-task",)).fetchone(),
                        ('{"objective":"preserve backup data"}', '{"status":"completed"}'))
                    self.assertEqual(restored_db.execute(
                        "SELECT event_type,payload_json FROM events WHERE task_id=%s "
                        "ORDER BY event_id DESC LIMIT 1", ("backup-restore-task",)).fetchone(),
                        ("backup_restore_probe", '{"retained":true}'))
                    self.assertEqual(restored_db.execute(
                        "SELECT value_json FROM agent_memory WHERE agent_id=%s AND key=%s",
                        ("orchestrator", "backup-restore-probe")).fetchone(),
                        ('{"memory":"retained"}',))
                    self.assertEqual(restored_db.execute(
                        "SELECT marker,payload::text FROM backup_restore_probe WHERE probe_id=%s",
                        ("restore-readback",)).fetchone(),
                        ("v8-restore-ok", '{"migrations": 7, "preserved": true}'))
                    self.assertEqual(restored_db.execute(
                        "SELECT action_digest FROM consumed_approvals WHERE approval_id=%s",
                        ("backup-restore-approval",)).fetchone(), ("a" * 64,))
            finally:
                with psycopg.connect(admin_dsn, autocommit=True) as admin:
                    for database in reversed(created_databases):
                        admin.execute(
                            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
                        )

if __name__ == "__main__":
    unittest.main(verbosity=2)
