"""Pure scoring for golden-log evals; no cloud or ADK imports."""

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
