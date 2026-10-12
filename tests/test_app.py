import io
import unittest
from unittest.mock import patch

import app as webapp


class UploadEndpointTests(unittest.TestCase):
    def setUp(self):
        webapp.app.config.update(TESTING=True)
        self.client = webapp.app.test_client()

    def test_home_page_is_available(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_analyze_requires_a_zip_file(self):
        response = self.client.post(
            "/api/analyze",
            data={"files": (io.BytesIO(b"plain text"), "report.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Only ZIP files", response.get_json()["error"])

    def test_oversized_upload_is_rejected(self):
        with patch.object(webapp, "MAX_FILE", 8):
            response = self.client.post(
                "/api/analyze",
                data={"files": (io.BytesIO(b"123456789"), "report.zip")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 413)
        self.assertIn("file limit", response.get_json()["error"])


    def test_upload_is_not_rejected_by_application_size_cap_when_unlimited(self):
        # A small payload exercises the same unlimited-limit code path without
        # allocating a multi-GB fixture in CI.
        dashboard = {"overall": {"totalTests": 0}, "suites": []}
        with patch.object(webapp, "MAX_FILE", 0), \
             patch.object(webapp, "analyze_reports", return_value=dashboard), \
             patch.object(webapp.history, "save"):
            response = self.client.post(
                "/api/analyze",
                data={"files": (io.BytesIO(b"123456789"), "report.zip")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 200)

    def test_apa_upload_packages_reports_with_suite_based_names(self):
        def fake_analysis(paths):
            filename = paths[0][0]
            suite = "CTS" if filename.startswith("cts") else "GTS"
            return {"suites": [{"name": suite}]}

        with patch.object(webapp, "MAX_FILE", 0), patch.object(webapp, "analyze_reports", side_effect=fake_analysis):
            response = self.client.post(
                "/api/apa-upload",
                data={"files": [
                    (io.BytesIO(b"zip-one"), "cts-first.zip"),
                    (io.BytesIO(b"zip-two"), "cts-second.zip"),
                    (io.BytesIO(b"zip-three"), "gts.zip"),
                ]},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")
        import zipfile
        with zipfile.ZipFile(io.BytesIO(response.data)) as package:
            self.assertEqual(package.namelist(), ["CTS_report1.zip", "CTS_report2.zip", "GTS_report.zip"])
            self.assertEqual(package.read("CTS_report1.zip"), b"zip-one")

    def test_health_endpoint_checks_database(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "healthy")

    def test_publish_rejects_non_object_payload(self):
        response = self.client.post("/api/publish", json=["not", "a", "dashboard"])
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
