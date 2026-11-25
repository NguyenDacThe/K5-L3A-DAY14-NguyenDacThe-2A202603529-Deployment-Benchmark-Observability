# Benchmark & Observability Report — Day 14

> **CP7 và CP8 đã hoàn thành.** Các số liệu dưới đây lấy từ JSON/CSV, Prometheus API, Jaeger và screenshot thật. Stack local đã được dọn sau khi lưu bằng chứng.

**Họ tên:** Nguyễn Đắc Thể
**Ngày chạy:** 25/11/2026
**Môi trường:** Ubuntu/WSL2, Python 3.11.18, CPU 12th Gen Intel(R) Core(TM) i5-12500H, 16 logical CPU, RAM WSL 7.61 GiB; một process Uvicorn cho mỗi agent. Client và agent cùng WSL, source/log trên filesystem Windows mount.

[Metadata môi trường và SHA-256](reports/cp7-environment.json), [lệnh, timestamp UTC và exit code](reports/cp7-commands.json). Mỗi lượt load có **300 request đo**, một warm-up không tính; bốn concurrency 1/10/50/100, ba lượt tail ở concurrency 20. Agent v1 ở cổng 8001, v2 ở 8002; đây là phép đo local, không tạo tải lên Railway.

Cấu hình load: `MOCK_LATENCY_MS=120`, `MOCK_JITTER_MS=60`, `MOCK_SLOW_MS=1500`, `MOCK_RETRIEVAL_MS=20`, `MOCK_ERROR_RATE=0.01`, model `mock-llm-small`; slow rate 0.03 cho bảng concurrency và thay đổi như bảng 2.2. Các load test chạy trước khi bổ sung hai entry KB. Eval v1/v2/fixed giữ cùng cấu hình nhưng đặt `MOCK_ERROR_RATE=0` để cô lập chất lượng; slow rate vẫn 0.03. Không đặt random seed; mỗi cấu hình load đo một lượt, nên kết quả có dao động.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | Tạo khoảng dự phòng so với latency mock thông thường khoảng 200 ms và bắt được ảnh hưởng của request chậm khi vượt khoảng 5% mẫu |
| Error rate `/ask` | ≤ 2% | Mock lỗi nền 1%; ngưỡng cho phép một phần dao động của mẫu 300 request |
| Accuracy trên golden dataset | 100% sau sửa KB, 0 regression | Bộ câu hỏi cố định 23 câu của lab; mọi câu phải đạt threshold keyword 0.6 của script |

Hai ngưỡng load đúng với mặc định script (`--slo-p95-ms 500 --slo-error-rate 0.02`, toán tử **≤**). Baseline eval dùng gate mặc định 80%; lần eval fixed và job CI dùng 100%. Accuracy trên bộ keyword nhỏ này không chứng minh độ chính xác với câu hỏi bất kỳ trong production.

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| [1](reports/load_v2_c1.json) | 4.03 | 196.4 | 228.4 | 1710.5 | 1.33% | PASS |
| [10](reports/load_v2_c10.json) | 37.23 | 198.1 | 229.1 | 1692.2 | 1.00% | PASS |
| [50](reports/load_v2_c50.json) | 128.70 | 325.5 | 451.8 | 1742.3 | 1.00% | PASS |
| [100](reports/load_v2_c100.json) | 51.68 | 577.1 | 3781.3 | 4345.8 | 0.67% | FAIL |

**Nhận xét:** RPS tăng từ 4.03 ở concurrency 1 lên 128.70 ở 50, rồi giảm còn 51.68 ở 100. Ở mức 100, p50 đã là 577.1 ms và p95 3781.3 ms, cho thấy phần lớn mức tăng không chỉ nằm ở vài request slow; SLO latency FAIL, error rate vẫn PASS. Không suy ra throughput tăng tuyến tính theo concurrency.

Đây là batch hữu hạn 300 request; tổng thời gian còn chịu ảnh hưởng của các request chậm cuối batch, scheduling/socket, xử lý middleware và log I/O. Agent dùng asyncio nhưng vẫn có chi phí Python và ghi log đồng bộ trên Windows mount. Các yếu tố này là hướng cần profile; chưa có CPU/I/O profiling để kết luận chính xác nút thắt. Không dùng kết quả ngắn này như capacity steady-state của production.

