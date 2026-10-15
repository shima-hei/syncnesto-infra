"""デモStorageの既存アバターだけを読み、稼働とS3接続を定期確認する。"""

import os
import sys

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from scripts.deploy import demo

DEMO_PROJECT = "jxtwcdmaooiasodubofu"
AVATAR_KEY = "default-avatar.png"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def check(env: dict[str, str]) -> None:
    """通常環境を拒否し、HEADと先頭8 bytesのGETだけを実行する。"""
    settings = demo.storage_environment(env)
    if settings[demo.STORAGE_KEYS[0]] != DEMO_PROJECT:
        raise RuntimeError("Expected the configured demo storage project")
    target = demo.storage_target(settings)
    client = boto3.client(
        "s3",
        endpoint_url=target.endpoint,
        region_name=target.region,
        aws_access_key_id=settings[demo.STORAGE_KEYS[1]],
        aws_secret_access_key=settings[demo.STORAGE_KEYS[2]],
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=10,
            retries={"mode": "standard", "total_max_attempts": 3},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
    try:
        head = client.head_object(Bucket=target.bucket, Key=AVATAR_KEY)
        size = head.get("ContentLength", 0)
        if (
            not isinstance(size, int)
            or size < len(PNG_SIGNATURE)
            or head.get("ContentType") != "image/png"
        ):
            raise RuntimeError("Demo avatar metadata is invalid")
        response = client.get_object(
            Bucket=target.bucket, Key=AVATAR_KEY, Range="bytes=0-7"
        )
        body = response["Body"]
        try:
            if (
                response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 206
                or response.get("ContentRange") != f"bytes 0-7/{size}"
                or body.read(len(PNG_SIGNATURE) + 1) != PNG_SIGNATURE
            ):
                raise RuntimeError("Demo avatar range response is invalid")
        finally:
            body.close()
    finally:
        client.close()


def main() -> int:
    try:
        check(dict(os.environ))
    except (BotoCoreError, ClientError, RuntimeError, OSError) as error:
        # SDK例外は署名やURLを含み得るため、メッセージやtracebackを出さない。
        print(
            f"Demo storage health check failed ({type(error).__name__}). "
            "Check the demo project status, S3 credentials, and default avatar.",
            file=sys.stderr,
        )
        return 1
    print("Demo storage healthy: existing private avatar metadata and PNG read OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
