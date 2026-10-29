"""Golden-log eval: score investigate() on each fixture, or write the ADK eval set from the fixtures."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
EVALSET = ROOT / "adk" / "golden-logs.evalset.json"
SEVERITY_ORDER = ("info", "warning", "error", "critical")
RUBRICS = {
    "db-timeout": ["Identifies database connection timeouts or pool exhaustion as the observed failure.",
                   "Presents the cause as tentative rather than a confirmed root cause."],
    "auth-expired": ["Identifies expired tokens causing HTTP 401 authentication failures.",
                     "Presents the cause as tentative rather than a confirmed root cause."],
    "payment-timeout": ["Identifies the payment gateway timing out and the charge state being unknown.",
                        "Presents the cause as tentative rather than a confirmed root cause."],
    "healthy-startup": ["Describes the service as starting normally, without inventing a failure.",
                        "Uses a severity of info or warning, not error or critical."],
}


def score_result(findings, expected):
    """Return (passed, reasons) for one set of findings against its expectations."""
    reasons = []
    severity = findings.get("severity")
    if severity not in SEVERITY_ORDER:
        reasons.append(f"unknown severity {severity!r}")
    else:
        rank = SEVERITY_ORDER.index(severity)
        minimum = expected.get("severity_at_least")
        if minimum is not None and rank < SEVERITY_ORDER.index(minimum):
            reasons.append(f"severity {severity} is below {minimum}")
        maximum = expected.get("severity_at_most")
        if maximum is not None and rank > SEVERITY_ORDER.index(maximum):
            reasons.append(f"severity {severity} is above {maximum}")
    keywords = expected.get("must_mention_any") or []
    text = f"{findings.get('summary', '')} {findings.get('likely_cause', '')}".lower()
    if keywords and not any(keyword.lower() in text for keyword in keywords):
        reasons.append("none of the expected keywords appear in summary or likely_cause")
    return not reasons, reasons


def pass_rate(results):
    """Fraction of passing results; 0.0 for an empty list."""
    return sum(1 for passed in results if passed) / len(results) if results else 0.0


def load_fixtures():
    for log in sorted(FIXTURES.glob("*.log")):
        expected = json.loads(log.with_suffix(".expected.json").read_text(encoding="utf-8"))
        yield log.stem, log.read_text(encoding="utf-8"), expected


def write_adk_evalset():
    from google.adk.evaluation.eval_set import EvalSet
    cases = []
    for name, content, _ in load_fixtures():
        # Same payload shape investigate() sends.
        numbered = "\n".join(f"[L{number}] {line}" for number, line in enumerate(content.splitlines(), 1))
        cases.append({
            "eval_id": name,
            "conversation": [{
                "invocation_id": f"{name}-1",
                "user_content": {"role": "user", "parts": [{"text": json.dumps(
                    {"current_log": numbered, "historical_incidents": []})}]},
            }],
            "session_input": {"app_name": "log_investigator", "user_id": "eval", "state": {}},
            "rubrics": [{"rubric_id": f"{name}-{index}", "rubric_content": {"text_property": text}}
                        for index, text in enumerate(RUBRICS[name], 1)],
        })
    evalset = EvalSet.model_validate({"eval_set_id": "golden-logs", "name": "Golden logs",
                                      "description": "Synthetic logs with known diagnoses.", "eval_cases": cases})
    EVALSET.write_text(json.dumps(evalset.model_dump(mode="json", exclude_none=True), indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--write-adk-evalset", action="store_true")
    args = parser.parse_args(argv)
    if args.write_adk_evalset:
        write_adk_evalset()
        return 0
    sys.path.insert(0, str(ROOT.parent))
    outcomes = []
    for name, content, expected in load_fixtures():
        try:
            # Imported here so the scorer tests need no ADK.
            from agent_service.service import investigate
            passed, reasons = score_result(asyncio.run(investigate(content)), expected)
        except Exception as error:  # A crash is a failure, not an abort.
            passed, reasons = False, [f"crashed: {type(error).__name__}"]
        outcomes.append(passed)
        print(f"{'PASS' if passed else 'FAIL'} {name}" + ("" if passed else " - " + "; ".join(reasons)))
    rate = pass_rate(outcomes)
    print(f"{sum(outcomes)}/{len(outcomes)} passed, pass rate {rate:.2f}, threshold {args.threshold:.2f}")
    return 0 if rate >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
