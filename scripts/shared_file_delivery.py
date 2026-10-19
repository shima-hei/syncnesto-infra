"""LOCAL共有添付の配信先だけを初期化する。通常S3/SQSには接続しない。"""

import argparse
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import dotenv_values

PREFIX = "SHARED_FILE_DELIVERY_"


def create_config(path: Path, data: Path, port: int, origin: str) -> None:
    """既存ファイルを上書きせず、所有者専用の設定を作る。"""
    if not 1024 < port < 65536 or port in {3000, 4566, 5432, 8000}:
        raise ValueError("専用ポートを指定してください")
    if data.is_symlink() or path.is_symlink():
        raise ValueError("専用の実directory/fileを指定してください")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    if data.stat().st_mode & 0o077:
        raise ValueError("データdirectoryを所有者専用にしてください")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1"}
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("LOCALのFrontend originを指定してください")
    values = {
        "SHARED_PUBLICATION_DOWNLOAD_ENABLED": "false",
        PREFIX + "ENDPOINT_URL": f"http://127.0.0.1:{port}",
        PREFIX + "PORT": str(port),
        PREFIX + "BUCKET_NAME": "syncnesto-local-shared-files",
        PREFIX + "ACCESS_KEY_ID": "local-shared-" + secrets.token_hex(12),
        PREFIX + "SECRET_ACCESS_KEY": secrets.token_urlsafe(48),
        PREFIX + "DATA_DIR": str(data.resolve()),
        PREFIX + "FRONTEND_ORIGIN": origin,
    }
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write("".join(f"{key}={value}\n" for key, value in values.items()))


def configuration(path: Path) -> dict[str, str]:
    """明示された専用設定だけを読み、クラウドの設定を混ぜない。"""
    if path.stat().st_mode & 0o077:
        raise ValueError("設定fileを所有者専用にしてください")
    values = {
        key: value for key, value in dotenv_values(path).items() if value is not None
    }
    endpoint = urlsplit(values[PREFIX + "ENDPOINT_URL"])
    if (
        endpoint.scheme != "http"
        or endpoint.hostname not in {"localhost", "127.0.0.1"}
        or endpoint.port in {None, 3000, 4566, 5432, 8000}
        or endpoint.path not in {"", "/"}
        or endpoint.query
        or endpoint.fragment
        or endpoint.username is not None
        or endpoint.password is not None
    ):
        raise ValueError("専用のLOCAL配信先だけを指定してください")
    for name in [
        "BUCKET_NAME",
        "ACCESS_KEY_ID",
        "SECRET_ACCESS_KEY",
        "FRONTEND_ORIGIN",
    ]:
        if not values.get(PREFIX + name):
            raise ValueError("配信専用設定が不足しています")
    origin = urlsplit(values[PREFIX + "FRONTEND_ORIGIN"])
    if (
        origin.scheme != "http"
        or origin.hostname not in {"localhost", "127.0.0.1"}
        or origin.path
        or origin.query
        or origin.fragment
        or origin.username is not None
        or origin.password is not None
    ):
        raise ValueError("LOCALのFrontend originを指定してください")
    return values


def initialize(path: Path) -> None:
    """専用bucketを作り、既存の異なる設定を勝手に置換しない。"""
    values = configuration(path)
    client = boto3.client(
        "s3",
        endpoint_url=values[PREFIX + "ENDPOINT_URL"],
        aws_access_key_id=values[PREFIX + "ACCESS_KEY_ID"],
        aws_secret_access_key=values[PREFIX + "SECRET_ACCESS_KEY"],
        region_name="ap-northeast-1",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=10,
            retries={"total_max_attempts": 1},
        ),
    )
    bucket = values[PREFIX + "BUCKET_NAME"]
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as error:
        if error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 404:
            raise
        client.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )
    version = client.get_bucket_versioning(Bucket=bucket).get("Status")
    if version is None:
        client.put_bucket_versioning(
            Bucket=bucket, VersioningConfiguration={"Status": "Enabled"}
        )
    elif version != "Enabled":
        raise ValueError("既存の配信バケットのversioningを確認してください")
    rule = {
        "AllowedOrigins": [values[PREFIX + "FRONTEND_ORIGIN"]],
        "AllowedMethods": ["GET", "HEAD"],
        "AllowedHeaders": ["range"],
        "ExposeHeaders": ["Content-Disposition", "Content-Length", "Content-Range"],
    }
    try:
        existing = client.get_bucket_cors(Bucket=bucket).get("CORSRules", [])
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") != "NoSuchCORSConfiguration":
            raise
        existing = []
    if not existing:
        client.put_bucket_cors(Bucket=bucket, CORSConfiguration={"CORSRules": [rule]})
    else:

        def normalized(rules):
            return [{key: sorted(item.get(key, [])) for key in rule} for item in rules]

        if normalized(existing) != normalized([rule]):
            raise ValueError("既存の配信バケットのCORSを確認してください")


def main() -> None:
    """秘密を表示せず、明示した専用設定の作成/初期化を実行する。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-config")
    create.add_argument("--data-dir", type=Path, required=True)
    create.add_argument("--port", type=int, default=8333)
    create.add_argument("--origin", default="http://localhost:3000")
    commands.add_parser("init")
    args = parser.parse_args()
    if args.command == "create-config":
        create_config(args.env_file, args.data_dir, args.port, args.origin)
    else:
        initialize(args.env_file)
    print(json.dumps({"command": args.command, "success": True}))


if __name__ == "__main__":
    main()
