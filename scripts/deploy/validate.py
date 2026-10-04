"""ローカルのstateや資格情報を使わずTerraform構成を検証する。"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .environment import ROOT, STACKS


def main() -> int:
    """構成とlockだけを一時ディレクトリへコピーして検証する。"""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("TF_VAR_", "PG_", "VERCEL_", "NEON_", "SUPABASE_"))
        and key not in {"TF_DATA_DIR", "TF_WORKSPACE"}
    }
    with tempfile.TemporaryDirectory(prefix="syncnesto-terraform-check-") as directory:
        for name, source in {
            "localstack": ROOT / "terraform/localstack",
            **STACKS,
        }.items():
            target = Path(directory) / name
            target.mkdir()
            for path in (*source.glob("*.tf"), source / ".terraform.lock.hcl"):
                shutil.copy2(path, target / path.name)
            if (source / "tests").exists():
                shutil.copytree(source / "tests", target / "tests")
            for command in (
                ["init", "-backend=false", "-input=false", "-lockfile=readonly"],
                ["validate"],
                ["test"],
            ):
                result = subprocess.run(
                    ["terraform", f"-chdir={target}", *command], env=env
                )
                if result.returncode:
                    return result.returncode
            print(f"PASS: {name} validation completed without production state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
