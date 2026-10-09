"""Bounded, evidence-first reconstruction. No model calls or invented topology."""
import json
import re
from collections import Counter
from datetime import datetime, timezone

MAX_LINES = 12000
MAX_EVENTS = 1200
MAX_SERVICES = 20
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,79}\Z")
LEVEL = re.compile(r"\b(TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|CRITICAL|FATAL|ALERT|EMERGENCY)\b", re.I)
STAMP = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?|\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)(?!\d)")
PAIRS = re.compile(r'\b([A-Za-z_][\w.]*)=(?:"([^"\r\n]*)"|([^\s,;]+))')
LEVELS = {"warn": "warning", "fatal": "critical", "alert": "critical", "emergency": "critical", "notice": "info", "trace": "debug"}


def _name(value):
    return value if isinstance(value, str) and NAME.fullmatch(value) else None


def _timestamp(value):
    if not isinstance(value, str):
        return None, None
    value = value.replace(",", ".")
    try:
        if re.match(r"\d{4}-", value):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            # Naive stamps are a consistent log clock, not the host's timezone.
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp(), "datetime"
        parsed = datetime.strptime(value, "%H:%M:%S.%f" if "." in value else "%H:%M:%S")
        return parsed.hour * 3600 + parsed.minute * 60 + parsed.second + parsed.microsecond / 1e6, "clock"
    except (ValueError, OverflowError):
        return None, None


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _parse(raw, line):
    values = {}
    message = raw
    if raw.lstrip().startswith("{"):
        try:
            document = json.loads(raw)
            if isinstance(document, dict):
                payload = document.get("jsonPayload", document)
                if isinstance(payload, dict):
                    values.update(payload)
                values.update({k: v for k, v in document.items() if not isinstance(v, (dict, list))})
                resource = document.get("resource", {})
                if isinstance(resource, dict) and isinstance(resource.get("labels"), dict):
                    values.setdefault("service", resource["labels"].get("service_name"))
                candidate = values.get("message") or values.get("msg") or values.get("textPayload")
                if isinstance(candidate, str):
                    message = candidate
        except (ValueError, RecursionError):
            pass  # A malformed JSON line is still inspectable evidence.
    text_fields = {match[1]: match[2] if match[2] is not None else match[3] for match in PAIRS.finditer(message)}
    # Structured metadata takes precedence over field-like text in a message.
    values = {**text_fields, **values}
    if isinstance(values.get("message", values.get("msg")), str):
        message = values.get("message", values.get("msg"))
    level_match = LEVEL.search(raw)
    level = values.get("severity") or values.get("level") or (level_match[1] if level_match else "info")
    level = str(level).lower()
    level = LEVELS.get(level, level)
    if level not in ("debug", "info", "warning", "error", "critical"):
        level = "info"
    service = _name(values.get("service") or values.get("service_name") or values.get("logger"))
    service_source = "field" if service else "unattributed"
    if not service and level_match:
        tail = raw[level_match.end():].lstrip(" :")
        bracket = re.match(r"\[([A-Za-z0-9_.:/-]{1,80})\]", tail)
        conventional = re.match(r"([a-z][A-Za-z0-9_-]{0,79})\s+", tail)
        candidate = bracket[1] if bracket else conventional[1] if conventional else None
        # Common prose after a level must not become fictional services.
        prose = {"the", "a", "an", "request", "failed", "unable", "connection", "timeout", "retry", "test", "starting", "started", "error", "warning", "authentication", "payment"}
        if candidate and candidate.lower() not in prose:
            service = candidate
            service_source = "log_format"
    service = service or "unattributed"
    trace = None
    for key in ("trace_id", "trace", "request_id", "requestId", "correlation_id"):
        trace = _name(values.get(key))
        if trace:
            break
    target = _name(values.get("target") or values.get("upstream") or values.get("dependency"))
    stamp_match = STAMP.search(raw)
    stamp = values.get("timestamp") or values.get("time") or (stamp_match[1] if stamp_match else None)
    seconds, clock_type = _timestamp(stamp)
    status = _number(values.get("status", values.get("status_code", values.get("http_status"))))
    if status is not None and (status >= 500 or status in (401, 403)) and level in ("debug", "info"):
        level = "error"
    lower = message.lower()
    if level in ("error", "critical") or (status is not None and (status >= 500 or status in (401, 403))):
        kind = "failure"
    elif (re.search(r"\b(recovered|restored|healthy|resolved)\b|\brecovery\s+(observed|complete|confirmed)\b", lower)
          and not re.search(r"\b(not|never)\s+(?:\w+\s+){0,2}(recovered|restored|healthy|resolved)\b|\brecovery\s+(failed|pending)\b", lower)
          and level in ("info", "debug")):
        kind = "recovery"
    elif re.search(r"\b(deploy(?:ed|ment)?|config(?:uration)?[_ -]changed|rollback|rolled.back)\b", lower):
        kind = "change"
    elif ((_number(values.get("retry", values.get("retry_count"))) or 0) > 0
          or (re.search(r"\b(retry|retrying|retries)\b", lower)
              and not re.search(r"\b(without|no|zero)\s+(retry|retries)\b|\bretry(?:_count)?=0\b", lower))):
        kind = "retry"
    elif level == "warning":
        kind = "warning"
    elif status is not None and 200 <= status < 300:
        kind = "success"
    else:
        kind = "activity"
    return {"id": f"L{line}", "line": line, "service": service, "service_source": service_source,
            "trace": trace, "target": target, "severity": level, "kind": kind,
            "timestamp": stamp if isinstance(stamp, str) else None,
            "message": message[:1000], "raw": raw[:2400], "clipped": len(raw) > 2400,
            "_seconds": seconds, "_clock": clock_type}


