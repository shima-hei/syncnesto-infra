"""公開環境の認証情報・CLI・CI制約の回帰テスト。"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.deploy import ci, environment, terraform
from scripts.deploy.__main__ import main as dispatch


class EnvironmentTests(unittest.TestCase):
    def test_exported_state_connection_takes_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.terraform-state.local").write_text(
                "PG_CONN_STR='from-file'\n"
            )
            with (
                patch.object(environment, "ROOT", root),
                patch.dict(os.environ, {"PG_CONN_STR": "exported"}, clear=True),
            ):
                self.assertEqual(
                    environment.state_environment()["PG_CONN_STR"], "exported"
                )

    def test_local_credentials_fill_only_missing_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.terraform.local").write_text(
                "VERCEL_API_TOKEN='from-file'\nNEON_API_KEY='neon-fixture'\n"
            )
            with (
                patch.object(environment, "ROOT", root),
                patch.dict(os.environ, {"VERCEL_API_TOKEN": "exported"}, clear=True),
            ):
                result = environment.terraform_environment()
                self.assertEqual(result["VERCEL_API_TOKEN"], "exported")
                self.assertEqual(result["NEON_API_KEY"], "neon-fixture")

    def test_invalid_credential_setting_does_not_disclose_value(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.terraform.local").write_text("UNKNOWN='private-fixture'\n")
            with (
                patch.object(environment, "ROOT", root),
                patch.dict(os.environ, {}, clear=True),
            ):
                with self.assertRaises(ValueError) as caught:
                    environment.terraform_environment()
                self.assertNotIn("private-fixture", str(caught.exception))

    def test_failed_outputs_do_not_disclose_stdout_or_stderr(self):
        result = subprocess.CompletedProcess([], 1, "private-output", "private-error")
        with patch.object(environment.subprocess, "run", return_value=result):
            with self.assertRaises(RuntimeError) as caught:
                environment.terraform_outputs(env={})
            self.assertNotIn("private-output", str(caught.exception))
            self.assertNotIn("private-error", str(caught.exception))

    def test_migration_rejects_application_role_and_unverified_tls(self):
        for uri in (
            "postgresql://syncnesto_app:fixture@ep-example.neon.tech/syncnesto?sslmode=verify-full",
            "postgresql://syncnesto_owner:fixture@ep-example.neon.tech/syncnesto?sslmode=require",
        ):
            with (
                self.subTest(uri=uri),
                patch.object(
                    environment,
                    "state_environment",
                    return_value={"PGSSLROOTCERT": "ca"},
                ),
                patch.object(
                    environment,
                    "terraform_outputs",
                    return_value={"migration_database_url": uri},
                ),
            ):
                with self.assertRaises(RuntimeError):
                    environment.backend_environment()

    def test_backend_operations_do_not_inherit_development_mail_settings(self):
        with (
            patch.object(
                environment,
                "state_environment",
                return_value={
                    "PGSSLROOTCERT": "ca",
                    "EMAIL_PROVIDER": "smtp",
                    "FRONTEND_PUBLIC_URL": "http://localhost:3000",
                    "DEMO_MODE": "true",
                },
            ),
            patch.object(
                environment,
                "terraform_outputs",
                return_value={
                    "migration_database_url": "postgresql://syncnesto_owner:fixture@ep-example.neon.tech/syncnesto?sslmode=verify-full",
                    "frontend_url": "https://syncnesto.vercel.app",
                    "backend_jwt_secret": "jwt-fixture",
                    "backend_bff_secret": "bff-fixture",
                },
            ),
        ):
            result = environment.backend_environment()
        self.assertEqual(result["EMAIL_PROVIDER"], "disabled")
        self.assertEqual(result["FRONTEND_PUBLIC_URL"], "https://syncnesto.vercel.app")
        self.assertEqual(result["APP_ENV"], "production")
        self.assertEqual(result["DEMO_MODE"], "false")


class TerraformTests(unittest.TestCase):
    def test_demo_runtime_inputs_are_added_without_replacing_normal_inputs(self):
        from tests.test_demo_operations import dedicated_outputs

        env = {
            "VERCEL_API_TOKEN": "fixture",
            "TF_VAR_demo_runtime_enabled": "true",
            "SUPABASE_S3_ACCESS_KEY_ID": "normal-access",
            "SUPABASE_S3_SECRET_ACCESS_KEY": "normal-secret",
        }
        dedicated_env = {
            **env,
            "DEMO_SUPABASE_PROJECT_REF": "jxtwcdmaooiasodubofu",
            "DEMO_SUPABASE_S3_ACCESS_KEY_ID": "demo-access",
            "DEMO_SUPABASE_S3_SECRET_ACCESS_KEY": "demo-secret",
        }
        with (
            patch.object(terraform, "terraform_environment", return_value=env),
            patch.object(
                terraform,
                "terraform_outputs",
                side_effect=[
                    {"vercel_backend_project_id": "prj_fixture"},
                    {"backend_database_url": "normal-db"},
                    {
                        "backend_database_url": "postgresql://syncnesto_app:fixture@ep-demo-pooler.neon.tech/syncnesto?sslmode=verify-full"
                    },
                ],
            ),
            patch("scripts.deploy.demo.demo_outputs", return_value=dedicated_outputs()),
            patch(
                "scripts.deploy.demo.storage_environment",
                side_effect=lambda current: {
                    **current,
                    **{
                        key: value
                        for key, value in dedicated_env.items()
                        if key.startswith("DEMO_SUPABASE_")
                    },
                },
            ),
            patch.object(terraform.subprocess, "call", return_value=0) as call,
            patch.object(sys, "argv", ["terraform", "runtime", "plan"]),
        ):
            self.assertEqual(terraform.main(), 0)
        forwarded = call.call_args.kwargs["env"]
        self.assertEqual(forwarded["TF_VAR_database_url"], "normal-db")
        self.assertEqual(forwarded["TF_VAR_storage_access_key"], "normal-access")
        self.assertEqual(forwarded["TF_VAR_storage_secret_key"], "normal-secret")
        self.assertIn("ep-demo-pooler", forwarded["TF_VAR_demo_database_url"])
        self.assertEqual(forwarded["TF_VAR_demo_storage_access_key"], "demo-access")
        self.assertNotIn("demo-secret", " ".join(call.call_args.args[0]))

    def test_runtime_credentials_are_forwarded_as_environment_only(self):
        env = {
            "VERCEL_API_TOKEN": "vercel-fixture",
            "SUPABASE_S3_ACCESS_KEY_ID": "access-fixture",
            "SUPABASE_S3_SECRET_ACCESS_KEY": "secret-fixture",
        }
        with (
            patch.object(terraform, "terraform_environment", return_value=env.copy()),
            patch.object(
                terraform,
                "terraform_outputs",
                side_effect=[
                    {"vercel_backend_project_id": "prj_fixture"},
                    {"backend_database_url": "db-fixture"},
                ],
            ),
            patch.object(terraform.subprocess, "call", return_value=0) as call,
            patch.object(sys, "argv", ["terraform", "runtime", "plan", "-input=false"]),
        ):
            self.assertEqual(terraform.main(), 0)
            forwarded = call.call_args.kwargs["env"]
            self.assertEqual(forwarded["TF_VAR_database_url"], "db-fixture")
            self.assertEqual(forwarded["TF_VAR_storage_secret_key"], "secret-fixture")
            self.assertNotIn("secret-fixture", " ".join(call.call_args.args[0]))

    def test_runtime_without_storage_keys_does_not_invoke_terraform(self):
        with (
            patch.object(
                terraform,
                "terraform_environment",
                return_value={"VERCEL_API_TOKEN": "fixture"},
            ),
            patch.object(
                terraform,
                "terraform_outputs",
                return_value={"vercel_backend_project_id": "prj_fixture"},
            ),
            patch.object(terraform.subprocess, "call") as call,
            patch.object(sys, "argv", ["terraform", "runtime", "apply"]),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(terraform.main(), 2)
            call.assert_not_called()

    def test_cli_preserves_terraform_flags(self):
        with (
            patch.object(
                sys,
                "argv",
                ["deploy", "terraform", "runtime", "plan", "-input=false"],
            ),
            patch("scripts.deploy.__main__.runpy.run_module") as run,
        ):
            dispatch()
            self.assertEqual(sys.argv[1:], ["runtime", "plan", "-input=false"])
            run.assert_called_once_with("scripts.deploy.terraform", run_name="__main__")


class CIGuardTests(unittest.TestCase):
    def run_ci(self, *, empty=False, destructive=False):
        env = {
            "PG_CONN_STR": "postgres://syncnesto_tfstate:fixture@ep-example.neon.tech/syncnesto_terraform?sslmode=verify-full",
            "VERCEL_API_TOKEN": "fixture",
            "NEON_API_KEY": "fixture",
            "SUPABASE_S3_ACCESS_KEY_ID": "fixture",
            "SUPABASE_S3_SECRET_ACCESS_KEY": "fixture",
        }

        def execute(args, *, env):
            if "pull" in args:
                return json.dumps({"resources": [] if empty else [{"type": "fixture"}]})
            if "show" in args:
                return json.dumps(
                    {
                        "resource_changes": [
                            {
                                "address": "fixture.resource",
                                "change": {
                                    "actions": ["delete", "create"]
                                    if destructive
                                    else ["no-op"]
                                },
                            }
                        ]
                    }
                )
            return ""

        with (
            patch.object(ci, "terraform_environment", return_value=env),
            patch.object(ci, "execute", side_effect=execute) as call,
            patch.object(sys, "argv", ["ci", "apply"]),
            patch.dict(os.environ, {}, clear=True),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            if empty or destructive:
                with self.assertRaises(RuntimeError):
                    ci.main()
                self.assertFalse(
                    any("apply" in item.args[0] for item in call.call_args_list)
                )
            else:
                self.assertEqual(ci.main(), 0)
                self.assertEqual(
                    sum("apply" in item.args[0] for item in call.call_args_list), 3
                )

    def test_actions_rejects_non_main_before_reading_secrets(self):
        with (
            patch.object(sys, "argv", ["ci", "apply"]),
            patch.dict(
                os.environ,
                {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/pull/1/merge"},
                clear=True,
            ),
            patch.object(ci, "terraform_environment") as env,
        ):
            with self.assertRaises(RuntimeError):
                ci.main()
            env.assert_not_called()

    def test_empty_state_refuses_apply(self):
        self.run_ci(empty=True)

    def test_replacement_refuses_apply(self):
        self.run_ci(destructive=True)

    def test_existing_non_destructive_state_applies_all_three_stacks(self):
        self.run_ci()


if __name__ == "__main__":
    unittest.main()
