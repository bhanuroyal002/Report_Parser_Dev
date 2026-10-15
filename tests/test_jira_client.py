import unittest
from unittest.mock import patch

from jira_client import JiraClient, _safe_jql_phrase, _score, _terms_for_finding


class JiraClientTests(unittest.TestCase):
    def test_unconfigured_client_leaves_findings_available(self):
        dashboard = {
            "failures": [{"suite": "CTS", "module": "CtsSampleTestCases", "testCase": "Sample#testAudio", "details": "Audio assertion failed"}],
            "incompleteModules": [],
        }
        result = JiraClient(base_url="", email="", api_token="").enrich_dashboard(dashboard)
        self.assertEqual(result["jiraIntegration"]["status"], "not_configured")
        self.assertEqual(result["failures"][0]["jiraMatches"], [])
        self.assertEqual(result["failures"][0]["jiraLookupStatus"], "not_configured")

    def test_search_match_includes_issue_and_status_history(self):
        client = JiraClient(
            base_url="https://jira.example.com",
            email="reader@example.com",
            api_token="not-a-real-token",
        )
        issue = {
            "key": "ANDROID-123",
            "fields": {
                "summary": "Sample testAudio failure on Android TV",
                "description": "CtsSampleTestCases Sample testAudio failed with audio assertion",
                "status": {"name": "Resolved"},
                "resolution": {"name": "Fixed"},
                "issuetype": {"name": "Bug"},
                "project": {"key": "ANDROID"},
                "priority": {"name": "Major"},
                "created": "2026-01-01T10:00:00.000+0000",
                "updated": "2026-02-01T10:00:00.000+0000",
                "resolutiondate": "2026-02-01T10:00:00.000+0000",
                "assignee": {"displayName": "Test User"},
            },
            "changelog": {
                "histories": [{
                    "created": "2026-02-01T10:00:00.000+0000",
                    "items": [{
                        "field": "status",
                        "fromString": "In Progress",
                        "toString": "Resolved",
                    }],
                }],
            },
        }
        dashboard = {
            "failures": [{
                "suite": "CTS",
                "module": "CtsSampleTestCases",
                "testCase": "Sample#testAudio",
                "details": "Audio assertion failed",
            }],
            "incompleteModules": [],
        }
        with patch.object(client, "_search", return_value=[issue]):
            result = client.enrich_dashboard(dashboard)
        self.assertEqual(result["jiraIntegration"]["status"], "connected")
        matches = result["failures"][0]["jiraMatches"]
        self.assertEqual(matches[0]["key"], "ANDROID-123")
        self.assertEqual(matches[0]["status"], "Resolved")
        self.assertEqual(matches[0]["resolution"], "Fixed")
        self.assertEqual(matches[0]["statusHistory"][0]["from"], "In Progress")
        self.assertEqual(matches[0]["statusHistory"][0]["to"], "Resolved")

    def test_jql_phrase_escapes_quotes_and_backslashes(self):
        self.assertEqual(_safe_jql_phrase('Audio "test" \\ failure'), 'Audio \\"test\\" \\\\ failure')

    def test_finding_terms_include_test_identity_and_module(self):
        terms = _terms_for_finding({
            "module": "arm64 CtsSampleTestCases",
            "testCase": "Sample#testAudio",
            "details": "java.lang.AssertionError: expected audio route",
        }, "failure")
        self.assertIn("Sample#testAudio", terms)
        self.assertIn("testAudio", terms)
        self.assertIn("arm64 CtsSampleTestCases", terms)

    def test_exact_test_method_scores_as_high_confidence(self):
        issue = {"fields": {"summary": "Failure in testAudio", "description": "CtsSampleTestCases"}}
        score, confidence, match_type = _score(
            issue,
            {"module": "CtsSampleTestCases", "testCase": "Sample#testAudio", "details": "failed"},
            "failure",
        )
        self.assertGreaterEqual(score, 70)
        self.assertEqual(confidence, "high")
        self.assertEqual(match_type, "test identity")


if __name__ == "__main__":
    unittest.main()
