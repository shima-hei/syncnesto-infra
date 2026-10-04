"""検証済みの管理接続でDefault Tenantの指定Ownerを初期化する。"""

import argparse
import subprocess
import sys
from pathlib import Path

from .environment import BACKEND, backend_environment


def main() -> int:
    """資格情報をログへ出さず、RBACと明示された初期Ownerを設定する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password-file", type=Path)
    args = parser.parse_args()
    if args.password_file is not None:
        if (
            not args.password_file.is_file()
            or args.password_file.stat().st_mode & 0o077
        ):
            print("Use an owner-only password file (mode 0600).", file=sys.stderr)
            return 2
    env = backend_environment()
    commands = [
        [
            "uv",
            "run",
            "python",
            "-c",
            "from scripts.seed_rbac import seed_roles_and_permissions; from app.repositories.rbac import RbacRepository; seed_roles_and_permissions(RbacRepository())",
        ],
        [
            "uv",
            "run",
            "python",
            "-m",
            "scripts.bootstrap_tenant_owner",
            "--email",
            args.email,
        ],
    ]
    if args.password_file is not None:
        commands[1].extend(["--password-file", str(args.password_file.resolve())])
    for command in commands:
        result = subprocess.run(
            command, cwd=BACKEND, env=env, capture_output=True, text=True
        )
        if result.returncode:
            print(
                "Tenant initialization failed; credentials were not logged. Inspect membership before retrying.",
                file=sys.stderr,
            )
            return result.returncode
    print("Default Tenant owner initialized. Project memberships were preserved.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, KeyError, OSError):
        print(
            "Tenant initialization setup failed; no raw credentials were published.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
