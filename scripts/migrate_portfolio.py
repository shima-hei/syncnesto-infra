"""Neonの専用DBへ管理接続でAlembic migrationだけを適用する。"""

import json
import os
import ssl
import subprocess
import sys
from pathlib import Path

from state_environment import state_environment

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT.parent / "syncnesto-backend"


def main() -> int:
    """資格情報を表示せず、クラウド専用URIでmigrationを実行する。"""
    result = subprocess.run(
        ["terraform", f"-chdir={ROOT / 'terraform' / 'portfolio'}", "output", "-json"],
        capture_output=True,
        text=True,
        env=state_environment(),
    )
    try:
        outputs = json.loads(result.stdout)
        uri = outputs["migration_database_url"]["value"]
        secret = outputs["backend_jwt_secret"]["value"]
        bff_secret = outputs["backend_bff_secret"]["value"]
    except (KeyError, ValueError, TypeError):
        print("Apply the portfolio stack first.", file=sys.stderr)
        return 2
    if ".neon.tech/" not in uri or not uri.endswith("?sslmode=verify-full"):
        print(
            "Refusing migration: expected a verified Neon connection.", file=sys.stderr
        )
        return 2
    ca_file = os.getenv("PGSSLROOTCERT") or ssl.get_default_verify_paths().cafile
    if not ca_file:
        print("Set PGSSLROOTCERT to a trusted CA bundle.", file=sys.stderr)
        return 2
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": uri,
            "PGSSLROOTCERT": ca_file,
            "APP_ENV": "production",
            "SECRET_KEY": secret,
            "BFF_SHARED_SECRET": bff_secret,
            "ALLOWED_HOSTS": "syncnesto-portfolio-api.vercel.app",
            "AUTH_COOKIE_SECURE": "true",
            "CSRF_COOKIE_SECURE": "true",
            "ALLOW_BEARER_TOKEN_RESPONSE": "false",
            "ALLOW_AUTHORIZATION_HEADER": "false",
            "SQL_ECHO": "false",
        }
    )
    # 例外やDBエラーにURIが含まれる可能性があるため、生ログは表示しない。
    migration = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    if migration.returncode:
        print(
            "Migration failed; inspect the database schema before retrying.",
            file=sys.stderr,
        )
        return migration.returncode
    print("Portfolio Neon migration completed. No local data or seed was copied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
