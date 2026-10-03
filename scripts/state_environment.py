"""共有stateの資格情報を引数・ログへ出さず、Terraformへ渡す。"""

import os
import shlex
import ssl
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
