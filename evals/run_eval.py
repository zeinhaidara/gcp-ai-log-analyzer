"""Score investigate() on each golden log. Needs agent dependencies and Vertex AI access."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

import score

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"


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
            passed, reasons = score.score_result(run_one(content), expected)
        except Exception as error:  # A crash is a failure, not an abort.
            passed, reasons = False, [f"crashed: {type(error).__name__}"]
        outcomes.append(passed)
        print(f"{'PASS' if passed else 'FAIL'} {name}" + ("" if passed else " - " + "; ".join(reasons)))
    rate = score.pass_rate(outcomes)
    print(f"{sum(outcomes)}/{len(outcomes)} passed, pass rate {rate:.2f}, threshold {args.threshold:.2f}")
    return 0 if rate >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