Tất cả request lỗi quan sát được là HTTP 503 từ mock upstream: concurrency 1 có 4 lỗi, 10 có 3, 50 có 3, 100 có 2. Script tính latency percentile từ request HTTP 200 và tính error rate trên toàn bộ request; warm-up bị loại khỏi cả bảng và tổng cost.

### 2.2 Tail latency

Cùng concurrency 20, mỗi lượt 300 request, `MOCK_ERROR_RATE=0.01`:

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) | RPS | Error rate | SLO |
|---|---|---|---|---|---|---|
| [0](reports/load_v2_slow_0.json) | 215.8 | 274.3 | 304.3 | 89.52 | 1.00% | PASS |
| [0.03](reports/load_v2_slow_0.03.json) | 281.3 | 306.5 | 1734.5 | 55.69 | 1.00% | PASS |
| [0.1](reports/load_v2_slow_0.1.json) | 390.3 | 1706.0 | 1726.7 | 42.50 | 1.00% | FAIL |

**Nhận xét:** Từ slow rate 0 lên 0.03, average tăng 215.8 → 281.3 ms, còn p99 tăng 304.3 → 1734.5 ms. Average chia đều chi phí của số ít request bị cộng thêm 1500 ms, nên che khuất trải nghiệm nhóm chờ lâu. Với 3% slow, p95 vẫn 306.5 ms và PASS dù p99 đã khoảng 1.73 giây.

Khi slow rate lên 10%, p95 tăng lên 1706.0 ms và SLO FAIL. p99 ở 0.03 và 0.1 cùng nằm quanh 1.7 giây; không nhất thiết tăng đơn điệu vì độ trễ cộng thêm giống nhau và mẫu ngẫu nhiên. p99 nhạy với nhóm chậm hiếm, p95 phản ánh khi nhóm đó đủ lớn; nên dùng percentile và thêm p99 gate nếu yêu cầu trải nghiệm cần bảo vệ phần đuôi chặt hơn.

### 2.3 Metrics và độ dài câu hỏi (Exercise 7.1)

Đã thêm histogram `agent_question_length_chars` với buckets 20/50/100/200/500/1000/2000 và observe một lần ở đầu `/ask`, trước retrieval/LLM. Dùng histogram giúp mô tả phân bố mà không tạo label cho từng độ dài.

Bằng chứng sau một câu hỏi 27 ký tự và ba URL không tồn tại: [metrics_sample.prom](06-lab-complete/benchmark-observability/develop/reports/metrics_sample.prom), [response thật](06-lab-complete/benchmark-observability/develop/reports/metrics_sample_response.json).

```text
# Counter: số request thành công theo method/route/status
http_requests_total{method="POST",route="/ask",status="200"} 1.0

# Gauge: request đang xử lý, snapshot lúc rảnh
agent_in_flight_requests 0.0

# Histogram mới: tổng 1 câu hỏi, dài 27 ký tự
agent_question_length_chars_bucket{le="50.0"} 1.0
agent_question_length_chars_count 1.0
agent_question_length_chars_sum 27.0

# Ba URL lạ cùng vào một nhãn route
http_requests_total{method="GET",route="unmatched",status="404"} 3.0
```

Counter tăng trong một vòng đời process, gauge có thể tăng/giảm, histogram xuất bucket/count/sum để tổng hợp phân bố. `observe_requests` dùng route template, route không khớp được gom thành `unmatched`. Nếu dùng URL thật làm label, bot tạo hàng nghìn URL ngẫu nhiên sẽ tạo hàng nghìn time series; cardinality và lượng RAM lưu metrics tăng theo. Không đưa request_id/user_id/câu hỏi vào labels.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | [Agent v1](reports/eval_v1.json) | [Agent v2](reports/eval_v2.json) | [Agent v2 sau sửa KB](reports/eval_v2_fixed.json) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.30% (21/23) | 100.00% (23/23) |
| Avg score | 0.0578 | 0.9130 | 1.0000 |
| Avg tokens / câu | 57.1 | 109.1 | 113.4 |
| Tổng cost (USD) | 0.000404 | 0.000762 | 0.000788 |
| Cost / câu đúng (USD) | 0.00040395 | 0.00003627 | 0.00003427 |
| Latency p50 / p95 (ms) | 157.6 / 193.1 | 184.9 / 224.7 | 190.6 / 218.5 |
| Lỗi HTTP/kết nối | 0 | 0 | 0 |
| Quality gate của lần chạy | FAIL (ngưỡng 80%) | PASS (ngưỡng 80%, 0 regression so với v1) | **PASS (ngưỡng 100%, 0 regression so với v2)** |

