"""専用配信先の誤接続・既存設定上書き・秘密の表示を防ぐ。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from scripts import shared_file_delivery as delivery


class SharedDeliveryTests(unittest.TestCase):
    def config(self, root):
        path = root / "private.env"
        delivery.create_config(path, root / "data", 18334, "http://localhost:3136")
        return path

    def test_private_random_configuration_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = self.config(root)
            before = path.read_bytes()
            self.assertEqual(path.stat().st_mode & 0o077, 0)
            self.assertEqual((root / "data").stat().st_mode & 0o077, 0)
            values = delivery.configuration(path)
            self.assertGreaterEqual(
                len(values[delivery.PREFIX + "SECRET_ACCESS_KEY"]), 48
            )
            self.assertEqual(values["SHARED_PUBLICATION_DOWNLOAD_ENABLED"], "false")
            with self.assertRaises(FileExistsError):
                delivery.create_config(
                    path, root / "data", 18334, "http://localhost:3136"
                )
            self.assertEqual(path.read_bytes(), before)

    def test_normal_s3_and_remote_endpoints_rejected_before_network(self):
        for endpoint in [
            "http://localhost:4566",
            "https://remote.example",
            "http://localhost:8333/path",
            "http://user@localhost:8333",
            "http://localhost",
            "http://:password@localhost:8333",
        ]:
            with tempfile.TemporaryDirectory() as temporary:
                path = self.config(Path(temporary))
                source = path.read_text().replace("http://127.0.0.1:18334", endpoint)
                path.write_text(source)
                with patch.object(delivery.boto3, "client") as factory:
                    with self.assertRaises(ValueError):
                        delivery.initialize(path)
                    factory.assert_not_called()

    def test_existing_cors_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.config(Path(temporary))
            client = MagicMock()
            client.get_bucket_versioning.return_value = {"Status": "Enabled"}
            client.get_bucket_cors.return_value = {
                "CORSRules": [{"AllowedOrigins": ["http://different.local"]}]
            }
            with (
                patch.object(delivery.boto3, "client", return_value=client),
                self.assertRaises(ValueError),
            ):
                delivery.initialize(path)
            client.put_bucket_cors.assert_not_called()
            client.put_bucket_versioning.assert_not_called()

    def test_new_bucket_initializes_only_dedicated_credentials_and_get_cors(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.config(Path(temporary))
            client = MagicMock()
            client.head_bucket.side_effect = ClientError(
                {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
                "HeadBucket",
            )
            client.get_bucket_versioning.return_value = {}
            client.get_bucket_cors.side_effect = ClientError(
                {"Error": {"Code": "NoSuchCORSConfiguration"}}, "GetBucketCors"
            )
            with patch.object(delivery.boto3, "client", return_value=client) as factory:
                delivery.initialize(path)
            kwargs = factory.call_args.kwargs
            self.assertEqual(kwargs["endpoint_url"], "http://127.0.0.1:18334")
            self.assertNotEqual(kwargs["aws_secret_access_key"], "test")
            rule = client.put_bucket_cors.call_args.kwargs["CORSConfiguration"][
                "CORSRules"
            ][0]
            self.assertEqual(rule["AllowedOrigins"], ["http://localhost:3136"])
            self.assertEqual(rule["AllowedMethods"], ["GET", "HEAD"])
            self.assertEqual(
                client.create_bucket.call_args.kwargs["Bucket"],
                "syncnesto-local-shared-files",
            )
            client.put_object.assert_not_called()


if __name__ == "__main__":
    unittest.main()
