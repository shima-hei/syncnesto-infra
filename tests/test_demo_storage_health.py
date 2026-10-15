"""通常Storageへの誤接続・書込み・資格情報のログ出力を防ぐ。"""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from scripts import demo_storage_health as health
from scripts.deploy import demo, storage


class DemoStorageHealthTests(unittest.TestCase):
    def setUp(self):
        self.env = dict(
            zip(demo.STORAGE_KEYS, (health.DEMO_PROJECT, "demo-key", "demo-secret"))
        )
        root_patch = patch.object(demo, "ROOT")
        root_patch.start().__truediv__.return_value.exists.return_value = False
        self.addCleanup(root_patch.stop)

    def test_rejects_other_projects_and_missing_demo_credentials_before_network(self):
        variants = []
        for ref in (storage.PROJECT, "a" * 20, "https://unexpected.example"):
            variants.append({**self.env, demo.STORAGE_KEYS[0]: ref})
        for key in demo.STORAGE_KEYS[1:]:
            env = self.env.copy()
            del env[key]
            env["SUPABASE_S3_ACCESS_KEY_ID"] = "normal-key"
            env["SUPABASE_S3_SECRET_ACCESS_KEY"] = "normal-secret"
            variants.append(env)
        for env in variants:
            with (
                self.subTest(env_keys=list(env)),
                patch.object(health.boto3, "client") as factory,
            ):
                with self.assertRaises(RuntimeError):
                    health.check(env)
                factory.assert_not_called()

    def client(self, *, prefix=health.PNG_SIGNATURE, status=206):
        client = MagicMock()
        client.head_object.return_value = {
            "ContentLength": 100,
            "ContentType": "image/png",
        }
        body = MagicMock()
        body.read.return_value = prefix
        client.get_object.return_value = {
            "Body": body,
            "ContentRange": "bytes 0-7/100",
            "ResponseMetadata": {"HTTPStatusCode": status},
        }
        return client, body

    def test_reads_only_fixed_avatar_and_closes_connections(self):
        client, body = self.client()
        with patch.object(health.boto3, "client", return_value=client):
            health.check(self.env)
        self.assertEqual(
            [call[0] for call in client.method_calls],
            ["head_object", "get_object", "close"],
        )
        client.get_object.assert_called_once_with(
            Bucket="syncnesto-demo", Key="default-avatar.png", Range="bytes=0-7"
        )
        body.read.assert_called_once_with(9)
        body.close.assert_called_once()
        client.close.assert_called_once()

    def test_invalid_or_unbounded_response_fails_and_closes_body(self):
        for prefix, status in ((b"wrong", 206), (health.PNG_SIGNATURE, 200)):
            client, body = self.client(prefix=prefix, status=status)
            with patch.object(health.boto3, "client", return_value=client):
                with self.assertRaises(RuntimeError):
                    health.check(self.env)
            body.close.assert_called_once()
            client.close.assert_called_once()

    def test_failure_is_nonzero_without_sdk_credentials_or_url_in_logs(self):
        error = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "demo-secret signed-url"}},
            "HeadObject",
        )
        output = io.StringIO()
        with (
            patch.object(health, "check", side_effect=error),
            contextlib.redirect_stderr(output),
        ):
            self.assertEqual(health.main(), 1)
        self.assertIn("ClientError", output.getvalue())
        self.assertNotIn("demo-secret", output.getvalue())
        self.assertNotIn("signed-url", output.getvalue())


if __name__ == "__main__":
    unittest.main()
