"""Collect actual Jaeger v3 spans for the CP8 injected-fault interval."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request

root = Path(__file__).resolve().parents[1]
injection = json.loads((root / "reports/cp8-fault-injection.json").read_text(encoding="utf-8-sig"))
start = datetime.fromisoformat(injection["started_at_utc"]).isoformat()


def fetch(path):
    with urllib.request.urlopen("http://localhost:16686" + path, timeout=30) as response:
        return [json.loads(line) for line in response.read().decode().splitlines() if line.strip()]


def flatten(chunks):
    traces = {}
    for chunk in chunks:
        for resource in chunk.get("result", {}).get("resourceSpans", []):
            for scope in resource.get("scopeSpans", []):
                for span in scope.get("spans", []):
                    traces.setdefault(span["traceId"], {})[span["spanId"]] = span
    return {trace_id: list(spans.values()) for trace_id, spans in traces.items()}


def duration(span):
    return (int(span["endTimeUnixNano"]) - int(span["startTimeUnixNano"])) / 1_000_000


def server_span(spans):
    return next(span for span in spans if span.get("kind") == 2)


for attempt in range(12):
    query = urllib.parse.urlencode({
        "query.service_name": "observable-agent",
        "query.start_time_min": start,
        "query.start_time_max": datetime.now(timezone.utc).isoformat(),
        "query.search_depth": 200,
    })
    traces = flatten(fetch("/api/v3/traces?" + query))
    # Batch export may expose a trace's child spans before its server span arrives.
    traces = {key: spans for key, spans in traces.items() if any(span.get("kind") == 2 for span in spans)}
    successful = [(key, spans) for key, spans in traces.items() if not any(span.get("status", {}).get("code") == 2 for span in spans)]
    errors = [(key, spans) for key, spans in traces.items() if any(event.get("name") == "exception" for span in spans for event in span.get("events", []))]
    if successful and errors:
        slow_id, slow_spans = max(successful, key=lambda item: duration(server_span(item[1])))
        if duration(server_span(slow_spans)) >= 1000:
            error_id, error_spans = errors[0]
            break
    time.sleep(5)
else:
    raise SystemExit("Could not find a slow successful trace and an exception trace in injected-fault interval")

summary = {"selection": "Longest successful trace among up to 200 queried traces in the fault interval; one trace with exception event", "query": query, "sample_trace_count": len(traces)}
for label, trace_id in (("slow", slow_id), ("error", error_id)):
    raw = fetch("/api/v3/traces/" + trace_id)
    spans = flatten(raw)[trace_id]
    server = server_span(spans)
    llm = next(span for span in spans if span["name"].startswith("chat "))
    retrieval = next(span for span in spans if span["name"] == "agent.retrieve_context")
    (root / f"reports/cp8-{label}-trace.json").write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    summary[label] = {"trace_id": trace_id, "server_span_id": server["spanId"], "llm_span_id": llm["spanId"], "duration_ms": duration(server), "llm_ms": duration(llm), "retrieval_ms": duration(retrieval), "llm_percent": round(duration(llm) / duration(server) * 100, 2), "llm_status": llm.get("status"), "exception_events": [event for span in spans for event in span.get("events", []) if event.get("name") == "exception"]}
(root / "reports/cp8-traces-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: {field: value for field, value in summary[key].items() if field != "exception_events"} for key in ("slow", "error")}, indent=2))
