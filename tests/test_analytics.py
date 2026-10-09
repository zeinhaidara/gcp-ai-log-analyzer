import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import analytics


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        analytics._cached = None
        analytics._expires = 0

    def test_local_mode_does_not_query(self):
        with patch.dict(os.environ, {"STORAGE_BACKEND": "sqlite"}):
            self.assertFalse(analytics.incident_analytics()["enabled"])

    def test_reporting_is_bounded_and_cached(self):
        client = Mock()
        client.query.return_value.result.return_value = [SimpleNamespace(
            day="2026-10-09", severity="error", service_name="orders",
            failure_category="database_timeout", incidents=2)]
        with patch.dict(os.environ, {"STORAGE_BACKEND": "gcp", "GOOGLE_CLOUD_PROJECT": "test-project", "BIGQUERY_TABLE": "test-project.demo.incidents"}), patch("google.cloud.bigquery.Client", return_value=client):
            result = analytics.incident_analytics()
            self.assertEqual(result["total"], 2)
            self.assertEqual(result["categories"], {"database_timeout": 2})
            self.assertEqual(analytics.incident_analytics(), result)
        client.query.assert_called_once()
        query = client.query.call_args.args[0]
        self.assertIn("INTERVAL 7 DAY", query)
        self.assertEqual(client.query.call_args.kwargs["job_config"].maximum_bytes_billed, 52428800)

    def test_failure_is_cached(self):
        from google.api_core.exceptions import ServiceUnavailable
        client = Mock()
        client.query.side_effect = ServiceUnavailable("secret")
        with patch.dict(os.environ, {"STORAGE_BACKEND": "gcp", "GOOGLE_CLOUD_PROJECT": "test-project", "BIGQUERY_TABLE": "test-project.demo.incidents"}), patch("google.cloud.bigquery.Client", return_value=client):
            result = analytics.incident_analytics()
            self.assertFalse(result["enabled"])
            self.assertNotIn("secret", str(result))
            analytics.incident_analytics()
        client.query.assert_called_once()
