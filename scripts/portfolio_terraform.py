"""公開環境のTerraformに実行用トークンを渡す。"""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN_KEYS = ("VERCEL_API_TOKEN", "NEON_API_KEY")


def main() -> int:
    """export済みの値を優先し、未設定の値を専用ファイルから読む。"""
    os.umask(0o077)
    args = sys.argv[1:]
    database_stack = bool(args and args[0] == "database")
    if database_stack:
        args = args[1:]
    if not args:
        print(
            "Usage: portfolio_terraform.py <terraform command> [arguments]",
            file=sys.stderr,
        )
        return 2

    env = os.environ.copy()
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
        missing = [key for key in TOKEN_KEYS if not env.get(key)]
        if missing:
            print(
                "Missing Terraform credentials: "
                + ", ".join(missing)
                + ". Export them or set .env.terraform.local.",
                file=sys.stderr,
            )
            return 2

    if remote_command and database_stack:
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
            connection = json.loads(result.stdout)["database_admin_connection"]["value"]
        except (KeyError, ValueError, TypeError):
            print(
                "The portfolio stack has no database admin connection yet.",
                file=sys.stderr,
            )
            return 2
        for target, source in {
            "database_host": "host",
            "pooled_host": "pooled_host",
            "database_name": "database",
            "database_owner": "username",
            "database_owner_password": "password",
        }.items():
            env[f"TF_VAR_{target}"] = connection[source]

    directory = ROOT / "terraform" / "portfolio"
    if database_stack:
        directory /= "database"

    return subprocess.call(["terraform", f"-chdir={directory}", *args], env=env)


if __name__ == "__main__":
    raise SystemExit(main())