Tổng cost được script làm tròn 6 chữ số thập phân; cost/câu đúng tính từ tổng chưa làm tròn rồi lưu 8 chữ số, nên chia các số hiển thị có thể lệch nhẹ. Tất cả là chi phí mô phỏng theo bảng giá mock, không phát sinh phí LLM thật.

**Những câu v2 trả lời sai ban đầu và cách sửa:**

| ID | Keyword thiếu trước sửa | Đã sửa trong `develop/utils/mock_llm.py` |
|---|---|---|
| security-02 | token, hết hạn, chữ ký | Thêm entry `jwt`, giải thích JWT là token có chữ ký và hạn dùng, so với API key cố định |
| scaling-03 | cpu, memory, custom metrics | Thêm entry `hpa/kubernetes/autoscal`, nêu HPA scale pod theo CPU, memory hoặc custom metrics |

Hai câu đều từ score 0 lên 1.0; toàn bộ 23 câu sau sửa có score 1.0. Không sửa golden dataset hoặc logic chấm; hash trước/sau được đối chiếu. Đã dừng và khởi động lại v2 để nạp KB mới.

**Trade-off:** v2 thêm retrieval và context nên tăng tokens/tổng cost so với v1, đồng thời tăng số câu đúng từ 1 lên 21, rồi 23. V2 fixed dùng 113.4 token/câu so với 57.1 của v1, nhưng cost/câu đúng giảm từ 0.00040395 xuống 0.00003427 USD. Chi phí mỗi request thấp của v1 chưa phản ánh việc chỉ có một câu đạt. Sau sửa KB, tổng cost tăng 0.000762 → 0.000788 USD nhưng cost/câu đúng tiếp tục giảm vì có thêm hai câu đạt.

p95 đo được v1/v2/fixed là 193.1/224.7/218.5 ms. Mẫu chỉ 23 câu, có jitter và slow rate 3%; không quy toàn bộ chênh lệch latency cho KB hoặc coi đây là kiểm định hiệu năng có ý nghĩa thống kê.

### 3.1 Quality gate cho CI

Đã viết [workflow eval.yml](.github/workflows/eval.yml): checkout, Python 3.11, cài requirements, khởi động v2, chờ readiness, chạy eval rồi upload report/log kể cả khi fail. CI tắt upstream error và slow injection để việc chấm chất lượng ổn định.

```bash
python eval/run_eval.py --url http://localhost:8002 \
  --min-accuracy 1.0 --baseline reports/eval_v2.json --out reports/eval_ci.json
```

Ngưỡng 100% chặt hơn yêu cầu 85% của Exercise 7.3. Script trả exit 1 nếu accuracy dưới ngưỡng hoặc có câu baseline đạt mà hiện tại không đạt. `set -euo pipefail` làm step/job fail; trap dừng server khi kết thúc. Đã chạy nguyên shell step của workflow trên local với virtualenv trong PATH; output: [ci-local.txt](06-lab-complete/benchmark-observability/develop/reports/ci-local.txt).

Chưa push/chạy workflow trên GitHub. Muốn GitHub thực sự chặn merge phải cấu hình branch protection/ruleset yêu cầu status check của job này; chỉ thêm YAML không tự bật quy tắc đó.

---

## 4. Observability stack (production, CP8)

Chạy stack local `k5-day14-observability`: Nginx 1.28, Prometheus 3.16.0, Grafana 13.2.4, Jaeger 2.23.0, Locust 2.47.0. Docker 29.9.3, 16 CPU, RAM Docker 8,174,555,136 bytes. Mỗi agent giới hạn 0.5 CPU / 256 MB và **1 Uvicorn worker** để metrics không bị chia giữa process. [Thông tin Docker](reports/cp8-docker-environment.txt).

Đã thêm `PYTHONUSERBASE=/home/agent/.local` trong Dockerfile để Python tìm đúng packages đã copy khi user có home `/app`. Đã đồng bộ hai entry JWT/HPA từ KB develop sang production. Sau thực nghiệm, tắt fault injection và chạy eval production qua Nginx: **23/23, 100%, 0 regression**, [JSON](reports/cp8-eval-production.json), [output](reports/cp8-eval-production.txt).

