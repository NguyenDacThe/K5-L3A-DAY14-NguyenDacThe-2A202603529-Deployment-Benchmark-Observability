"""Record real Prometheus alert transitions after the CP8 fault change."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.request

root = Path(__file__).resolve().parents[1]
injection = json.loads((root / "reports/cp8-fault-injection.json").read_text(encoding="utf-8-sig"))
started = datetime.fromisoformat(injection["started_at_utc"])
expected = {"AgentHighErrorRate", "AgentHighLatencyP95"}
report = {"injection": injection, "first_firing": {}, "observations": []}
deadline = time.monotonic() + 240
while time.monotonic() < deadline:
    now = datetime.now(timezone.utc)
    with urllib.request.urlopen("http://localhost:9090/api/v1/rules", timeout=10) as response:
        payload = json.load(response)
    rules = [rule for group in payload["data"]["groups"] for rule in group["rules"]]
    snapshot = {"checked_at_utc": now.isoformat(), "rules": rules}
    report["observations"].append(snapshot)
    for rule in rules:
        if rule["name"] in expected and rule["state"] == "firing" and rule["name"] not in report["first_firing"]:
            report["first_firing"][rule["name"]] = {
                "observed_at_utc": now.isoformat(),
                "elapsed_seconds": round((now - started).total_seconds(), 2),
                "alerts": rule["alerts"],
            }
            print(rule["name"], "FIRING after", report["first_firing"][rule["name"]]["elapsed_seconds"], "seconds", flush=True)
    (root / "reports/cp8-alert-timeline.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    firing = {rule["name"] for rule in rules if rule["state"] == "firing"}
    if expected <= firing:
        (root / "reports/cp8-alerts-both-firing.json").write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        print("PASS: both injected-fault alerts are firing simultaneously", flush=True)
        break
    time.sleep(5)
else:
    raise SystemExit("FAIL: injected-fault alerts did not both fire within 240 seconds")
