"""通常環境を拒否し、デモ専用資源の初期化・検証・回収を行う。"""

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit

from dotenv import dotenv_values

from . import storage, verify_database
from .environment import (
    BACKEND,
    BACKEND_ORIGIN,
    ROOT,
    state_environment,
    terraform_outputs,
)

SUPABASE_ORGANIZATION = "yxsnqlgubcohdavdcpry"
STORAGE_KEYS = (
    "DEMO_SUPABASE_PROJECT_REF",
    "DEMO_SUPABASE_S3_ACCESS_KEY_ID",
    "DEMO_SUPABASE_S3_SECRET_ACCESS_KEY",
)
MANAGEMENT_TOKEN = "DEMO_SUPABASE_ACCESS_TOKEN"


def demo_outputs(env: dict[str, str]) -> dict:
    """専用stateを読み、通常Project・host・別DBへの誤接続を拒否する。"""
    original = terraform_outputs(env=env)
    demo = terraform_outputs("demo", env=env)
    owner = demo["database_admin_connection"]
    original_owner = original["database_admin_connection"]
    direct = owner["host"]
    prefix, separator, suffix = direct.partition(".")
    uri = urlsplit(demo["migration_database_url"])
    if (
        not demo.get("neon_project_id")
        or demo["neon_project_id"] == original["neon_project_id"]
        or not demo.get("neon_branch_id")
        or direct == original_owner["host"]
        or owner["pooled_host"] == original_owner["pooled_host"]
        or not separator
        or not direct.endswith(".neon.tech")
        or "-pooler" in direct
        or owner["pooled_host"] != f"{prefix}-pooler.{suffix}"
        or owner["database"] != "syncnesto"
        or owner["username"] != "syncnesto_owner"
        or uri.scheme != "postgresql"
        or uri.hostname != direct
        or uri.username != owner["username"]
        or uri.path != "/syncnesto"
        or parse_qs(uri.query).get("sslmode") != ["verify-full"]
    ):
        raise RuntimeError("Dedicated demo project and verified connections required")
    return demo


def restricted_runtime_uri(dedicated: dict, database: dict) -> str:
    """専用stateでも通常hostやowner URIが混ざれば公開設定へ渡さない。"""
    uri = database["backend_database_url"]
    parsed = urlsplit(uri)
    if (
        parsed.hostname != dedicated["database_admin_connection"]["pooled_host"]
        or parsed.username != "syncnesto_app"
        or parsed.path != "/syncnesto"
        or parsed.scheme != "postgresql"
        or parsed.query != "sslmode=verify-full"
    ):
        raise RuntimeError("Expected the dedicated demo restricted pooler URI")
    return uri


def storage_environment(env: dict[str, str]) -> dict[str, str]:
    """デモ専用キーだけを補完し、通常キーの暗黙利用を防ぐ。"""
    result = env.copy()
    path = ROOT / ".env.demo.local"
    if path.exists():
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise RuntimeError("Demo credential file must be owner-only (chmod 600)")
        values = dotenv_values(path)
        if set(values) - {*STORAGE_KEYS, MANAGEMENT_TOKEN}:
            raise RuntimeError("Unexpected setting in demo credential file")
        for key, value in values.items():
            if value is not None:
                result.setdefault(key, value)
    if any(not result.get(key) for key in STORAGE_KEYS):
        raise RuntimeError("Set the dedicated demo Supabase reference and S3 keys")
    ref = result[STORAGE_KEYS[0]]
    if not re.fullmatch(r"[a-z]{20}", ref) or ref == storage.PROJECT:
        raise RuntimeError("Use a separate Supabase project for demo storage")
    for demo_key, original_key in zip(
        STORAGE_KEYS[1:],
        ("SUPABASE_S3_ACCESS_KEY_ID", "SUPABASE_S3_SECRET_ACCESS_KEY"),
        strict=True,
    ):
        if result.get(original_key) == result[demo_key]:
            raise RuntimeError("Demo must not reuse the portfolio storage credentials")
    return result


