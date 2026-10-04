"""Neonの専用DBへ管理接続でAlembic migrationだけを適用する。"""

import subprocess
import sys

from .environment import BACKEND, backend_environment


def main() -> int:
    """資格情報を表示せず、クラウド専用URIでmigrationを実行する。"""
    env = backend_environment()
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
    print("Neon migration completed. No local data or seed was copied.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, KeyError, OSError) as error:
        label = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print("Migration setup failed: " + label, file=sys.stderr)
        raise SystemExit(2) from None
