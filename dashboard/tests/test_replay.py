import unittest
from pathlib import Path
from replay import build_replay, MAX_EVENTS, MAX_LINES


class ReplayTests(unittest.TestCase):
    def test_demo_reconstructs_calls_fault_and_recovery(self):
        content = (Path(__file__).parents[1] / "static/demos/retry-storm.txt").read_text()
        replay = build_replay(content)
        self.assertEqual(replay["first_fault"], "L9")
        self.assertEqual(replay["coverage"]["order"], "timestamp")
        self.assertEqual({(link["source"], link["target"]) for link in replay["links"]},
                         {("gateway", "checkout"), ("checkout", "orders"), ("orders", "database")})
        self.assertEqual(replay["events"][-1]["kind"], "recovery")
        self.assertEqual(replay["events"][-1]["offset_ms"], 39000)
        self.assertEqual(len(replay["traces"]), 3)

    def test_json_cloud_logging_and_trace_correlation(self):
        content = '\n'.join([
            '{"timestamp":"2026-10-09T12:00:00Z","severity":"INFO","resource":{"labels":{"service_name":"orders"}},"jsonPayload":{"message":"Query submitted","target":"db","trace_id":"r1"}}',
            '{"timestamp":"2026-10-09T12:00:01Z","level":"ERROR","service":"db","request_id":"r1","message":"Connection timeout"}',
        ])
        replay = build_replay(content)
        self.assertEqual(replay["events"][0]["service"], "orders")
        self.assertEqual(replay["events"][1]["trace"], "r1")
        self.assertEqual(replay["first_fault"], "L2")

    def test_unstructured_logs_do_not_invent_topology_or_duration(self):
        replay = build_replay("ERROR timeout\n\nWARN retry\nrequest still pending")
        self.assertEqual([e["line"] for e in replay["events"]], [1, 3, 4])
        self.assertEqual(replay["links"], [])
        self.assertEqual(replay["nodes"][0]["id"], "unattributed")
        self.assertEqual(replay["coverage"]["order"], "source")
        self.assertTrue(all(e["offset_ms"] is None for e in replay["events"]))

    def test_shared_trace_alone_does_not_imply_dependency(self):
        replay = build_replay("12:00:00 INFO service=a trace=one ready\n12:00:01 ERROR service=b trace=one failure")
        self.assertEqual(replay["links"], [])

    def test_sorting_preserves_evidence_line_numbers_and_midnight(self):
        replay = build_replay("12:00:02 ERROR service=db failed\n12:00:01 WARN service=api waiting")
        self.assertEqual([e["id"] for e in replay["events"]], ["L2", "L1"])
        self.assertEqual(replay["events"][1]["offset_ms"], 1000)
        replay = build_replay("23:59:59 INFO service=db started\n00:00:01 ERROR service=db failed")
        self.assertEqual(replay["events"][1]["offset_ms"], 2000)

    def test_mixed_or_invalid_timestamps_preserve_source_order(self):
        for content in ("12:00:01 INFO service=a ready\nERROR service=b failed", "99:00:00 INFO service=a ready\n12:00:02 ERROR service=b failed", "2026-10-09T12:00:00Z INFO service=a ready\n12:00:02 ERROR service=b failed"):
            with self.subTest(content=content):
                replay = build_replay(content)
                self.assertEqual(replay["coverage"]["order"], "source")
                self.assertEqual([e["line"] for e in replay["events"]], [1, 2])

    def test_bounded_sampling_keeps_first_fault_last_event_and_source_refs(self):
        content = "\n".join(f"12:00:00 INFO service=api ready {i}" for i in range(MAX_EVENTS * 2))
        content += "\n12:00:01 ERROR service=db failed\n12:00:02 INFO service=db recovered"
        replay = build_replay(content)
        self.assertEqual(len(replay["events"]), MAX_EVENTS)
        self.assertTrue(replay["coverage"]["sampled"])
        self.assertEqual(replay["first_fault"], f"L{MAX_EVENTS * 2 + 1}")
        self.assertEqual(replay["events"][-1]["line"], MAX_EVENTS * 2 + 2)

    def test_parse_limit_is_explicit_and_service_count_is_bounded(self):
        replay = build_replay("\n".join(f"INFO service=svc{i} activity" for i in range(MAX_LINES + 2)))
        self.assertTrue(replay["coverage"]["truncated"])
        self.assertEqual(replay["coverage"]["scanned_lines"], MAX_LINES)
        self.assertLessEqual(len(replay["events"]), MAX_EVENTS)
        self.assertEqual(len(replay["nodes"]), 20)
        self.assertGreater(replay["coverage"]["omitted_services"], 0)

    def test_hypotheses_keep_only_real_nonempty_source_lines(self):
        findings = {"hypotheses": [{"title": "Pool", "explanation": "Tentative", "evidence_lines": [1, 2, 3, 100, True]}, {"title": "Invented", "explanation": "No evidence", "evidence_lines": [100]}]}
        replay = build_replay("INFO service=db started\n\nERROR service=db failed", findings)
        self.assertEqual(len(replay["hypotheses"]), 1)
        self.assertEqual(replay["hypotheses"][0]["evidence_lines"], [1, 3])

    def test_malformed_json_remains_evidence_and_raw_is_bounded(self):
        replay = build_replay('{"message": broken}\n' + 'x' * 5000)
        self.assertEqual(len(replay["events"]), 2)
        self.assertTrue(replay["events"][1]["clipped"])
        self.assertEqual(len(replay["events"][1]["raw"]), 2400)

    def test_retry_fields_and_warn_http_failures_are_observed(self):
        replay = build_replay('12:00:00 WARN service=api retry=1 message="Waiting"\n12:00:01 WARN service=api status=504 message="Request ended"')
        self.assertEqual(replay["events"][0]["kind"], "retry")
        self.assertEqual(replay["events"][1]["kind"], "failure")

    def test_nullable_cloud_fields_fall_back_without_losing_service_or_message(self):
        replay = build_replay('{"timestamp":null,"time":"12:00:00","severity":null,"level":"ERROR","service_name":"api","resource":{"labels":{"region":"us-central1"}},"textPayload":"Connection timed out"}')
        self.assertEqual(replay["events"][0]["service"], "api")
        self.assertEqual(replay["events"][0]["message"], "Connection timed out")
        self.assertEqual(replay["first_fault"], "L1")

    def test_negated_recovery_and_zero_retries_do_not_create_false_signals(self):
        replay = build_replay('12:00:00 INFO service=api message="Not yet recovered"\n12:00:01 INFO service=api status=200 retry_count=0 message="Completed without retry"\n12:00:02 INFO service=api message="Recovery pending"')
        self.assertEqual([event["kind"] for event in replay["events"]], ["activity", "success", "activity"])

    def test_structured_fields_are_not_overwritten_by_message_text(self):
        replay = build_replay('{"service":"api","target":"database","severity":"INFO","message":"service=fictional target=other status=503","status":200}')
        event = replay["events"][0]
        self.assertEqual((event["service"], event["target"], event["severity"]), ("api", "database", "info"))
        self.assertEqual(event["kind"], "success")


if __name__ == "__main__":
    unittest.main()
