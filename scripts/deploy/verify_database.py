"""Terraformで作成したNeonのTLS・認証・最小権限を実通信で検証する。"""

import ssl
from uuid import uuid4

import psycopg2
from psycopg2 import sql

from .environment import terraform_outputs


def connect(connection: dict, **overrides):
    """OSのCAで証明書とホスト名を検証して接続する。"""
    arguments = {
        "host": connection["host"],
        "dbname": connection["database"],
        "user": connection["username"],
        "password": connection["password"],
        "sslmode": "verify-full",
        "sslrootcert": ssl.get_default_verify_paths().cafile,
        "connect_timeout": 15,
    }
    arguments.update(overrides)
    result = psycopg2.connect(**arguments)
    result.autocommit = True
    return result


def main() -> None:
    """専用の検証テーブルだけを操作し、最後に削除する。"""
    owner = terraform_outputs()["database_admin_connection"]
    application = terraform_outputs("neon")["verification_connection"]
    assert owner["host"] == application["host"]
    assert owner["database"] == application["database"]
    assert owner["username"] != application["username"]
    probe = "security_probe_" + uuid4().hex
    admin = connect(owner)
    app = connect(application)
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "CREATE TABLE public.{} (id serial PRIMARY KEY, body text)"
                ).format(sql.Identifier(probe))
            )
        with app.cursor() as cursor:
            # Neon ProxyでTLSを終端するため、クライアントのlibpqで確認する。
            assert app.info.ssl_in_use
            cursor.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, "
                "rolbypassrls, rolinherit FROM pg_roles WHERE rolname = current_user"
            )
            assert cursor.fetchone() == (False, False, False, False, False, False)
            cursor.execute(
                "SELECT pg_has_role(current_user, 'neon_superuser', 'MEMBER')"
            )
            assert cursor.fetchone() == (False,)
            table = sql.Identifier("public", probe)
            cursor.execute(
                sql.SQL("INSERT INTO {} (body) VALUES ('probe') RETURNING id").format(
                    table
                )
            )
            row_id = cursor.fetchone()[0]
            cursor.execute(
                sql.SQL("SELECT body FROM {} WHERE id = %s").format(table), (row_id,)
            )
            assert cursor.fetchone() == ("probe",)
            cursor.execute(
                sql.SQL("UPDATE {} SET body = 'updated' WHERE id = %s").format(table),
                (row_id,),
            )
            assert cursor.rowcount == 1
            cursor.execute(
                sql.SQL("DELETE FROM {} WHERE id = %s").format(table), (row_id,)
            )
            assert cursor.rowcount == 1
            print(
                "PASS: verified TLS, non-admin role, future-table CRUD "
                "and sequence access"
            )

            pooled = connect(application, host=owner["pooled_host"])
            try:
                assert pooled.info.ssl_in_use
                with pooled.cursor() as pooled_cursor:
                    pooled_cursor.execute("SELECT current_user")
                    assert pooled_cursor.fetchone() == (application["username"],)
                    pooled_cursor.execute(
                        sql.SQL("SELECT count(*) FROM {}").format(table)
                    )
                    assert pooled_cursor.fetchone() == (0,)
                print("PASS: runtime pooler uses the restricted role with verified TLS")
            finally:
                pooled.close()

            denied_statements = {
                "create table": sql.SQL("CREATE TABLE public.{} (id int)").format(
                    sql.Identifier(probe + "_extra")
                ),
                "create role": sql.SQL("CREATE ROLE {}").format(sql.Identifier(probe)),
                "create database": sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(probe)
                ),
                "drop owner table": sql.SQL("DROP TABLE {}").format(table),
            }
            for label, statement in denied_statements.items():
                try:
                    cursor.execute(statement)
                except psycopg2.Error as error:
                    assert error.pgcode == "42501", f"Unexpected SQLSTATE for {label}"
                    print(f"PASS: {label} rejected with insufficient_privilege")
                else:
                    raise AssertionError(f"Application could {label}")

        denied_connections = [
            ("wrong password", {"password": "invalid-" + uuid4().hex}, "password"),
            ("unencrypted connection", {"sslmode": "disable"}, "insecure"),
            (
                "missing CA bundle",
                {"sslrootcert": "/nonexistent/security-probe-ca.pem"},
                "certificate",
            ),
        ]
        for label, overrides, expected_reason in denied_connections:
            try:
                unexpected = connect(application, **overrides)
            except psycopg2.OperationalError as error:
                assert expected_reason in str(error).lower(), (
                    f"Unexpected failure for {label}"
                )
                print(f"PASS: {label} rejected")
            else:
                unexpected.close()
                raise AssertionError(f"Accepted {label}")
    finally:
        app.close()
        with admin.cursor() as cursor:
            for name in (probe, probe + "_extra"):
                cursor.execute(
                    sql.SQL("DROP TABLE IF EXISTS public.{}").format(
                        sql.Identifier(name)
                    )
                )
            cursor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(probe))
            )
            cursor.execute(
                sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(probe))
            )
        admin.close()
    print("PASS: probe objects cleaned up; credentials were not printed")


if __name__ == "__main__":
    main()