def _sample(events):
    if len(events) <= MAX_EVENTS:
        return events
    # Preserve boundaries and the earliest signal of every kind/service before
    # uniformly sampling remaining context. Never renumber source evidence.
    chosen = {0, len(events) - 1}
    seen = set()
    for index, event in enumerate(events):
        key = (event["service"], event["kind"])
        if key not in seen and len(chosen) < MAX_EVENTS // 4:
            chosen.add(index)
            seen.add(key)
    signals = [i for i, e in enumerate(events) if e["kind"] not in ("activity", "success")]
    budget = MAX_EVENTS // 2
    if signals:
        chosen.update(signals[i * len(signals) // min(budget, len(signals))] for i in range(min(budget, len(signals))))
    remaining = [i for i in range(len(events)) if i not in chosen]
    slots = max(0, MAX_EVENTS - len(chosen))
    chosen.update(remaining[i * len(remaining) // slots] for i in range(slots))
    return [events[i] for i in sorted(chosen)[:MAX_EVENTS]]


def build_replay(content, findings=None):
    """Reconstruct observations and explicit call relationships from source lines."""
    lines = content.splitlines()
    events = [_parse(raw, number) for number, raw in enumerate(lines[:MAX_LINES], 1) if raw.strip()]
    timestamped = sum(e["_seconds"] is not None for e in events)
    types = {e["_clock"] for e in events}
    chronological = bool(events) and timestamped == len(events) and len(types) == 1
    rollover_assumed = False
    if chronological:
        if types == {"clock"}:
            rollover, previous = 0, None
            for event in events:
                seconds = event["_seconds"]
                if previous is not None and previous - seconds > 43200:
                    rollover += 86400
                    rollover_assumed = True
                event["_seconds"] += rollover
                previous = seconds
        events.sort(key=lambda e: (e["_seconds"], e["line"]))
    origin = events[0]["_seconds"] if chronological else None
    for event in events:
        event["offset_ms"] = round((event["_seconds"] - origin) * 1000) if chronological else None
        del event["_seconds"], event["_clock"]
    parsed_count = len(events)
    events = _sample(events)
    owners = Counter(e["service"] for e in events)
    names = list(owners)
    for event in events:
        if event["target"] and event["target"] not in names:
            names.append(event["target"])
    names = sorted(names, key=lambda name: (-owners[name], name))[:MAX_SERVICES]
    nodes = [{"id": name, "event_count": owners[name], "attributed": name != "unattributed"} for name in names]
    links = {}
    for event in events:
        source, target = event["service"], event["target"]
        if source != "unattributed" and source in names and target in names and source != target:
            key = (source, target)
            link = links.setdefault(key, {"source": source, "target": target, "event_ids": [], "basis": "explicit log field"})
            link["event_ids"].append(event["id"])
    hypotheses = []
    if isinstance(findings, dict) and isinstance(findings.get("hypotheses"), list):
        for candidate in findings["hypotheses"][:3]:
            if not isinstance(candidate, dict):
                continue
            references = candidate.get("evidence_lines", [])
            if not isinstance(references, list):
                continue
            references = sorted({n for n in references if type(n) is int and 1 <= n <= len(lines) and lines[n - 1].strip()})[:8]
            if references and isinstance(candidate.get("title"), str) and isinstance(candidate.get("explanation"), str):
                hypotheses.append({"title": candidate["title"][:160], "explanation": candidate["explanation"][:1500], "evidence_lines": references, "basis": "AI hypothesis"})
    first = next((e["id"] for e in events if e["kind"] == "failure"), None)
    return {"version": 1, "events": events, "nodes": nodes, "links": list(links.values()),
            "traces": sorted({e["trace"] for e in events if e["trace"]})[:100],
            "first_fault": first, "hypotheses": hypotheses,
            "coverage": {"total_lines": len(lines), "scanned_lines": min(len(lines), MAX_LINES),
                         "parsed_events": parsed_count, "shown_events": len(events),
                         "timestamped_events": timestamped, "order": "timestamp" if chronological else "source",
                         "clock_rollover_assumed": rollover_assumed,
                         "sampled": parsed_count > len(events), "truncated": len(lines) > MAX_LINES,
                         "omitted_services": max(0, len(set(owners) | {e['target'] for e in events if e['target']}) - len(nodes))}}