### 4.1 Screenshot và đọc dashboard (Exercise 7.4)

- [x] [Grafana có tải và Golden Signals](screenshots/grafana-dashboard.png).
- [x] [Trace chậm trong Jaeger](screenshots/jaeger-slow-trace.png).
- [x] [Trace lỗi có event exception](screenshots/jaeger-error-trace.png).
- [x] [Prometheus: hai alert lỗi/latency cùng firing](screenshots/prometheus-alert-firing.png).

Bốn ảnh chụp trực tiếp các UI local đang chạy bằng trình duyệt headless riêng; không phải ảnh mô phỏng hoặc số liệu dựng. Không dùng phiên đăng nhập/profile trình duyệt cá nhân.

**p95 và average:** [snapshot Prometheus](reports/cp8-baseline-metrics.json), lúc 17:38:57 GMT+7: p95 **293.85 ms**, avg **234.72 ms**. Ảnh Grafana chụp ngay sau đó hiển thị p95 293.73 ms, traffic 56.8 req/s, error rate 0.98%, in-flight 21 và 3 instance up. Giá trị ảnh/API có thể lệch nhẹ theo thời điểm scrape/refresh. Khoảng cách giữa avg và p95 cho thấy phân bố không đồng đều; p99 còn nhạy hơn với 3% slow request.

**Load balancing:** snapshot `sum by(instance)(rate(http_requests_total{job="agent",route="/ask"}[1m]))` ghi 172.18.0.5:8000: **18.22 req/s**; 172.18.0.8:8000: **17.58 req/s**; 172.18.0.9:8000: **17.66 req/s**. Ba instance được chia traffic gần đều. Lần thực nghiệm này dùng 3 instance của benchmark scaling, thay cho ví dụ 2 instance trong bài đọc.

**Tokens:** input **4111.94 token/s**, output **2153.35 token/s**. Input gồm system prompt, context retrieval và câu hỏi; output chỉ là câu trả lời. Panel Tokens/s có thể vẽ stacked, nên chiều cao đường phía trên không phải giá trị riêng của một series.

**Public metrics:** `GET http://localhost:8080/metrics` trả **404** do Nginx chặn đúng endpoint này; Prometheus scrape trực tiếp từng agent qua network nội bộ. [Output kiểm tra](reports/cp8-metrics-access.txt).

### 4.2 Thí nghiệm fault injection và alert (Exercise 7.6)

Đã áp dụng hai thay đổi A/B trong **cùng một lượt kết hợp**, giữ 3 agent, model small và tạo tải 30 users / ramp 5 trong 4 phút. Dùng rule gốc, không giảm ngưỡng hoặc thời gian `for`. Đây là quan sát fault kết hợp, không phải hai phép đo cô lập nguyên nhân.

| Thay đổi | Alert thực tế | Điều kiện / for | Từ lệnh đổi config đến lần đầu quan sát firing | Panel phản ánh |
|---|---|---|---|---|
| A: `MOCK_ERROR_RATE=0.2` | AgentHighErrorRate | error rate > 5%, liên tục 1 phút | **82.67 giây** | Error rate; LLM calls error |
| B: `MOCK_SLOW_RATE=0.3` | AgentHighLatencyP95 | p95 > 1 giây, liên tục 2 phút | **142.90 giây** | p95/p99; LLM latency |

[Config và timestamp đổi](reports/cp8-fault-injection.json), [timeline quan sát 5 giây/lần](reports/cp8-alert-timeline.json), [snapshot cả hai firing](reports/cp8-alerts-both-firing.json). Lúc first firing, error rate trong alert khoảng **18.53%**, p95 khoảng **1.89 giây**. Thời gian gồm khởi động lại agent, DNS/scrape, evaluation và polling; không chỉ là giá trị `for`. Prometheus scrape/evaluate mỗi 5 giây.

