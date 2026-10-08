"""共有stateを検証し、本番Terraformのplan/applyを順番に実行する。"""

import json
import os
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit

from .environment import DEMO_STACKS, STACKS, terraform_environment


def execute(args: list[str], *, env: dict[str, str]) -> str:
    """エラーにも資格情報が含まれる可能性があるため、生ログを公開しない。"""
    result = subprocess.run(args, env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Terraform command failed; no raw logs were published")
    return result.stdout


def main() -> int:
    """main用のCIから、既存stateだけを使って削除のないplanを適用する。"""
    os.umask(0o077)
    operation = sys.argv[1] if len(sys.argv) == 2 else ""
    if operation not in {"plan", "apply"}:
        raise ValueError("Select plan or apply")
    if (
        os.getenv("GITHUB_ACTIONS") == "true"
        and os.getenv("GITHUB_REF") != "refs/heads/main"
    ):
        raise RuntimeError("Production Terraform is restricted to main")
    env = terraform_environment()
    required = (
        "PG_CONN_STR",
        "VERCEL_API_TOKEN",
        "NEON_API_KEY",
        "SUPABASE_S3_ACCESS_KEY_ID",
        "SUPABASE_S3_SECRET_ACCESS_KEY",
    )
    if any(not env.get(key) for key in required):
        raise RuntimeError("Required production secrets are missing")
    parsed = urlsplit(env["PG_CONN_STR"])
    if (
        parsed.username != "syncnesto_tfstate"
        or parsed.path != "/syncnesto_terraform"
        or not parsed.hostname
        or not parsed.hostname.endswith(".neon.tech")
        or "-pooler" in parsed.hostname
        or parse_qs(parsed.query).get("sslmode") != ["verify-full"]
    ):
        raise RuntimeError("Expected verified direct connection to the state database")
    if env.get("TF_VAR_demo_runtime_enabled", "false").lower() == "true":
        # runtimeのoutput参照に必要。既存デモ資源のplan/applyは実行しない。
        for stack, directory in DEMO_STACKS.items():
            terraform = ["terraform", f"-chdir={directory}"]
            execute([*terraform, "init", "-input=false", "-lockfile=readonly"], env=env)
            state = json.loads(execute([*terraform, "state", "pull"], env=env))
            if not state.get("resources"):
                raise RuntimeError(
                    f"Existing {stack} state is required for demo runtime"
                )
    for stack, directory in STACKS.items():
        terraform = ["terraform", f"-chdir={directory}"]
        execute([*terraform, "init", "-input=false", "-lockfile=readonly"], env=env)
        state = json.loads(execute([*terraform, "state", "pull"], env=env))
        if not state.get("resources"):
            raise RuntimeError(
                "Shared state is empty; refusing a fresh production apply"
            )
        plan = directory / "ci.tfplan"
        helper = [sys.executable, "-m", "scripts.deploy", "terraform"]
        if stack:
            helper.append(stack)
        execute(
            [*helper, "plan", "-input=false", "-lock-timeout=120s", f"-out={plan}"],
            env=env,
        )
        content = json.loads(execute([*terraform, "show", "-json", str(plan)], env=env))
        changes = []
        for change in content.get("resource_changes", []):
            actions = change["change"]["actions"]
            if "delete" in actions:
                raise RuntimeError("Destructive plan refused; review manually")
            if actions != ["no-op"]:
                changes.append(change["address"] + ": " + ",".join(actions))
        print(f"{stack}: {len(changes)} resource changes")
        for change in changes:
            print("  " + change)
        if operation == "apply":
            execute(
                [*helper, "apply", "-input=false", "-lock-timeout=120s", str(plan)],
                env=env,
            )
            print(f"PASS: {stack} apply completed")
    print(
        "Production Terraform operation completed; state and plan were not uploaded as artifacts."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, KeyError) as error:
        label = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print("Production Terraform stopped: " + label, file=sys.stderr)
        raise SystemExit(1) from None
