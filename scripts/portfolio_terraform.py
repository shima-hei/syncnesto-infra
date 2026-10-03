"""公開環境のTerraformに実行用トークンを渡す。"""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from state_environment import state_environment

ROOT = Path(__file__).resolve().parents[1]
TOKEN_KEYS = ("VERCEL_API_TOKEN", "NEON_API_KEY")


def main() -> int:
    """export済みの値を優先し、未設定の値を専用ファイルから読む。"""
    os.umask(0o077)
    args = sys.argv[1:]
    stack = args.pop(0) if args and args[0] in {"database", "runtime"} else ""
    database_stack = stack == "database"
    runtime_stack = stack == "runtime"
    if not args:
        print(
            "Usage: portfolio_terraform.py <terraform command> [arguments]",
            file=sys.stderr,
        )
        return 2

    env = state_environment()
    credentials = ROOT / ".env.terraform.local"
    if credentials.exists():
        for number, line in enumerate(credentials.read_text().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.removeprefix("export ").partition("=")
            if not separator or key.strip() not in TOKEN_KEYS:
                print(f"Invalid credential setting at line {number}.", file=sys.stderr)
                return 2
            try:
                parts = shlex.split(value, comments=True)
            except ValueError:
                print(f"Invalid credential quoting at line {number}.", file=sys.stderr)
                return 2
            if len(parts) > 1:
                print(
                    f"Quote credential values containing spaces at line {number}.",
                    file=sys.stderr,
                )
                return 2
            env.setdefault(key.strip(), parts[0] if parts else "")

    remote_command = args[0] in {"plan", "apply", "import", "refresh", "destroy"}
    if remote_command and not database_stack:
        required = ("VERCEL_API_TOKEN",) if runtime_stack else TOKEN_KEYS
        missing = [key for key in required if not env.get(key)]
        if missing:
            print(
                "Missing Terraform credentials: "
                + ", ".join(missing)
                + ". Export them or set .env.terraform.local.",
                file=sys.stderr,
            )
            return 2

    if remote_command and (database_stack or runtime_stack):
        result = subprocess.run(
            [
                "terraform",
                f"-chdir={ROOT / 'terraform' / 'portfolio'}",
                "output",
                "-json",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode:
            print(
                "Apply the portfolio stack before configuring database privileges.",
                file=sys.stderr,
            )
            return 2
        try:
            outputs = json.loads(result.stdout)
            connection = outputs["database_admin_connection"]["value"]
        except (KeyError, ValueError, TypeError):
            print(
                "The portfolio stack has no database admin connection yet.",
                file=sys.stderr,
            )
            return 2
        if database_stack:
            for target, source in {
                "database_host": "host",
                "pooled_host": "pooled_host",
                "database_name": "database",
                "database_owner": "username",
                "database_owner_password": "password",
            }.items():
                env[f"TF_VAR_{target}"] = connection[source]

        if runtime_stack:
            required = ("SUPABASE_S3_ACCESS_KEY_ID", "SUPABASE_S3_SECRET_ACCESS_KEY")
            missing = [key for key in required if not env.get(key)]
            if missing:
                print(
                    "Missing storage credentials: " + ", ".join(missing),
                    file=sys.stderr,
                )
                return 2
            result = subprocess.run(
                [
                    "terraform",
                    f"-chdir={ROOT / 'terraform' / 'portfolio' / 'database'}",
                    "output",
                    "-json",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            try:
                database_outputs = json.loads(result.stdout)
                env["TF_VAR_database_url"] = database_outputs["backend_database_url"][
                    "value"
                ]
                env["TF_VAR_backend_project_id"] = outputs["vercel_backend_project_id"][
                    "value"
                ]
            except (KeyError, ValueError, TypeError):
                print(
                    "Apply the database and backend stacks before runtime configuration.",
                    file=sys.stderr,
                )
                return 2
            env["TF_VAR_storage_access_key"] = env[required[0]]
            env["TF_VAR_storage_secret_key"] = env[required[1]]

    directory = ROOT / "terraform" / "portfolio"
    if stack:
        directory /= stack

    return subprocess.call(["terraform", f"-chdir={directory}", *args], env=env)


if __name__ == "__main__":
    raise SystemExit(main())
