"""既存Neonにstate専用DBを準備し、バックアップ後にlocal stateを移行する。"""

import json
import os
import secrets
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import psycopg2
from psycopg2 import sql

from state_environment import state_environment

ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO = ROOT / "terraform/portfolio"
ROLE = "syncnesto_tfstate"
DATABASE = "syncnesto_terraform"
SCHEMAS = {
    "": "portfolio_state",
    "database": "database_state",
    "runtime": "runtime_state",
}


def main() -> int:
    """専用DB・ロールの作成と、既存3構成の移行を行う。"""
    os.umask(0o077)
    env = state_environment()
    local_state = PORTFOLIO / "terraform.tfstate"
    metadata = json.loads((PORTFOLIO / ".terraform/terraform.tfstate").read_text())
    if metadata.get("backend", {}).get("type") == "pg":
        result = subprocess.run(
            ["terraform", f"-chdir={PORTFOLIO}", "state", "pull"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        initial = json.loads(result.stdout)
    else:
        initial = json.loads(local_state.read_text())
    owner = initial["outputs"]["database_admin_connection"]["value"]
    credentials = ROOT / ".env.terraform-state.local"
    if not credentials.exists():
        password = secrets.token_urlsafe(48)
        uri = (
            f"postgres://{ROLE}:{quote(password, safe='')}@{owner['host']}/{DATABASE}"
            "?sslmode=verify-full"
        )
        fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(f"PG_CONN_STR='{uri}'\n")
    env = state_environment()
    from urllib.parse import urlsplit

    parsed = urlsplit(env["PG_CONN_STR"])
    if parsed.username != ROLE or parsed.path != f"/{DATABASE}":
        raise ValueError("Unexpected state database credentials")
    connection = psycopg2.connect(
        host=owner["host"],
        dbname=owner["database"],
        user=owner["username"],
        password=owner["password"],
        sslmode="verify-full",
        sslrootcert=env["PGSSLROOTCERT"],
        connect_timeout=20,
    )
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,))
            if not cursor.fetchone():
                cursor.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB "
                        "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 10"
                    ).format(sql.Identifier(ROLE), sql.Literal(parsed.password))
                )
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DATABASE,))
            if not cursor.fetchone():
                cursor.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DATABASE))
                )
            cursor.execute(
                sql.SQL("GRANT CONNECT, CREATE ON DATABASE {} TO {}").format(
                    sql.Identifier(DATABASE), sql.Identifier(ROLE)
                )
            )
            cursor.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(DATABASE)
                )
            )
            cursor.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(
                    sql.Identifier(owner["database"]), sql.Identifier(ROLE)
                )
            )
    finally:
        connection.close()
    state_db = psycopg2.connect(
        host=owner["host"],
        dbname=DATABASE,
        user=owner["username"],
        password=owner["password"],
        sslmode="verify-full",
        sslrootcert=env["PGSSLROOTCERT"],
        connect_timeout=20,
    )
    state_db.autocommit = True
    with state_db.cursor() as cursor:
        cursor.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
        # pg backendはstate IDの共通sequenceだけpublic schemaに作る。
        cursor.execute(
            sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(
                sql.Identifier(ROLE)
            )
        )
    state_db.close()
    backup = ROOT / "state-backups" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup.mkdir(parents=True, mode=0o700)
    for stack in SCHEMAS:
        directory = PORTFOLIO / stack
        metadata_file = directory / ".terraform/terraform.tfstate"
        metadata = (
            json.loads(metadata_file.read_text()) if metadata_file.exists() else {}
        )
        if metadata.get("backend", {}).get("type") == "pg":
            result = subprocess.run(
                ["terraform", f"-chdir={directory}", "state", "pull"],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            state = json.loads(result.stdout)
            if not state.get("resources"):
                raise RuntimeError("Existing remote state is empty; refusing migration")
            (backup / f"{stack or 'portfolio'}.tfstate").write_text(result.stdout)
            print(f"PASS: {stack or 'portfolio'} already uses nonempty shared state")
            continue
        local = directory / "terraform.tfstate"
        if not local.exists():
            raise RuntimeError(
                "Expected existing local state; refusing fresh bootstrap"
            )
        source = json.loads(local.read_text())
        shutil.copy2(local, backup / f"{stack or 'portfolio'}.tfstate")
        result = subprocess.run(
            [
                "terraform",
                f"-chdir={directory}",
                "init",
                "-migrate-state",
                "-force-copy",
                "-input=false",
                "-lockfile=readonly",
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(f"State migration failed for {stack or 'portfolio'}")
        migrated = subprocess.run(
            ["terraform", f"-chdir={directory}", "state", "pull"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        target = json.loads(migrated.stdout)
        # pg backendへの移行でlineage/serialは作り直される。内容を比較する。
        if source.get("resources") != target.get("resources") or source.get(
            "outputs"
        ) != target.get("outputs"):
            raise RuntimeError("Migrated state differs from the backup")
        print(f"PASS: {stack or 'portfolio'} state migrated without resource changes")
    print("Shared state prepared. Local backups and credentials are Git-ignored.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ValueError,
        KeyError,
        RuntimeError,
        psycopg2.Error,
        subprocess.CalledProcessError,
        OSError,
    ) as error:
        label = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print("Shared state setup failed: " + label, file=sys.stderr)
        raise SystemExit(1) from None
