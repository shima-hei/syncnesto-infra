"""既存LOCAL SeaweedFSに検証証拠専用bucketだけを追加する。"""

import argparse
import json
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from scripts.shared_file_delivery import PREFIX, configuration

BUCKET = "syncnesto-local-verification-evidence"


def client_for(path):
    """既存server資格情報を読み、値を表示しない。"""
    values = configuration(path)
    if values[PREFIX + "BUCKET_NAME"] == BUCKET:
        raise ValueError("既存の共有配信bucketと分けてください")
    return boto3.client(
        "s3",
        endpoint_url=values[PREFIX + "ENDPOINT_URL"],
        aws_access_key_id=values[PREFIX + "ACCESS_KEY_ID"],
        aws_secret_access_key=values[PREFIX + "SECRET_ACCESS_KEY"],
        region_name="ap-northeast-1",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=2,
            read_timeout=5,
            retries={"total_max_attempts": 1},
        ),
    )


def check_private(client):
    """既存の公開ACL/policy/CORSを勝手に置き換えない。"""
    acl = client.get_bucket_acl(Bucket=BUCKET)
    if any(
        g.get("Grantee", {}).get("Type") == "Group"
        or g.get("Grantee", {}).get("ID") != acl.get("Owner", {}).get("ID")
        for g in acl.get("Grants", [])
    ):
        raise ValueError("証拠bucketのACLがprivateではありません")
    for operation, key, missing in (
        (client.get_bucket_policy, "Policy", {"NoSuchBucketPolicy", "NoSuchPolicy"}),
        (client.get_bucket_cors, "CORSRules", {"NoSuchCORSConfiguration"}),
    ):
        try:
            if operation(Bucket=BUCKET).get(key):
                raise ValueError("既存policy/CORSは確認が必要です")
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") not in missing:
                raise


def initialize(path: Path):
    """対象bucket以外への書込・既存設定の修復は行わない。"""
    client = client_for(path)
    created = False
    try:
        client.head_bucket(Bucket=BUCKET)
    except ClientError as error:
        if error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 404:
            raise
        client.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )
        created = True
    check_private(client)
    status = client.get_bucket_versioning(Bucket=BUCKET).get("Status")
    if status is None and created:
        client.put_bucket_versioning(
            Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"}
        )
    elif status != "Enabled":
        raise ValueError("既存bucketのversioningが契約と異なります。自動置換しません")
    if client.get_bucket_versioning(Bucket=BUCKET).get("Status") != "Enabled":
        raise ValueError("Versioningを確認できません")
    return {
        "success": True,
        "created": created,
        "bucket": BUCKET,
        "versioning": "Enabled",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(initialize(args.env_file)))


if __name__ == "__main__":
    main()
