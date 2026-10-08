"""Supabaseの非公開バケット準備・S3実通信検証・一時ファイル清掃。"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from .environment import ROOT

PROJECT = "pdyywnoregglnyjlapta"
BUCKET = "syncnesto-portfolio"
ENDPOINT = f"https://{PROJECT}.storage.supabase.co/storage/v1/s3"
ORIGIN = "https://syncnesto.vercel.app"
MAX_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class StorageTarget:
    """操作先をクライアント・バケット設定・実通信検証で共有する。"""

    project: str = PROJECT
    bucket: str = BUCKET
    region: str = "ap-southeast-1"
    origin: str = ORIGIN
    max_bytes: int = MAX_BYTES

    @property
    def endpoint(self) -> str:
        """ProjectからS3 endpointを組み立て、任意hostを受け付けない。"""
        return f"https://{self.project}.storage.supabase.co/storage/v1/s3"


PORTFOLIO = StorageTarget()


def request(url: str, *, method: str = "GET", headers=None, body=None):
    """応答とHTTP statusを返す。URLや資格情報はログに出さない。"""
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


def storage_headers(
    target: StorageTarget = PORTFOLIO, *, management_token: str | None = None
) -> dict[str, str]:
    """管理APIからservice_roleを一時的に読み、バケット操作だけに使用する。"""
    token = management_token or os.environ["SUPABASE_ACCESS_TOKEN"]
    status, _, body = request(
        f"https://api.supabase.com/v1/projects/{target.project}/api-keys?reveal=true",
        headers={"Authorization": "Bearer " + token},
    )
    if status != 200:
        raise RuntimeError(f"Cannot read project API keys (HTTP {status})")
    key = next(
        item["api_key"] for item in json.loads(body) if item["name"] == "service_role"
    )
    return {
        "apikey": key,
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
    }


def s3_client(
    target: StorageTarget = PORTFOLIO,
    *,
    access_key: str | None = None,
    secret_key: str | None = None,
):
    """アプリと同じ署名・path形式・checksum設定でクライアントを作る。"""
    return boto3.client(
        "s3",
        endpoint_url=target.endpoint,
        region_name=target.region,
        aws_access_key_id=access_key or os.environ["SUPABASE_S3_ACCESS_KEY_ID"],
        aws_secret_access_key=secret_key or os.environ["SUPABASE_S3_SECRET_ACCESS_KEY"],
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def prepare(
    s3, target: StorageTarget = PORTFOLIO, *, management_token: str | None = None
) -> None:
    """指定先の非公開バケットとサイズ上限を冪等に用意する。"""
    headers = storage_headers(target, management_token=management_token)
    base = f"https://{target.project}.supabase.co/storage/v1/bucket"
    status, _, _ = request(f"{base}/{target.bucket}", headers=headers)
    if status not in (200, 400, 404):
        raise RuntimeError(f"Cannot inspect bucket (HTTP {status})")
    settings = {"public": False, "file_size_limit": target.max_bytes}
    if status != 200:
        settings.update({"id": target.bucket, "name": target.bucket})
    status, _, _ = request(
        f"{base}/{target.bucket}" if status == 200 else base,
        method="PUT" if status == 200 else "POST",
        headers=headers,
        body=json.dumps(settings).encode(),
    )
    if status not in (200, 201):
        raise RuntimeError(f"Cannot configure private bucket (HTTP {status})")
    status, _, body = request(f"{base}/{target.bucket}", headers=headers)
    metadata = json.loads(body)
    if (
        status != 200
        or metadata.get("public") is not False
        or metadata.get("file_size_limit") != target.max_bytes
    ):
        raise RuntimeError("Bucket privacy or size limit could not be verified")
    s3.put_object(
        Bucket=target.bucket,
        Key="default-avatar.png",
        Body=(ROOT / "default-avatar.png").read_bytes(),
        ContentType="image/png",
    )
    print("PASS: private bucket, configured file limit, default avatar prepared")


def verify(s3, target: StorageTarget = PORTFOLIO) -> None:
    """署名付きURL・CORS・匿名アクセス拒否を実通信で確認する。"""
    key = "security-probes/" + uuid4().hex
    content = b"syncnesto private storage probe\n"
    put_url = s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": target.bucket,
            "Key": key,
            "ContentType": "text/plain",
            "ContentLength": len(content),
        },
        ExpiresIn=600,
    )
    try:
        status, headers, _ = request(
            put_url,
            method="OPTIONS",
            headers={
                "Origin": target.origin,
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        if (
            status not in (200, 204)
            or headers.get("Access-Control-Allow-Origin") not in (target.origin, "*")
            or "PUT" not in headers.get("Access-Control-Allow-Methods", "")
        ):
            raise RuntimeError("Browser PUT preflight failed")
        status, headers, _ = request(
            put_url,
            method="PUT",
            headers={"Content-Type": "text/plain", "Origin": target.origin},
            body=content,
        )
        if status not in (200, 201) or headers.get(
            "Access-Control-Allow-Origin"
        ) not in (target.origin, "*"):
            raise RuntimeError(f"Presigned PUT failed (HTTP {status})")
        get_url = s3.generate_presigned_url(
            "get_object", Params={"Bucket": target.bucket, "Key": key}, ExpiresIn=600
        )
        status, _, body = request(get_url)
        if status != 200 or body != content:
            raise RuntimeError("Presigned GET returned incorrect content")
        for url in (
            get_url.split("?", 1)[0],
            f"https://{target.project}.supabase.co/storage/v1/object/public/{target.bucket}/{key}",
        ):
            status, _, _ = request(url)
            if status < 400:
                raise RuntimeError("Anonymous access unexpectedly succeeded")
        tampered = get_url.replace("X-Amz-Signature=", "X-Amz-Signature=0")
        status, _, _ = request(tampered)
        if status < 400:
            raise RuntimeError("Invalid signature unexpectedly succeeded")
        result = s3.get_object(Bucket=target.bucket, Key=key)
        try:
            if result["Body"].read() != content or result["ContentLength"] != len(
                content
            ):
                raise RuntimeError("SDK read returned incorrect object metadata")
        finally:
            result["Body"].close()
        print(
            "PASS: signed PUT/GET, SDK read, browser preflight, anonymous and invalid-signature rejection"
        )
    finally:
        s3.delete_object(Bucket=target.bucket, Key=key)


def cleanup(s3, execute: bool) -> None:
    """1日以上古いpending prefixだけを清掃。通常は件数確認だけ行う。"""
    cutoff = datetime.now(UTC) - timedelta(days=1)
    count = 0
    for page in s3.get_paginator("list_objects_v2").paginate(
        Bucket=BUCKET, Prefix="pending-uploads/"
    ):
        for item in page.get("Contents", []):
            if item["LastModified"] < cutoff:
                count += 1
                if execute:
                    s3.delete_object(Bucket=BUCKET, Key=item["Key"])
    print(f"Pending objects older than one day: {count}; deleted={execute}")


def main() -> int:
    """コマンドを実行し、エラー時も署名付きURLや秘密を表示しない。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify", "cleanup-pending"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        s3 = s3_client()
        if args.command == "prepare":
            prepare(s3)
        elif args.command == "verify":
            verify(s3)
        else:
            cleanup(s3, args.execute)
    except (
        KeyError,
        StopIteration,
        RuntimeError,
        BotoCoreError,
        ClientError,
        urllib.error.URLError,
    ) as error:
        # urllib例外やSDKエラーには署名付きURLが含まれる可能性がある。
        label = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print("Storage operation failed: " + label, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
