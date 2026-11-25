"""Read-only checks of submission artifacts; writes an audit, never stages or pushes."""
import csv
import json
import re
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
checks = []


def git(*args):
    return subprocess.run(
        ['git', '-c', f'safe.directory={ROOT}', '-c', 'core.autocrlf=true', *args], cwd=ROOT,
        capture_output=True, check=True,
    ).stdout.decode('utf-8', errors='replace')


def read(path):
    data = (ROOT / path).read_bytes()
    return data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')


def js(path):
    return json.loads(read(path))


def check(name, ok, detail):
    checks.append(dict(name=name, passed=bool(ok), detail=detail))


origin = git('remote', 'get-url', 'origin').strip()
public = js('reports/submission-github.json')
check('Repository identity/public',
      bool(re.search(r'K5-L3[AB]-DAY14-[A-Za-z]+-2A\d+-Deployment-Benchmark-Observability', origin))
      and origin.removesuffix('.git') == public['url']
      and public['http_status'] == 200 and public['anonymous_access'] and public['public_marker_present'],
      'Anonymous GitHub HTTP 200; origin matches named public fork (saved check).')
grader = read('reports/submission-production-ready.txt')
check('Full production grader', 'PASS 12/12' in grader and '42/42 checks passed' in grader
      and read('reports/submission-production-ready.exitcode').strip() == '0',
      'Original grader with public URL: 12/12 criteria, 42/42 checks, exit 0.')
cloud = js('reports/submission-public-checks.json')
check('Public deployment', cloud['passed'] and [c['actual_status'] for c in cloud['checks']] == [200, 200, 401, 200],
      f"Saved HTTPS checks at {cloud['checked_at_utc']}: 200/200/401/200.")
mission = read('MISSION_ANSWERS.md')
report = read('BENCHMARK_REPORT.md')
check('Submission documents', all((ROOT / p).is_file() for p in ['MISSION_ANSWERS.md', 'DEPLOYMENT.md', 'BENCHMARK_REPORT.md'])
      and all(f'Part {i}' in mission for i in range(1, 6)) and 'AI log' in mission
      and 'CP8 và audit SUBMISSION' in mission and 'PASS 12/12' in mission
      and cloud['base_url'] in read('DEPLOYMENT.md')
      and all(f'## {i}.' in report for i in range(1, 7)) and '___' not in report,
      'Part 1–5, grader checklist, CP7/8, AI log, deployment URL and completed benchmark report.')

required = [f'load_v2_c{c}.json' for c in [1, 10, 50, 100]] + [
    f'load_v2_slow_{s}.json' for s in ['0', '0.03', '0.1']] + [
    'eval_v1.json', 'eval_v2.json', 'eval_v2_fixed.json']
develop = ROOT / '06-lab-complete/benchmark-observability/develop'
check('Ten JSON artifacts and copies', all((ROOT/'reports'/n).read_bytes() == (develop/'reports'/n).read_bytes() for n in required)
      and all(js('reports/'+n)['total_requests'] == 300 for n in required[:7]),
      'All 10 required JSON files exist and match develop copies; seven loads have 300 requests each.')
for name, expected in [('eval_v1', 1), ('eval_v2', 21), ('eval_v2_fixed', 23), ('cp8-eval-production', 23)]:
    data = js(f'reports/{name}.json')
    check(name, data['passed'] == expected and data['total'] == 23,
          f"{data['passed']}/23 correct; fixed and production must have 23/23.")
base = js('reports/eval_v2.json')
fixed = js('reports/eval_v2_fixed.json')
production_eval = js('reports/cp8-eval-production.json')
check('No quality regression', all(data['quality_gate']['passed'] and
      data['quality_gate']['regressions'] == [] and
      data['quality_gate']['min_accuracy'] == 1.0 for data in [fixed, production_eval]),
      'Fixed and production JSON gates require 100%, both PASS with zero regressions.')

for scale, expected in [(1, (7812, 74, 340, 65.62)), (3, (7798, 69, 230, 65.42))]:
    filename = f'scale_{scale}_stats.csv'
    path = ROOT / 'benchmark-results' / filename
    with path.open(newline='', encoding='utf-8-sig') as stream:
        row = next(r for r in csv.DictReader(stream) if r['Name'] == 'Aggregated')
    got = (int(row['Request Count']), int(row['Failure Count']), int(row['95%']), round(float(row['Requests/s']), 2))
    check(f'Locust scale {scale}', got == expected and
          path.read_bytes() == (ROOT/'06-lab-complete/benchmark-observability/production/benchmark-results'/filename).read_bytes()
          and all(str(v) in report for v in [expected[0], expected[1], expected[2], expected[3]]),
          f'Aggregated requests/failures/p95/RPS = {got}; root CSV matches original and report.')

images = ['dashboard', 'running', 'test', 'grafana-dashboard', 'jaeger-slow-trace', 'jaeger-error-trace', 'prometheus-alert-firing']
for image in images:
    raw = (ROOT / f'screenshots/{image}.png').read_bytes()
    width, height = struct.unpack('>II', raw[16:24])
    check(f'Screenshot {image}', raw[:8] == b'\x89PNG\r\n\x1a\n' and len(raw) > 10000 and width >= 800 and height >= 500,
          f'PNG {width}x{height}, {len(raw)} bytes; images also reviewed visually.')
