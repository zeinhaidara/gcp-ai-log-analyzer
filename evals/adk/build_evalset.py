"""Generate golden_logs.evalset.json from evals/fixtures. Run from the repo root."""
import json
from pathlib import Path

from google.adk.evaluation.eval_set import EvalSet

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent / "fixtures"

RUBRICS = {
    "db_timeout": ["Identifies database connection timeouts or pool exhaustion as the observed failure.",
                   "Presents the cause as tentative rather than a confirmed root cause."],
    "auth_expired": ["Identifies expired tokens causing HTTP 401 authentication failures.",
                     "Presents the cause as tentative rather than a confirmed root cause."],
    "payment_timeout": ["Identifies the payment gateway timing out and the charge state being unknown.",
                        "Presents the cause as tentative rather than a confirmed root cause."],
    "healthy_startup": ["Describes the service as starting normally, without inventing a failure.",
                        "Uses a severity of info or warning, not error or critical."],
}


def user_message(content):
    # Same payload shape investigate() sends.
    numbered = "\n".join(f"[L{number}] {line}" for number, line in enumerate(content.splitlines(), 1))
    return json.dumps({"current_log": numbered, "historical_incidents": []})


def build():
    cases = []
    for log in sorted(FIXTURES.glob("*.log")):
        cases.append({
            "eval_id": log.stem,
            "conversation": [{
                "invocation_id": f"{log.stem}-1",
                "user_content": {"role": "user", "parts": [{"text": user_message(log.read_text(encoding="utf-8"))}]},
            }],
            "session_input": {"app_name": "log_investigator", "user_id": "eval", "state": {}},
            "rubrics": [{"rubric_id": f"{log.stem}-{index}", "rubric_content": {"text_property": text}}
                        for index, text in enumerate(RUBRICS[log.stem], 1)],
        })
    evalset = EvalSet.model_validate({"eval_set_id": "golden_logs", "name": "Golden logs",
                                      "description": "Synthetic logs with known diagnoses.", "eval_cases": cases})
    (HERE / "golden_logs.evalset.json").write_text(
        json.dumps(evalset.model_dump(mode="json", exclude_none=True), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