Đã chạy `promtool test rules`: **SUCCESS**, [output](reports/cp8-promtool.txt). `LLMCostBurnRateHigh` đã firing từ baseline tải 100 users trước A/B và vẫn hiện trên ảnh; không quy nó cho một thí nghiệm đổi sang model large. [CSV fault](benchmark-results/fault_ab_stats.csv) và [failure breakdown](benchmark-results/fault_ab_failures.csv) còn ghi 184 lỗi /ask 502 và 17 lỗi /health 502 lúc recreate/DNS (17:40:51–17:41:01), sau đó 680 lỗi /ask 503 do mock. Lỗi ở Nginx không nằm trong counter 5xx của agent; cần theo dõi cả tầng proxy hoặc synthetic check.

C và D trong bảng gợi ý (model large, pause instance) không thực hiện; yêu cầu ít nhất hai alert được đáp ứng bằng A/B. E là câu hỏi phân tích, không có số đo đổi v1 trong CP8: chuyển sang v1 có thể làm chất lượng giảm mà hạ tầng vẫn khỏe. Cần golden dataset/quality gate trước deploy và eval định kỳ trên câu hỏi đã kiểm duyệt; CP7 đã cho thấy v1 chỉ đạt 1/23 trong khi metrics hạ tầng không chứa đánh giá đúng/sai.

### 4.3 Debug bằng trace (Exercise 7.5)

Jaeger 2.23 dùng API `/api/v3`; truy vấn khai báo service, khoảng thời gian RFC3339 và search depth. Bộ thu thập bỏ các trace chưa có server span vì batch exporter có thể gửi child span trước. [Script thu trace](scripts/collect_cp8_traces.py) và [tóm tắt dữ liệu](reports/cp8-traces-summary.json).

**Trace chậm:** chọn trace thành công dài nhất trong **191 trace hoàn chỉnh** trả về của truy vấn giới hạn tối đa 200 trace trong giai đoạn fault; không khẳng định đây là trace dài nhất của mọi request.

- `trace_id`: **6711d1947324fe1f016c563706254e29**
- Tổng thời gian server span: **1723.87 ms**.
- Bước LLM `chat mock-llm-small`: **1693.40 ms**, **98.23%** tổng thời gian.
- Retrieval: **26.82 ms**.
- Các span cha `POST /ask` / `agent.run` bao các span con; không cộng mọi span với nhau để tính tổng.

[JSON trace chậm](reports/cp8-slow-trace.json). Dòng log JSON thực tế có cùng trace ID:

```json
{
  "ts": "2026-11-25T10:42:35.407369+00:00",
  "level": "INFO",
  "service": "observable-agent",
  "instance": "b4ef8ac4adfd",
  "event": "llm_call",
  "trace_id": "6711d1947324fe1f016c563706254e29",
  "span_id": "9428902c0cca9bd1",
  "request_id": "78e7212f6e89",
  "model": "mock-llm-small",
  "agent_version": "v2",
  "input_tokens": 76,
  "output_tokens": 39,
  "cost_usd": 0.000035,
  "llm_ms": 1692.9
}
```

**Trace lỗi:** `a7c7125ca07440b11dcbd031083fdfed`, tổng **864.20 ms**; span LLM **836.49 ms**, OTel status ERROR (code 2), event `exception` có `exception.type=utils.mock_llm.LLMError` và thông báo upstream 503.

[JSON trace lỗi](reports/cp8-error-trace.json). Dòng log khớp:

```json
{
  "ts": "2026-11-25T10:42:44.678358+00:00",
  "level": "INFO",
  "service": "observable-agent",
  "instance": "e22d68857857",
  "event": "llm_error",
  "trace_id": "a7c7125ca07440b11dcbd031083fdfed",
  "span_id": "37769f169fb40962",
  "request_id": "7f5987752abc",
  "error": "Upstream LLM error: 503 Service Unavailable (mock)"
}
```

Hai dòng được trích và đối chiếu với [log agent](reports/cp8-agent.log), lưu riêng tại [cp8-trace-log-correlation.json](reports/cp8-trace-log-correlation.json). Token/cost trong log được làm tròn, thời gian sleep mock và span cũng có overhead đo; không bắt buộc các số khác loại bằng nhau tuyệt đối.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Mỗi lượt cùng 100 users, ramp-up 10 user/s, `wait_time=between(0.5,2)`, mock error 1%, slow 3%, model small, 1 worker/container; không fault A/B trong hai lượt này. Kiểm tra replica trước khi chạy: [1 agent](reports/cp8-scale-1-containers.txt), [3 agent](reports/cp8-scale-3-containers.txt). Chờ DNS discovery 12–15 giây sau scale.

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| [1](benchmark-results/scale_1_stats.csv) | 65.62 | 190 | 340 | 1700 | 74/7812 (0.95%) |
| [3](benchmark-results/scale_3_stats.csv) | 65.42 | 190 | 230 | 1700 | 69/7798 (0.88%) |

