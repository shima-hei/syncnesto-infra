"""共有stateのTLS・権限分離・Terraformのロック競合を実通信で確認する。"""

import subprocess
import sys
from urllib.parse import urlsplit

import psycopg2

from .environment import STACKS, state_environment, terraform_outputs


def main() -> int:
    """stateを変更せず、接続拒否とネイティブロックを確認する。"""
    env = state_environment()
    app = terraform_outputs("neon", env=env)["verification_connection"]
    state = psycopg2.connect(env["PG_CONN_STR"], sslrootcert=env["PGSSLROOTCERT"])
    state.autocommit = True
    try:
        if not state.info.ssl_in_use:
            raise RuntimeError("State connection has no TLS")
        with state.cursor() as cursor:
            cursor.execute(
                "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolinherit "
                "FROM pg_roles WHERE rolname=current_user"
            )
            if cursor.fetchone() != (False, False, False, False, False, False):
                raise RuntimeError("State role has excess privileges")
            cursor.execute("SELECT pg_has_role(current_user,'neon_superuser','MEMBER')")
            if cursor.fetchone() != (False,):
                raise RuntimeError("State role inherits management access")
            for schema in ("portfolio_state", "database_state", "runtime_state"):
                cursor.execute(
                    f"SELECT count(*) FROM {schema}.states WHERE name='default'"
                )
                if cursor.fetchone() != (1,):
                    raise RuntimeError("Shared state is incomplete")
        print("PASS: verified TLS, restricted state role and three shared states")
        try:
            unexpected = psycopg2.connect(
                host=app["host"],
                dbname="syncnesto_terraform",
                user=app["username"],
                password=app["password"],
                sslmode="verify-full",
                sslrootcert=env["PGSSLROOTCERT"],
                connect_timeout=15,
            )
        except psycopg2.Error as error:
            if error.pgcode != "42501" and "permission denied for database" not in str(
                error
            ):
                raise RuntimeError(
                    "Application connection failed for an unexpected reason"
                ) from None
        else:
            unexpected.close()
            raise RuntimeError("Application role could access the state database")
        try:
            unexpected = psycopg2.connect(
                env["PG_CONN_STR"],
                dbname="syncnesto",
                sslrootcert=env["PGSSLROOTCERT"],
                connect_timeout=15,
            )
        except psycopg2.Error as error:
            if error.pgcode != "42501" and "permission denied for database" not in str(
                error
            ):
                raise RuntimeError(
                    "State connection failed for an unexpected reason"
                ) from None
        else:
            unexpected.close()
            raise RuntimeError("State role could access the application database")
        print("PASS: application/state database access is separated")
        with state.cursor() as cursor:
            cursor.execute("SELECT id FROM portfolio_state.states WHERE name='default'")
            cursor.execute("SELECT pg_advisory_lock(%s)", (cursor.fetchone()[0],))
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.deploy",
                "terraform",
                "plan",
                "-input=false",
                "-lock-timeout=1s",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
        )
        if (
            result.returncode == 0
            or "state lock" not in (result.stdout + result.stderr).lower()
        ):
            raise RuntimeError("Terraform did not refuse a concurrent state lock")
        print(
            "PASS: Terraform rejected the concurrent state lock; session close releases it"
        )
        password = urlsplit(env["PG_CONN_STR"]).password
        for directory in STACKS.values():
            metadata = (directory / ".terraform/terraform.tfstate").read_text()
            if password in metadata or env["PG_CONN_STR"] in metadata:
                raise RuntimeError("State credential was persisted in backend metadata")
        print("PASS: state credentials absent from local backend metadata")
    finally:
        state.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, psycopg2.Error, subprocess.SubprocessError) as error:
        label = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print("Shared state verification failed: " + label, file=sys.stderr)
        raise SystemExit(1) from None
