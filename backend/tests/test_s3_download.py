import io
import os
import unittest
from unittest.mock import MagicMock, patch

from app.storage.upload1 import parse_s3_location


class S3LocationTests(unittest.TestCase):
    def test_parses_virtual_hosted_https_url(self):
        bucket, key = parse_s3_location(
            "https://test-bucket.s3.amazonaws.com/POC/example%20document.docx",
            expected_bucket="test-bucket",
        )
        self.assertEqual(bucket, "test-bucket")
        self.assertEqual(key, "POC/example document.docx")

    def test_parses_s3_url(self):
        self.assertEqual(
            parse_s3_location(
                "s3://test-bucket/POC/example.docx",
                expected_bucket="test-bucket",
            ),
            ("test-bucket", "POC/example.docx"),
        )

    def test_rejects_an_unconfigured_bucket(self):
        with self.assertRaisesRegex(ValueError, "configured S3 bucket"):
            parse_s3_location(
                "https://another-bucket.s3.amazonaws.com/example.docx",
                expected_bucket="test-bucket",
            )


class S3ProxyDownloadTests(unittest.TestCase):
    def test_proxy_uses_authenticated_s3_get_object(self):
        from app.core import server

        s3_client = MagicMock()
        s3_client.get_object.return_value = {
            "Body": io.BytesIO(b"private document bytes"),
            "ContentType": (
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
        }

        with patch.dict(os.environ, {"S3_BUCKET_NAME": "test-bucket"}, clear=False):
            visible_handler = MagicMock()
            visible_handler.table.scan.return_value = {
                "Items": [{"document_id": "doc-1", "s3_url": "https://test-bucket.s3.amazonaws.com/POC/example.docx"}]
            }
            server.app.config["TESTING"] = True
            with patch.object(server, "get_s3_client", return_value=s3_client), patch.object(
                server, "DynamoDBHandler", return_value=visible_handler
            ):
                response = server.app.test_client().post(
                    "/api/proxy-download",
                    json={
                        "s3_url": (
                            "https://test-bucket.s3.amazonaws.com/"
                            "POC/example.docx"
                        )
                    },
                )
            server.app.config["TESTING"] = False

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"private document bytes")
        self.assertEqual(
            response.headers["Content-Disposition"],
            'attachment; filename="example.docx"',
        )
        s3_client.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="POC/example.docx"
        )


if __name__ == "__main__":
    unittest.main()