Các hàng lấy từ **Aggregated** của CSV, gồm cả `POST /ask` và `GET /health` theo tỷ lệ task 10:1; percentile của Locust là bucket làm tròn. Riêng /ask: 1 instance có **59.68 req/s, p95 360 ms, 74/7104 lỗi**; 3 instance có **59.45 req/s, p95 240 ms, 69/7086 lỗi**. Failure là HTTP 503 mock, không coi exit code 1 của Locust vì request lỗi là mất file đo. CSV và log giữ nguyên.

**Giải thích:** p95 aggregate giảm 340 → 230 ms, p99 vẫn 1700 ms và RPS gần như giữ nguyên. Với số user và think time cố định, thêm server không tự nhân throughput lên ba lần. Tail delay do mock LLM vẫn còn; trace quan sát có 98.23% thời gian ở bước LLM. Kết quả phù hợp với workload đang chờ LLM và giới hạn tải client, nhưng chỉ có một lượt mỗi cấu hình nên không kết luận nhân quả đầy đủ về CPU/I/O.

**Sửa cách chạy để giữ đúng replica:** Compose `run locust` có thể tự khởi động dependency và áp lại mặc định 2 replica. Lượt preflight gặp tình trạng này đã bị loại khỏi số liệu cuối. Các lượt chính thức dùng `--no-deps`, đã đối chiếu container count; không thay CSV 2 replica thành nhãn 1/3.

```bash
# Chạy trong production/, dùng đúng project cho mọi lệnh:
docker compose -p k5-day14-observability up -d --build --scale agent=1
docker compose -p k5-day14-observability run --no-deps --rm locust \
  -f /mnt/locust/locustfile.py --host http://nginx --headless -u 100 -r 10 -t 2m \
  --csv /mnt/results/scale_1
docker compose -p k5-day14-observability up -d --no-deps --scale agent=3 agent
# Chờ discovery cập nhật rồi chạy tương tự với --csv /mnt/results/scale_3.
```

[Summary máy đọc được](reports/cp8-locust-summary.json), [log scale 1](reports/cp8-locust-scale-1.log), [log scale 3](reports/cp8-locust-scale-3.log). Toàn bộ CSV có ở cả `production/benchmark-results/` và `benchmark-results/` gốc repo.

---

## 6. Kết luận

1. Percentile cần được xem cùng error rate và throughput: CP7 concurrency 100 vượt SLO dù tỷ lệ lỗi thấp; CP8 scale thêm instance cải thiện p95 nhưng p99 vẫn chịu slow LLM.
2. Metrics, trace và log trả lời các câu hỏi khác nhau: dashboard phát hiện thay đổi, span xác định bước LLM chiếm thời gian, trace_id liên kết tới đúng sự kiện JSON.
3. Alert có cửa sổ đo, `for` và độ trễ quan sát; chất lượng câu trả lời cần eval riêng. Model nhỏ cũng có thể vượt cost burn-rate khi throughput cao.

Nếu vận hành thật, cần metric ở tầng Nginx/synthetic để thấy lỗi proxy, eval chất lượng theo phiên bản, retrieval miss và cost/câu đúng. Các đề xuất thêm này chưa được triển khai ngoài những phần đã đo trong lab.

**Tình trạng cuối:** CP7/CP8 hoàn thành, đã lưu đủ 10 JSON bắt buộc, CSV scale 1/3, 7 ảnh deploy/observability, log và trace. Đã chụp ảnh trước khi `docker compose -p k5-day14-observability down -v` và đóng trình duyệt headless riêng. Deployment Railway vẫn giữ online; [kiểm tra public mới nhất](reports/submission-public-checks.json) đạt 200/200/401/200, [script chấm cuối](reports/submission-production-ready.txt) PASS 12/12, 42/42 checks. Xem [SUBMISSION_AUDIT.md](SUBMISSION_AUDIT.md) để phân biệt hồ sơ local sẵn sàng commit với trạng thái đã push lên GitHub.
