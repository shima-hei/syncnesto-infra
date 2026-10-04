"""公開環境のTerraformに実行用トークンを渡す。"""

import os
import subprocess
import sys

from .environment import STACKS, TOKEN_KEYS, terraform_environment, terraform_outputs


def main() -> int:
    """各stackに必要な資格情報だけを環境変数として渡す。"""
    os.umask(0o077)
    args = sys.argv[1:]
    stack = args.pop(0) if args and args[0] in STACKS else "vercel"
    if not args:
        print(
            "Usage: python -m scripts.deploy terraform [vercel|neon|runtime] <command> [arguments]",
            file=sys.stderr,
        )
        return 2

    env = terraform_environment()
    remote_command = args[0] in {"plan", "apply", "import", "refresh", "destroy"}
    if remote_command and stack != "neon":
        required = ("VERCEL_API_TOKEN",) if stack == "runtime" else TOKEN_KEYS
        missing = [key for key in required if not env.get(key)]
        if missing:
            print(
                "Missing Terraform credentials: " + ", ".join(missing), file=sys.stderr
            )
            return 2

    if remote_command and stack != "vercel":
        outputs = terraform_outputs(env=env)
        if stack == "neon":
            connection = outputs["database_admin_connection"]
            for target, source in {
                "database_host": "host",
                "pooled_host": "pooled_host",
                "database_name": "database",
                "database_owner": "username",
                "database_owner_password": "password",
            }.items():
                env[f"TF_VAR_{target}"] = connection[source]
        else:
            required = ("SUPABASE_S3_ACCESS_KEY_ID", "SUPABASE_S3_SECRET_ACCESS_KEY")
            missing = [key for key in required if not env.get(key)]
            if missing:
                print(
                    "Missing storage credentials: " + ", ".join(missing),
                    file=sys.stderr,
                )
                return 2
            database_outputs = terraform_outputs("neon", env=env)
            env.update(
                {
                    "TF_VAR_database_url": database_outputs["backend_database_url"],
                    "TF_VAR_backend_project_id": outputs["vercel_backend_project_id"],
                    "TF_VAR_storage_access_key": env[required[0]],
                    "TF_VAR_storage_secret_key": env[required[1]],
                }
            )

    return subprocess.call(["terraform", f"-chdir={STACKS[stack]}", *args], env=env)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, KeyError, OSError) as error:
        label = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print("Terraform setup failed: " + label, file=sys.stderr)
        raise SystemExit(2) from None
