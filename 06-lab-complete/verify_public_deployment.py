"""Check the four CP6 HTTP cases without printing credentials.

Run from the repository root with AGENT_API_KEY set in the environment:
    python 06-lab-complete/verify_public_deployment.py --url https://your-host \
        --out reports/cp6-public-checks.json
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # Never forward the API key to a redirect destination.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_public_deployment(base: str, key: str, timeout: float = 15) -> dict:
    parsed = urllib.parse.urlsplit(base)
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.username or parsed.password or parsed.query or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("Use the HTTPS origin of the agent, without credentials, path, query or fragment")
    base = base.rstrip("/")
    opener = urllib.request.build_opener(NoRedirect())
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "base_url": base, "checks": []}
    cases = [
        ("health", "GET", "/health", False, 200),
        ("ready", "GET", "/ready", False, 200),
        ("ask_without_key", "POST", "/ask", False, 401),
        ("ask_with_key", "POST", "/ask", True, 200),
    ]
    for name, method, path, authenticated, expected in cases:
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["X-API-Key"] = key
        request = urllib.request.Request(
            base + path, method=method, headers=headers,
            data=json.dumps({"question": "Hello"}).encode() if method == "POST" else None,
        )
        try:
            with opener.open(request, timeout=timeout) as response:
                status = response.status
                body = response.read(65536).decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            status = error.code
            body = error.read(65536).decode("utf-8", "replace")
        except (urllib.error.URLError, OSError) as error:
            status = None
            body = str(error)
        body = body.replace(key, "<REDACTED>")
        passed = status == expected
        if passed and name in ("health", "ready", "ask_with_key"):
            try:
                payload = json.loads(body)
                passed = isinstance(payload, dict)
                if passed and name == "health":
                    passed = payload.get("status") == "ok" and payload.get("environment") == "production"
                elif passed and name == "ready":
                    passed = payload.get("ready") is True
                elif passed and name == "ask_with_key":
                    passed = isinstance(payload.get("answer"), str) and bool(payload["answer"])
            except (ValueError, TypeError):
                passed = False
        report["checks"].append({
            "name": name, "method": method, "path": path,
            "expected_status": expected, "actual_status": status,
            "passed": passed, "response_body": body,
        })
        print(f"{name}: HTTP {status}, expected {expected} — {'PASS' if passed else 'FAIL'}", flush=True)
    report["passed"] = all(check["passed"] for check in report["checks"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", type=Path, default=Path("reports/cp6-public-checks.json"))
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    key = os.getenv("AGENT_API_KEY", "")
    if not key:
        parser.error("Set AGENT_API_KEY in the environment; do not put it in command-line arguments")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        report = check_public_deployment(args.url, key, args.timeout)
    except ValueError as error:
        parser.error(str(error))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{'PASS' if report['passed'] else 'FAIL'}: CP6 public checks; report: {args.out}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
