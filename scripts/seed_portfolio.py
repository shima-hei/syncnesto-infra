"""専用Neon DBにRBACと初期管理者を作成する。"""

import argparse
import json
import os
import secrets
import ssl
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT.parent / "syncnesto-backend"
CREDENTIALS = ROOT / ".env.portfolio-admin.local"


def main() -> int:
    """資格情報を所有者専用ファイルに保存し、既存seedを再利用する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    if "@" not in args.email or any(char in args.email for char in "\r\n'\""):
        print("Set a valid admin email.", file=sys.stderr)
        return 2
    if not CREDENTIALS.exists():
        password = secrets.token_urlsafe(32)
        fd = os.open(CREDENTIALS, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(
                f"INITIAL_ADMIN_EMAIL='{args.email}'\nINITIAL_ADMIN_PASSWORD='{password}'\n"
            )
    credentials = dotenv_values(CREDENTIALS)
    if credentials.get("INITIAL_ADMIN_EMAIL") != args.email or not credentials.get(
        "INITIAL_ADMIN_PASSWORD"
    ):
        print(
            "Existing credential file differs; refusing to overwrite it.",
            file=sys.stderr,
        )
        return 2
    result = subprocess.run(
        ["terraform", f"-chdir={ROOT / 'terraform' / 'portfolio'}", "output", "-json"],
        capture_output=True,
        text=True,
    )
    try:
        outputs = json.loads(result.stdout)
        uri = outputs["migration_database_url"]["value"]
        if ".neon.tech/" not in uri or not uri.endswith("?sslmode=verify-full"):
            raise ValueError
        env = os.environ.copy()
        env.update(
            {
                "DATABASE_URL": uri,
                "PGSSLROOTCERT": ssl.get_default_verify_paths().cafile or "",
                "APP_ENV": "production",
                "SECRET_KEY": outputs["backend_jwt_secret"]["value"],
                "BFF_SHARED_SECRET": outputs["backend_bff_secret"]["value"],
                "ALLOWED_HOSTS": "syncnesto-portfolio-api-shima-hei.vercel.app",
                "AUTH_COOKIE_SECURE": "true",
                "CSRF_COOKIE_SECURE": "true",
                "ALLOW_BEARER_TOKEN_RESPONSE": "false",
                "ALLOW_AUTHORIZATION_HEADER": "false",
                "SQL_ECHO": "false",
                "DEFAULT_AVATAR_KEY": "default-avatar.png",
                "INITIAL_ADMIN_EMAIL": args.email,
                "INITIAL_ADMIN_PASSWORD": credentials["INITIAL_ADMIN_PASSWORD"],
                "INITIAL_ADMIN_NAME": "Portfolio Admin",
            }
        )
    except (KeyError, TypeError, ValueError):
        print("Apply the portfolio database before seeding.", file=sys.stderr)
        return 2
    if not env["PGSSLROOTCERT"]:
        print("A trusted CA file is required.", file=sys.stderr)
        return 2
    result = subprocess.run(
        ["uv", "run", "python", "-m", "scripts.seed_rbac"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        print(
            "Portfolio seed failed; credentials remain saved for retry.",
            file=sys.stderr,
        )
        return result.returncode
    print(f"Portfolio admin created. Credentials saved only in {CREDENTIALS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
