import unittest

import golden_logs

EXPECTED = {"severity_at_least": "error", "must_mention_any": ["database", "timeout"]}


def findings(severity="error", summary="Database connection timeout", cause="Pool exhausted"):
    return {"severity": severity, "summary": summary, "likely_cause": cause}


class ScoreTests(unittest.TestCase):
    def test_pass(self):
        passed, reasons = golden_logs.score_result(findings(), EXPECTED)
        self.assertTrue(passed)
        self.assertEqual(reasons, [])

    def test_severity_too_low(self):
        passed, reasons = golden_logs.score_result(findings("warning"), EXPECTED)
        self.assertFalse(passed)
        self.assertIn("below", reasons[0])

    def test_severity_too_high(self):
        expected = {"severity_at_least": "info", "severity_at_most": "warning", "must_mention_any": ["database"]}
        passed, reasons = golden_logs.score_result(findings("critical"), expected)
        self.assertFalse(passed)
        self.assertIn("above", reasons[0])

    def test_unknown_severity(self):
        passed, reasons = golden_logs.score_result(findings("catastrophic"), EXPECTED)
        self.assertFalse(passed)
        self.assertIn("unknown severity", reasons[0])

    def test_missing_keyword(self):
        passed, reasons = golden_logs.score_result(findings(summary="Disk full", cause="Logs not rotated"), EXPECTED)
        self.assertFalse(passed)
        self.assertIn("keywords", reasons[0])

    def test_keyword_match_is_case_insensitive(self):
        self.assertTrue(golden_logs.score_result(findings(summary="DATABASE DOWN", cause=""), EXPECTED)[0])

    def test_pass_rate(self):
        self.assertEqual(golden_logs.pass_rate([]), 0.0)
        self.assertEqual(golden_logs.pass_rate([True, True, False, True]), 0.75)
        self.assertEqual(golden_logs.pass_rate([False]), 0.0)


if __name__ == "__main__":
    unittest.main()
