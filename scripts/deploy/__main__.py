"""公開環境の操作を用途別のコマンドへ振り分ける。"""

import argparse
import runpy
import sys

COMMANDS = {
    "validate": ("validate", "本番stateと資格情報を使わず全Terraform構成を検証"),
    "terraform": ("terraform", "Terraformへ認証情報を渡して実行"),
    "ci": ("ci", "既存の共有stateで全構成をplan/apply"),
    "migrate": ("migrate", "バックエンドのAlembic migration"),
    "seed": ("seed", "RBACと初期管理者の作成"),
    "tenant-owner": ("tenant_owner", "Default Tenantの指定Ownerを初期化"),
    "storage": ("storage", "非公開バケットの準備・検証・清掃"),
    "demo": ("demo", "専用資源だけの初期化・分離検証・回収"),
    "bootstrap-state": ("bootstrap_state", "既存stateのバックアップ・共有DBへの移行"),
    "verify-state": ("verify_state", "stateの権限分離・TLS・ロックの検証"),
    "verify-database": ("verify_database", "アプリDBのTLS・最小権限の検証"),
    "verify-web": ("verify_web", "公開アプリのログイン・CSRF・画像送信の検証"),
}


def main() -> None:
    """個別モジュールの引数処理と秘密を隠すエラー処理を維持する。"""
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="\n".join(f"{key}: {value[1]}" for key, value in COMMANDS.items()),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    module = f"scripts.deploy.{COMMANDS[args.command][0]}"
    sys.argv = [f"{parser.prog} {args.command}", *args.arguments]
    runpy.run_module(module, run_name="__main__")


if __name__ == "__main__":
    main()
