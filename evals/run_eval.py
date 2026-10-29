"""Score investigate() on each golden log. Needs agent dependencies and Vertex AI access."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
SEVERITY_ORDER = ("info", "warning", "error", "critical")


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


def run_one(content):
    # Imported here so the scorer tests need no ADK.
    sys.path.insert(0, str(ROOT.parent))
    from agent_service.service import investigate
    return asyncio.run(investigate(content))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=0.8)
    args = parser.parse_args(argv)
    outcomes = []
    for name, content, expected in load_fixtures():
        try:
            passed, reasons = score_result(run_one(content), expected)
        except Exception as error:  # A crash is a failure, not an abort.
            passed, reasons = False, [f"crashed: {type(error).__name__}"]
        outcomes.append(passed)
        print(f"{'PASS' if passed else 'FAIL'} {name}" + ("" if passed else " - " + "; ".join(reasons)))
    rate = pass_rate(outcomes)
    print(f"{sum(outcomes)}/{len(outcomes)} passed, pass rate {rate:.2f}, threshold {args.threshold:.2f}")
    return 0 if rate >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