def management_token(env: dict[str, str]) -> str:
    """専用のscoped PATを優先し、既存トークンを変更せずに準備する。"""
    token = env.get(MANAGEMENT_TOKEN) or env.get("SUPABASE_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Set a management token scoped to the demo project")
    return token


def storage_target(env: dict[str, str]) -> storage.StorageTarget:
    """承認した配置のprivate bucketだけを操作する。"""
    return storage.StorageTarget(
        project=env[STORAGE_KEYS[0]],
        bucket="syncnesto-demo",
        origin="https://syncnesto.vercel.app",
        max_bytes=5 * 1024 * 1024,
    )


def backend_environment(*, with_storage: bool = False) -> dict[str, str]:
    """デモ受付を起動せず、専用DBをdirect接続で扱う。"""
    env = state_environment()
    demo = demo_outputs(env)
    if not env.get("PGSSLROOTCERT"):
        raise RuntimeError("Set PGSSLROOTCERT to a trusted CA bundle")
    # 運用コマンドが通常環境の資格情報を誤って利用しないよう除く。
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        env[key] = ""
    env.update(
        {
            "DATABASE_URL": demo["migration_database_url"],
            "APP_ENV": "production",
            "DEMO_MODE": "false",
            "DEMO_DATA_ISOLATED": "true",
            "DELETED_DATA_CLEANUP_MODE": "disabled",
            "EMAIL_PROVIDER": "disabled",
            "FRONTEND_PUBLIC_URL": "https://syncnesto.vercel.app",
            "SECRET_KEY": demo["backend_jwt_secret"],
            "BFF_SHARED_SECRET": demo["backend_bff_secret"],
            "CRON_SECRET": demo["backend_cron_secret"],
            "ALLOWED_HOSTS": urlsplit(BACKEND_ORIGIN).hostname,
            "AUTH_COOKIE_SECURE": "true",
            "CSRF_COOKIE_SECURE": "true",
            "ALLOW_BEARER_TOKEN_RESPONSE": "false",
            "ALLOW_AUTHORIZATION_HEADER": "false",
            "SQL_ECHO": "false",
            "DEFAULT_AVATAR_KEY": "default-avatar.png",
            "AWS_EC2_METADATA_DISABLED": "true",
        }
    )
    if with_storage:
        env = storage_environment(env)
        target = storage_target(env)
        env.update(
            {
                # 回収だけを実行するprocess。通常接続を使った場合は必ず接続不能。
                "DATABASE_URL": "postgresql://unused:unused@unused.invalid/unused?sslmode=verify-full",
                "DEMO_DATABASE_URL": demo["migration_database_url"],
                "DEMO_SECRET_KEY": demo["backend_jwt_secret"],
                "DEMO_AWS_ACCESS_KEY_ID": env[STORAGE_KEYS[1]],
                "DEMO_AWS_SECRET_ACCESS_KEY": env[STORAGE_KEYS[2]],
                "DEMO_AWS_REGION": target.region,
                "DEMO_AWS_S3_BUCKET_NAME": target.bucket,
                "DEMO_AWS_S3_ENDPOINT_URL": target.endpoint,
                "FILE_UPLOAD_MODE": "presigned",
            }
        )
    return env


