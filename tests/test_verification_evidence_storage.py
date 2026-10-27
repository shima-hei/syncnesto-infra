"""検証証拠bucket以外へ書かず、既存の異なる設定を拒否する。"""

import unittest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from scripts import verification_evidence_storage as evidence


def missing(code, status=404):
    return ClientError(
        {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
        "test",
    )


class EvidenceBucketTests(unittest.TestCase):
    def client(self):
        client = MagicMock()
        client.get_bucket_acl.return_value = {
            "Owner": {"ID": "owner"},
            "Grants": [{"Grantee": {"Type": "CanonicalUser", "ID": "owner"}}],
        }
        client.get_bucket_policy.side_effect = missing("NoSuchBucketPolicy")
        client.get_bucket_cors.side_effect = missing("NoSuchCORSConfiguration")
        client.get_bucket_versioning.return_value = {"Status": "Enabled"}
        return client

    def test_create_only_evidence_bucket_and_versioning(self):
        client = self.client()
        client.head_bucket.side_effect = missing("NoSuchBucket")
        client.get_bucket_versioning.side_effect = [{}, {"Status": "Enabled"}]
        with patch.object(evidence, "client_for", return_value=client):
            self.assertTrue(evidence.initialize(None)["created"])
        client.put_bucket_versioning.assert_called_once_with(
            Bucket=evidence.BUCKET, VersioningConfiguration={"Status": "Enabled"}
        )
        for call in client.method_calls:
            self.assertEqual(call.kwargs.get("Bucket"), evidence.BUCKET)

    def test_idempotent_existing_bucket_has_no_writes(self):
        client = self.client()
        with patch.object(evidence, "client_for", return_value=client):
            self.assertFalse(evidence.initialize(None)["created"])
        client.create_bucket.assert_not_called()
        client.put_bucket_versioning.assert_not_called()

    def test_incompatible_existing_configuration_is_not_repaired(self):
        for kind in ["acl", "policy", "cors", "versioning"]:
            client = self.client()
            if kind == "acl":
                client.get_bucket_acl.return_value["Grants"] = [
                    {"Grantee": {"Type": "Group"}}
                ]
            elif kind == "policy":
                client.get_bucket_policy.side_effect = None
                client.get_bucket_policy.return_value = {"Policy": "existing"}
            elif kind == "cors":
                client.get_bucket_cors.side_effect = None
                client.get_bucket_cors.return_value = {
                    "CORSRules": [{"AllowedOrigins": ["*"]}]
                }
            else:
                client.get_bucket_versioning.return_value = {"Status": "Suspended"}
            with (
                self.subTest(kind=kind),
                patch.object(evidence, "client_for", return_value=client),
                self.assertRaises(ValueError),
            ):
                evidence.initialize(None)
            client.put_bucket_versioning.assert_not_called()
