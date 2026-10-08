"""デモ専用コマンドが通常資源や資格情報を利用しないことを検証する。"""

import copy
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.deploy import demo, environment, storage


def portfolio_outputs():
    return {
        "neon_project_id": "existing-project",
        "database_admin_connection": {
            "host": "ep-existing.neon.tech",
            "pooled_host": "ep-existing-pooler.neon.tech",
        },
    }


def dedicated_outputs():
    return {
        "neon_project_id": "demo-project",
        "neon_branch_id": "demo-branch",
        "database_admin_connection": {
            "host": "ep-demo.neon.tech",
            "pooled_host": "ep-demo-pooler.neon.tech",
            "database": "syncnesto",
            "username": "syncnesto_owner",
            "password": "fixture-owner-password",
        },
        "migration_database_url": "postgresql://syncnesto_owner:fixture@ep-demo.neon.tech/syncnesto?sslmode=verify-full",
        "backend_jwt_secret": "fixture-demo-jwt",
        "backend_bff_secret": "fixture-demo-bff",
        "backend_cron_secret": "fixture-demo-cron",
    }


class DemoDatabaseTests(unittest.TestCase):
    def test_runtime_refuses_owner_normal_host_and_unverified_tls(self):
        uri = "postgresql://syncnesto_app:fixture@ep-demo-pooler.neon.tech/syncnesto?sslmode=verify-full"
        self.assertEqual(
            demo.restricted_runtime_uri(
                dedicated_outputs(), {"backend_database_url": uri}
            ),
            uri,
        )
        for invalid in (
            uri.replace("ep-demo", "ep-existing"),
            uri.replace("syncnesto_app", "syncnesto_owner"),
            uri.replace("verify-full", "require"),
        ):
            with self.assertRaises(RuntimeError):
                demo.restricted_runtime_uri(
                    dedicated_outputs(), {"backend_database_url": invalid}
                )

    def test_rejects_existing_project_host_and_mismatched_uri(self):
        variants = []
        for change in ("project", "host", "pooler", "state-db", "uri"):
            value = copy.deepcopy(dedicated_outputs())
            if change == "project":
                value["neon_project_id"] = "existing-project"
            elif change == "host":
                value["database_admin_connection"]["host"] = "ep-existing.neon.tech"
            elif change == "pooler":
                value["database_admin_connection"]["pooled_host"] = (
                    "ep-existing-pooler.neon.tech"
                )
            elif change == "state-db":
                value["database_admin_connection"]["database"] = "syncnesto_terraform"
            else:
                value["migration_database_url"] = value[
                    "migration_database_url"
                ].replace("ep-demo", "ep-existing")
            variants.append(value)
        for value in variants:
            with (
                self.subTest(value=value["neon_project_id"]),
                patch.object(
                    demo, "terraform_outputs", side_effect=[portfolio_outputs(), value]
                ),
            ):
                with self.assertRaises(RuntimeError):
                    demo.demo_outputs({})

    def test_backend_uses_only_demo_db_and_disables_mail_and_demo_entry(self):
        with (
            patch.object(
                demo,
                "state_environment",
                return_value={
                    "PGSSLROOTCERT": "trusted-ca",
                    "EMAIL_PROVIDER": "smtp",
                    "AWS_ACCESS_KEY_ID": "portfolio-key",
                    "AWS_SECRET_ACCESS_KEY": "portfolio-secret",
                    "AWS_SESSION_TOKEN": "portfolio-session",
                    "DEMO_MODE": "true",
                },
            ),
            patch.object(demo, "demo_outputs", return_value=dedicated_outputs()),
        ):
            env = demo.backend_environment()
        self.assertIn("ep-demo.neon.tech", env["DATABASE_URL"])
        self.assertEqual(env["APP_ENV"], "production")
        self.assertEqual(env["DEMO_MODE"], "false")
        self.assertEqual(env["DEMO_DATA_ISOLATED"], "true")
        self.assertEqual(env["EMAIL_PROVIDER"], "disabled")
        for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
            self.assertEqual(env[key], "")

    def test_production_ci_stack_list_excludes_demo_stacks(self):
        self.assertEqual(set(environment.STACKS), {"vercel", "neon", "runtime"})
        self.assertEqual(set(environment.DEMO_STACKS), {"demo", "demo-neon"})

    def test_nonempty_database_refuses_initialization(self):
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (
            1,
            0,
            0,
        )
        with patch.object(demo.verify_database, "connect", return_value=connection):
            with self.assertRaises(
                RuntimeError, msg="Existing identities must never be seeded"
            ):
                demo.empty_database({})
        connection.close.assert_called_once()

    def test_child_receives_no_management_or_state_credentials(self):
        env = {
            "DATABASE_URL": "demo-db-fixture",
            "AWS_ACCESS_KEY_ID": "demo-key-fixture",
            "PG_CONN_STR": "state-fixture",
            "SUPABASE_ACCESS_TOKEN": "management-fixture",
            "DEMO_SUPABASE_ACCESS_TOKEN": "demo-management-fixture",
            "NEON_API_KEY": "neon-fixture",
            "DEMO_SUPABASE_S3_SECRET_ACCESS_KEY": "duplicate-fixture",
        }
        summary = {
            "processed": 1,
            "pending": 1,
            "remaining": 3,
            "execute": True,
            "limit": 10,
        }
        result = MagicMock(returncode=0, stdout=json.dumps(summary))
        stream = io.StringIO()
        with patch.object(demo.subprocess, "run", return_value=result) as run:
            with contextlib.redirect_stdout(stream):
                demo.run_backend(
                    ["python", "-m", "scripts.cleanup_demo"], env, cleanup=True
                )
        forwarded = run.call_args.kwargs["env"]
        self.assertEqual(set(forwarded), {"DATABASE_URL", "AWS_ACCESS_KEY_ID"})
        self.assertIn("pending=1", stream.getvalue())
        self.assertIn("remaining=3", stream.getvalue())
        self.assertNotIn("fixture", stream.getvalue())

    def test_failed_child_logs_never_disclose_credentials(self):
        result = MagicMock(
            returncode=1, stdout="private-fixture", stderr="private-fixture"
        )
        with patch.object(demo.subprocess, "run", return_value=result):
            with self.assertRaises(RuntimeError) as caught:
                demo.run_backend(["alembic", "upgrade", "head"], {})
            self.assertNotIn("private-fixture", str(caught.exception))


