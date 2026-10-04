"""共有stateの資格情報を引数・ログへ出さず、Terraformへ渡す。"""

import json
import os
import shlex
import ssl
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
VERCEL = ROOT / "terraform/vercel"
BACKEND = ROOT.parent / "syncnesto-backend"
BACKEND_ORIGIN = "https://syncnesto-api.vercel.app"
STACKS = {
    "vercel": VERCEL,
    "neon": ROOT / "terraform/neon",
    "runtime": VERCEL / "runtime",
}
TOKEN_KEYS = ("VERCEL_API_TOKEN", "NEON_API_KEY")


def state_environment() -> dict[str, str]:
    """export済みの値を優先し、ローカルの専用ファイルを補完する。"""
    env = os.environ.copy()
    credentials = ROOT / ".env.terraform-state.local"
    if credentials.exists() and not env.get("PG_CONN_STR"):
        for line in credentials.read_text().splitlines():
            if line.startswith("PG_CONN_STR="):
                values = shlex.split(line.partition("=")[2])
                if len(values) != 1:
                    raise ValueError("Invalid state credential file")
                env["PG_CONN_STR"] = values[0]
    ca_file = ssl.get_default_verify_paths().cafile
    if ca_file:
        env.setdefault("PGSSLROOTCERT", ca_file)
    return env


def terraform_environment() -> dict[str, str]:
    """クラウド操作用トークンを補完し、秘密をエラーへ含めない。"""
    env = state_environment()
    credentials = ROOT / ".env.terraform.local"
    if credentials.exists():
        for number, line in enumerate(credentials.read_text().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.removeprefix("export ").partition("=")
            if not separator or key.strip() not in TOKEN_KEYS:
                raise ValueError(f"Invalid credential setting at line {number}")
            try:
                parts = shlex.split(value, comments=True)
            except ValueError:
                raise ValueError(
                    f"Invalid credential quoting at line {number}"
                ) from None
            if len(parts) > 1:
                raise ValueError(f"Quote credential values at line {number}")
            env.setdefault(key.strip(), parts[0] if parts else "")
    return env


def terraform_outputs(
    stack: str = "vercel", *, env: dict[str, str] | None = None
) -> dict:
    """outputをメモリ内で取得し、失敗時の生ログを表示しない。"""
    if stack not in STACKS:
        raise ValueError("Unknown Terraform stack")
    result = subprocess.run(
        ["terraform", f"-chdir={STACKS[stack]}", "output", "-json"],
        capture_output=True,
        text=True,
        env=state_environment() if env is None else env,
    )
    if result.returncode:
        raise RuntimeError(f"Cannot read {stack} outputs; apply the stack first")
    try:
        return {key: item["value"] for key, item in json.loads(result.stdout).items()}
    except (ValueError, TypeError, KeyError, AttributeError):
        raise RuntimeError(
            "Invalid Terraform outputs; no raw logs were published"
        ) from None


def backend_environment() -> dict[str, str]:
    """migrationとseedに、同じ管理接続・TLS・本番設定を渡す。"""
    env = state_environment()
    outputs = terraform_outputs(env=env)
    uri = outputs["migration_database_url"]
    parsed = urlsplit(uri)
    if (
        parsed.username != "syncnesto_owner"
        or parsed.path != "/syncnesto"
        or not parsed.hostname
        or not parsed.hostname.endswith(".neon.tech")
        or "-pooler" in parsed.hostname
        or parse_qs(parsed.query).get("sslmode") != ["verify-full"]
    ):
        raise RuntimeError("Expected a verified direct Neon migration connection")
    if not env.get("PGSSLROOTCERT"):
        raise RuntimeError("Set PGSSLROOTCERT to a trusted CA bundle")
    env.update(
        {
            "DATABASE_URL": uri,
            "APP_ENV": "production",
            "SECRET_KEY": outputs["backend_jwt_secret"],
            "BFF_SHARED_SECRET": outputs["backend_bff_secret"],
            "ALLOWED_HOSTS": urlsplit(BACKEND_ORIGIN).hostname,
            "AUTH_COOKIE_SECURE": "true",
            "CSRF_COOKIE_SECURE": "true",
            "ALLOW_BEARER_TOKEN_RESPONSE": "false",
            "ALLOW_AUTHORIZATION_HEADER": "false",
            "SQL_ECHO": "false",
        }
    )
    return env
