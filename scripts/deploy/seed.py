"""専用Neon DBにRBACと初期管理者を作成する。"""

import argparse
import os
import secrets
import subprocess
import sys

from dotenv import dotenv_values

from .environment import BACKEND, ROOT, backend_environment

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
    try:
        env = backend_environment()
    except (KeyError, TypeError, ValueError, RuntimeError):
        print(
            "Apply the Neon database before seeding with verified TLS.",
            file=sys.stderr,
        )
        return 2
    env.update(
        {
            "DEFAULT_AVATAR_KEY": "default-avatar.png",
            "INITIAL_ADMIN_EMAIL": args.email,
            "INITIAL_ADMIN_PASSWORD": credentials["INITIAL_ADMIN_PASSWORD"],
            "INITIAL_ADMIN_NAME": "Syncnesto Admin",
        }
    )
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
    print(f"Initial admin created. Credentials saved only in {CREDENTIALS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