class DemoStorageTests(unittest.TestCase):
    def credentials(self):
        return {
            "DEMO_SUPABASE_PROJECT_REF": "a" * 20,
            "DEMO_SUPABASE_S3_ACCESS_KEY_ID": "demo-key-fixture",
            "DEMO_SUPABASE_S3_SECRET_ACCESS_KEY": "demo-secret-fixture",
        }

    def test_storage_never_falls_back_to_portfolio_keys(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(demo, "ROOT", Path(directory)),
        ):
            with self.assertRaises(RuntimeError):
                demo.storage_environment(
                    {
                        "SUPABASE_S3_ACCESS_KEY_ID": "original-key",
                        "SUPABASE_S3_SECRET_ACCESS_KEY": "original-secret",
                    }
                )
            for override in (
                {"DEMO_SUPABASE_PROJECT_REF": storage.PROJECT},
                {"SUPABASE_S3_ACCESS_KEY_ID": "demo-key-fixture"},
                {"SUPABASE_S3_SECRET_ACCESS_KEY": "demo-secret-fixture"},
            ):
                with self.assertRaises(RuntimeError):
                    demo.storage_environment(self.credentials() | override)

    def test_credentials_require_owner_only_file_and_export_takes_precedence(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(demo, "ROOT", Path(directory)),
        ):
            file = Path(directory) / ".env.demo.local"
            file.write_text(
                "DEMO_SUPABASE_PROJECT_REF='" + "b" * 20 + "'\n"
                "DEMO_SUPABASE_ACCESS_TOKEN=demo-management-fixture\n"
            )
            file.chmod(0o644)
            with self.assertRaises(RuntimeError):
                demo.storage_environment(self.credentials())
            file.chmod(0o600)
            self.assertEqual(
                demo.storage_environment(self.credentials())[demo.STORAGE_KEYS[0]],
                "a" * 20,
            )
            self.assertEqual(
                demo.management_token(demo.storage_environment(self.credentials())),
                "demo-management-fixture",
            )

    def test_dedicated_management_token_is_used_for_both_project_and_bucket(self):
        env = self.credentials() | {
            "SUPABASE_ACCESS_TOKEN": "portfolio-management-fixture",
            "DEMO_SUPABASE_ACCESS_TOKEN": "demo-management-fixture",
        }
        target = demo.storage_target(env)
        metadata = {
            "id": target.project,
            "organization_id": demo.SUPABASE_ORGANIZATION,
            "name": "syncnesto-demo",
            "region": target.region,
            "status": "ACTIVE_HEALTHY",
        }
        with (
            patch.object(
                storage,
                "request",
                return_value=(200, {}, json.dumps(metadata).encode()),
            ) as request,
            patch.object(storage, "s3_client") as client,
        ):
            demo.verify_storage(env, target)
            self.assertEqual(
                request.call_args.kwargs["headers"]["Authorization"],
                "Bearer demo-management-fixture",
            )
            client.return_value.list_buckets.assert_called_once()
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(
                storage,
                "request",
                return_value=(
                    200,
                    {},
                    b'[{"name":"service_role","api_key":"fixture-service-role"}]',
                ),
            ) as request,
        ):
            storage.storage_headers(target, management_token=demo.management_token(env))
            self.assertEqual(
                request.call_args.kwargs["headers"]["Authorization"],
                "Bearer demo-management-fixture",
            )
            self.assertIn(target.project, request.call_args.args[0])

    def test_management_token_is_required_before_network_access(self):
        with patch.object(storage, "request") as request:
            with self.assertRaises(RuntimeError):
                demo.verify_storage(
                    self.credentials(), demo.storage_target(self.credentials())
                )
            request.assert_not_called()

    def test_storage_project_must_belong_to_approved_organization(self):
        env = self.credentials() | {"SUPABASE_ACCESS_TOKEN": "management-fixture"}
        target = demo.storage_target(env)
        metadata = {
            "id": target.project,
            "organization_id": "different-organization",
            "name": "syncnesto-demo",
            "region": target.region,
            "status": "ACTIVE_HEALTHY",
        }
        with (
            patch.object(
                storage,
                "request",
                return_value=(200, {}, json.dumps(metadata).encode()),
            ),
            patch.object(storage, "s3_client") as client,
        ):
            with self.assertRaises(RuntimeError):
                demo.verify_storage(env, target)
            client.assert_not_called()

    def test_prepare_targets_only_demo_bucket_with_provider_size_limit(self):
        target = demo.storage_target(self.credentials())
        client = MagicMock()
        replies = [
            (404, {}, b"{}"),
            (201, {}, b"{}"),
            (
                200,
                {},
                json.dumps(
                    {"public": False, "file_size_limit": 5 * 1024 * 1024}
                ).encode(),
            ),
        ]
        with (
            patch.object(storage, "storage_headers", return_value={}),
            patch.object(storage, "request", side_effect=replies) as request,
        ):
            storage.prepare(client, target)
        self.assertEqual(client.put_object.call_args.kwargs["Bucket"], "syncnesto-demo")
        for call in request.call_args_list:
            self.assertIn(target.project, call.args[0])
            self.assertNotIn(storage.PROJECT, call.args[0])
        created = json.loads(request.call_args_list[1].kwargs["body"])
        self.assertEqual(created["file_size_limit"], 5 * 1024 * 1024)
        self.assertFalse(created["public"])

    def test_sdk_uses_explicit_demo_endpoint_and_credentials(self):
        env = self.credentials()
        target = demo.storage_target(env)
        with (
            patch.object(storage.boto3, "client") as client,
            patch.dict(os.environ, {}, clear=True),
        ):
            storage.s3_client(
                target,
                access_key=env[demo.STORAGE_KEYS[1]],
                secret_key=env[demo.STORAGE_KEYS[2]],
            )
        kwargs = client.call_args.kwargs
        self.assertEqual(kwargs["endpoint_url"], target.endpoint)
        self.assertEqual(kwargs["aws_access_key_id"], "demo-key-fixture")
        self.assertEqual(kwargs["aws_secret_access_key"], "demo-secret-fixture")