timeline = js('reports/cp8-alert-timeline.json')['first_firing']
snapshot = js('reports/cp8-alerts-both-firing.json')['rules']
check('Two simultaneous firing alerts', all(
    name in timeline and timeline[name]['elapsed_seconds'] > 0
    and any(r['name'] == name and r['state'] == 'firing' for r in snapshot)
    for name in ['AgentHighErrorRate', 'AgentHighLatencyP95']),
    'Error alert 82.67s and latency alert 142.90s; same firing snapshot; original thresholds.')
traces = js('reports/cp8-traces-summary.json')
logs = js('reports/cp8-trace-log-correlation.json')
check('Trace/log correlation', all(traces[k]['trace_id'] == logs[k]['trace_id']
      and traces[k]['trace_id'] in read('reports/cp8-agent.log')
      and traces[k]['trace_id'] in read(f'reports/cp8-{k}-trace.json') for k in ['slow', 'error'])
      and bool(traces['error']['exception_events']), 'Real slow/error trace IDs match captured agent JSON logs; error has exception.')
check('Alert rule validation', 'SUCCESS' in read('reports/cp8-promtool.txt'), 'promtool original rules: SUCCESS.')

protected = ['06-lab-complete/check_production_ready.py',
             '06-lab-complete/benchmark-observability/develop/eval/golden_dataset.jsonl',
             '06-lab-complete/benchmark-observability/develop/eval/run_eval.py',
             '06-lab-complete/benchmark-observability/develop/load_test.py']
check('Protected grader/dataset unchanged', all(
    git('show', 'HEAD:'+p).replace('\r\n', '\n') == read(p).replace('\r\n', '\n') for p in protected),
    'Grader, golden dataset, eval and load scripts match HEAD.')
check('Git whitespace', not git('diff', '--check').strip(), 'git diff --check passes.')
tracked = git('ls-files', '-z').split('\0')
history = [line.partition(' ')[2] for line in git('rev-list', '--all', '--objects').splitlines()]
bad_env = [p for p in tracked + history if p and Path(p).name.startswith('.env') and Path(p).name != '.env.example']
check('No env in index/history', not bad_env, f'Forbidden env paths in tracked files/history: {len(bad_env)}.')
candidates = sorted(set(p for p in git('ls-files', '--cached', '--others', '--exclude-standard', '-z').split('\0') if p))
known = []
for env in ['06-lab-complete/.env', '06-lab-complete/.env.cloud']:
    if (ROOT/env).exists():
        for line in read(env).splitlines():
            key, _, value = line.partition('=')
            if any(s in key.upper() for s in ['KEY', 'TOKEN', 'PASSWORD']) and len(value.strip('"\'')) >= 16:
                known.append(value.strip('"\''))
leaks, large, contacts = [], [], []
for name in candidates:
    path = ROOT / name
    if not path.is_file():
        continue
    data = path.read_bytes()
    if len(data) >= 100 * 1024**2:
        large.append(name)
    if b'\0' in data and not data.startswith((b'\xff\xfe', b'\xfe\xff')):
        continue
    try:
        content = read(name)
    except UnicodeError:
        continue
    if any(secret in content for secret in known) or re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}', content):
        leaks.append(name)
    if name in ['MISSION_ANSWERS.md', 'DEPLOYMENT.md', 'BENCHMARK_REPORT.md'] or name.startswith(('reports/', 'benchmark-results/')):
        if re.search(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', content) or re.search(
                r'(?<![\w.])(?:\+84|0)(?:[35789](?:[ .-]?\d){8}|2(?:[ .-]?\d){9})(?![\w.])', content):
            contacts.append(name)
check('Secret scan of commit candidates', not leaks, f'{len(candidates)} candidate files; known local/cloud secrets and token/private-key patterns; findings: {leaks}. Values never printed.')
check('Submission contact data', not contacts, f'Email/Vietnam phone pattern scan of authored reports/docs: {contacts}; screenshots visually reviewed; pattern scan is not exhaustive.')
check('GitHub file sizes', not large, f'No candidate file >=100 MiB; oversized files: {large}.')
check('Local CP8 cleanup', js('reports/cp8-cleanup.json')['clean'], 'No containers or networks remain for k5-day14-observability; cloud retained.')

result = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),
              ready_to_commit=all(c['passed'] for c in checks),
              remote_submission_current=False,
              note='Working tree changes are not committed/pushed; GitHub Actions and LMS submission remain pending.',
              checks=checks)
(ROOT/'reports/submission-audit.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
for item in checks:
    print(('PASS' if item['passed'] else 'FAIL') + ': ' + item['name'] + ' — ' + item['detail'])
print(f"\nReady to commit: {result['ready_to_commit']}; checks {sum(c['passed'] for c in checks)}/{len(checks)}")
raise SystemExit(0 if result['ready_to_commit'] else 1)
