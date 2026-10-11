import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import parser as report_parser


def tradefed_xml(fingerprint="vendor/device/device:14/UP1A.231005.007/123:userdebug/test-keys",
                 suite="cts", done="true", result="pass"):
    failed = ' failed="1"' if result == "fail" else ' failed="0"'
    failure = '<Failure message="expected true but was false"><StackTrace>AssertionError</StackTrace></Failure>' if result == "fail" else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Result suite_name="{suite}" suite_plan="{suite}" suite_version="16_r1" suite_build_number="42">
  <Build build_fingerprint="{fingerprint}" build_version_security_patch="2026-09-05" build_version_release="14" build_version_sdk="34" build_abis="arm64-v8a" build_id="UP1A.231005.007" build_type="userdebug"/>
  <Summary pass="{1 if result == 'pass' else 0}"{failed} modules_done="{1 if done == 'true' else 0}" modules_total="1"/>
  <Module name="CtsSampleTestCases" abi="arm64-v8a" done="{done}">
    <TestCase name="SampleTest">
      <Test name="testExample" result="{result}">{failure}</Test>
    </TestCase>
  </Module>
</Result>""".encode()


def write_zip(path, files):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)


class TradefedParserTests(unittest.TestCase):
    def test_parse_tradefed_xml_extracts_build_and_failure_details(self):
        report = report_parser.parse_tradefed_xml(tradefed_xml(result="fail"), "fixture.zip!test_result.xml")
        self.assertEqual(report["suite"], "CTS")
        self.assertEqual(report["fingerprint"], "vendor/device/device:14/UP1A.231005.007/123:userdebug/test-keys")
        self.assertEqual(report["securityPatch"], "2026-09-05")
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["failures"][0]["testCase"], "SampleTest#testExample")
        self.assertIn("expected true but was false", report["failures"][0]["details"])

    def test_analyze_zip_returns_dashboard_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cts.zip"
            write_zip(path, {"results/cts/test_result.xml": tradefed_xml()})
            dashboard = report_parser.analyze_reports([("cts.zip", str(path))])
        self.assertEqual(dashboard["recognizedReports"], 1)
        self.assertEqual(dashboard["overall"]["totalTests"], 1)
        self.assertEqual(dashboard["overall"]["passed"], 1)
        self.assertEqual(dashboard["buildFingerprint"], "vendor/device/device:14/UP1A.231005.007/123:userdebug/test-keys")
        self.assertEqual(dashboard["suites"][0]["name"], "CTS")

    def test_nested_zip_is_scanned(self):
        nested = io.BytesIO()
        with zipfile.ZipFile(nested, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("test_result.xml", tradefed_xml())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outer.zip"
            write_zip(path, {"nested/inner.zip": nested.getvalue()})
            dashboard = report_parser.analyze_reports([("outer.zip", str(path))])
        self.assertEqual(dashboard["recognizedReports"], 1)
        self.assertEqual(dashboard["xmlReportsFound"], 1)

    def test_different_build_fingerprints_suppress_aggregate_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.zip"
            second = Path(tmp) / "second.zip"
            write_zip(first, {"test_result.xml": tradefed_xml()})
            write_zip(second, {"test_result.xml": tradefed_xml(fingerprint="other/device/device:14/build:tag")})
            dashboard = report_parser.analyze_reports([("first.zip", str(first)), ("second.zip", str(second))])
        self.assertTrue(dashboard["overall"]["fingerprintMismatch"])
        self.assertEqual(dashboard["overall"]["totalTests"], 0)
        self.assertEqual(dashboard["buildFingerprint"], "MULTIPLE BUILDS DETECTED")

    def test_incomplete_module_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incomplete.zip"
            write_zip(path, {"test_result.xml": tradefed_xml(done="false")})
            dashboard = report_parser.analyze_reports([("incomplete.zip", str(path))])
        self.assertEqual(len(dashboard["incompleteModules"]), 1)
        self.assertEqual(dashboard["incompleteModules"][0]["reason"], "Module is marked done=false in Tradefed result")

    def test_invalid_zip_is_rejected_with_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.zip"
            path.write_bytes(b"not a zip")
            with self.assertRaisesRegex(ValueError, "No recognized Tradefed"):
                report_parser.analyze_reports([("broken.zip", str(path))])

    def test_oversized_xml_entry_is_skipped_before_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oversized.zip"
            write_zip(path, {"test_result.xml": b"x" * (1024 * 1024 + 1)})
            with patch.object(report_parser, "MAX_ZIP_ENTRY_BYTES", 1024 * 1024):
                reports, found, errors = report_parser.scan(str(path), "oversized.zip", set(), set())
        self.assertEqual(reports, [])
        self.assertEqual(found, 0)
        self.assertTrue(any("entry is too large" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