def run_backend(
    arguments: list[str], env: dict[str, str], *, cleanup: bool = False
) -> int:
    """秘密が混入し得るsubprocessの生ログを表示しない。"""
    child_env = {
        key: value
        for key, value in env.items()
        if key
        not in {
            "PG_CONN_STR",
            "VERCEL_API_TOKEN",
            "NEON_API_KEY",
            "SUPABASE_ACCESS_TOKEN",
        }
        and not key.startswith(("TF_VAR_", "DEMO_SUPABASE_", "SUPABASE_S3_"))
    }
    result = subprocess.run(
        ["uv", "run", *arguments],
        cwd=BACKEND,
        env=child_env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError("Demo operation failed; raw logs were withheld")
    if cleanup:
        data = json.loads(result.stdout)
        if (
            set(data) != {"processed", "pending", "remaining", "execute", "limit"}
            or data["limit"] != 10
            or type(data["execute"]) is not bool
            or type(data["remaining"]) is not int
            or data["remaining"] < 0
            or any(
                type(data[key]) is not int or not 0 <= data[key] <= 10
                for key in ("processed", "pending")
            )
        ):
            raise RuntimeError("Invalid demo cleanup summary; raw logs were withheld")
        print(
            f"Demo cleanup: execute={data['execute']}, processed={data['processed']}, "
            f"pending={data['pending']}, remaining={data['remaining']} (limit=10)"
        )
    else:
        print("PASS: dedicated demo operation completed")
    return 0


def empty_database(owner: dict) -> None:
    """初期化専用seedを、Identityや業務データがない段階だけに限定する。"""
    connection = verify_database.connect(owner)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT (SELECT count(*) FROM users), "
                "(SELECT count(*) FROM projects), "
                "(SELECT count(*) FROM demo_sessions)"
            )
            if cursor.fetchone() != (0, 0, 0):
                raise RuntimeError("Demo seed requires an empty application database")
    finally:
        connection.close()


def verify_storage(env: dict[str, str], target: storage.StorageTarget):
    """管理情報とS3認証を読み取りで確認し、書込前にProjectの所属を確定する。"""
    status, _, body = storage.request(
        f"https://api.supabase.com/v1/projects/{target.project}",
        headers={"Authorization": "Bearer " + management_token(env)},
    )
    if status != 200:
        raise RuntimeError("Cannot verify the demo storage project organization")
    project = json.loads(body)
    if (
        project.get("id") != target.project
        or project.get("organization_id") != SUPABASE_ORGANIZATION
        or project.get("name") != "syncnesto-demo"
        or project.get("region") != target.region
        or project.get("status") != "ACTIVE_HEALTHY"
    ):
        raise RuntimeError("Storage project must match the approved demo placement")
    client = storage.s3_client(
        target, access_key=env[STORAGE_KEYS[1]], secret_key=env[STORAGE_KEYS[2]]
    )
    # このendpointで成功することを確かめ、別Projectのキーを拒否する。
    client.list_buckets()
    return client


def main() -> int:
    """コマンドとstateで操作先を固定し、Vercelの公開設定には書き込まない。"""
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("migrate", "seed", "verify-database"):
        subcommands.add_parser(command)
    cleanup = subcommands.add_parser("cleanup")
    cleanup.add_argument("--execute", action="store_true")
    bucket = subcommands.add_parser("storage")
    bucket.add_argument("operation", choices=("prepare", "verify"))
    args = parser.parse_args()
    try:
        if args.command == "storage":
            env = storage_environment(state_environment())
            target = storage_target(env)
            client = verify_storage(env, target)
            if args.operation == "prepare":
                storage.prepare(client, target, management_token=management_token(env))
            else:
                storage.verify(client, target)
            return 0
        env = backend_environment(with_storage=args.command == "cleanup")
        if args.command == "migrate":
            return run_backend(["alembic", "upgrade", "head"], env)
        if args.command == "cleanup":
            arguments = ["python", "-m", "scripts.cleanup_demo", "--json"]
            if args.execute:
                arguments.append("--execute")
            return run_backend(arguments, env, cleanup=True)
        demo = demo_outputs(env)
        owner = demo["database_admin_connection"]
        if args.command == "seed":
            empty_database(owner)
            return run_backend(
                ["python", "-m", "scripts.seed_rbac", "--roles-only"], env
            )
        application = terraform_outputs("demo-neon", env=env)["verification_connection"]
        if (
            application["host"] != owner["host"]
            or application["database"] != "syncnesto"
            or application["username"] != "syncnesto_app"
        ):
            raise RuntimeError(
                "Demo runtime role must belong to the dedicated database"
            )
        verify_database.verify(owner, application)
        return 0
    except Exception:
        # 接続URI・署名URL・管理API本文をエラーに含めない。
        print(
            "Demo operation failed; verify dedicated configuration and retry.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
