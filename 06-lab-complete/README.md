# Part 6 — Final Project: Production-ready AI Agent

Agent đã được triển khai từ bản khung, kết hợp cấu hình môi trường, API key, Redis, rate limit, cost guard, log JSON và graceful shutdown.

CP5 đã đạt **PASS 12/12, 41/41 checks** ngày 25/11/2026. Output đầy đủ: [cp5-production-ready.txt](../reports/cp5-production-ready.txt). Đây là kiểm tra local và cấu hình deploy; URL cloud được thực hiện riêng ở CP6.

CP6 đã deploy tại **https://agent-production-702ecd1c.up.railway.app**, agent và Redis Online, bốn kiểm tra public đạt 200/200/401/200. Script chấm có `--public-url` đạt **12/12, 42/42 checks**. Xem [DEPLOYMENT.md](../DEPLOYMENT.md) để biết cấu hình cloud, cách kiểm tra và bằng chứng; chỉ dùng Trial credit, không nâng cấp gói. Railway hiện deprecated tùy chọn file TOML cũ nên health check cloud đã được đặt trực tiếp trên service; vẫn giữ TOML theo yêu cầu chấm lab.

Bài chỉ được tính hoàn thành khi script chấm báo **`PASS 12/12`**:

```bash
pip install -r requirements.txt
python check_production_ready.py
```

---

## Checklist Deliverable

- [x] Dockerfile (multi-stage, đo được 274 MB)
- [x] docker-compose.yml (agent + redis)
- [x] .dockerignore
- [x] Health check endpoint (`GET /health`)
- [x] Readiness endpoint (`GET /ready`)
- [x] API Key authentication
- [x] Rate limiting
- [x] Cost guard
- [x] Config từ environment variables
- [x] Structured logging
- [x] Graceful shutdown
- [x] Cấu hình Railway sẵn sàng cho CP6

---

## Script chấm dựa vào những tiêu chí dưới đây

Script tự khởi động agent của bạn, gọi API thật, build và chạy Docker image. Để chấm được, agent phải tuân theo các quy ước sau:

| Hạng mục | Yêu cầu |
|----------|---------|
| Điểm vào | `app/main.py` có biến `app` (FastAPI), chạy được bằng `uvicorn app.main:app --workers 2` từ thư mục này |
| `GET /health` | Luôn trả **200** khi process còn chạy, kể cả khi Redis chưa kết nối được |
| `GET /ready` | **200** khi sẵn sàng; **503** khi Redis (`REDIS_URL`) không kết nối được |
| `POST /ask` | Body JSON `{"question": "..."}` (được phép có thêm `user_id`) → **200** |
| API key | Header `X-API-Key` phải trùng biến `AGENT_API_KEY`; thiếu hoặc sai → **401** |
| Rate limit | Tối đa `RATE_LIMIT_PER_MINUTE` request / 60 giây cho mỗi API key; vượt → **429** (nên có header `Retry-After`). State lưu trong **Redis**, vẫn còn sau khi restart agent |
| Cost guard | Tổng chi phí vượt `DAILY_BUDGET_USD` (hoặc `MONTHLY_BUDGET_USD`) → **402** |
| Biến môi trường | Đọc từ env: `AGENT_API_KEY`, `REDIS_URL`, `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD` / `MONTHLY_BUDGET_USD`, `PORT`, `ENVIRONMENT`. Liệt kê đủ trong `.env.example`. Script chạy với `ENVIRONMENT=staging` |
| Log | Mỗi dòng log của app là **1 JSON object hợp lệ** (log của uvicorn không tính) |
| Graceful shutdown | Nhận SIGTERM khi đang có request → request đó vẫn trả 200, process tự thoát với exit code 0. Trong Docker, `docker stop` phải xong trong < 10 giây |
| Docker image | Multi-stage, base slim, user non-root, có `HEALTHCHECK`, < 500 MB. `CMD` lắng nghe theo biến `PORT` (mặc định 8000), uvicorn là PID 1. Container khởi động được khi **không có** Redis |
| Compose | Một service build từ `Dockerfile` + một service dùng image `redis:*`; agent có `REDIS_URL` trỏ tới service Redis và `depends_on` nó |
| `.dockerignore` | Loại trừ `.env`, `__pycache__`, `venv` |
| Deploy config | `railway.toml` (builder `DOCKERFILE`, `healthcheckPath = "/health"`) **hoặc** `render.yaml` (`type: web`, `healthCheckPath: /health`, secret dùng `generateValue` / `sync: false`) |

---

## Cấu trúc triển khai

```
06-lab-complete/
├── app/
│   ├── main.py           # Routes, JSON logging, lifespan; sync endpoint chạy trong thread pool
│   ├── config.py         # Env/.env; kiểm tra cấu hình, không ghi cứng key
│   ├── auth.py           # X-API-Key, constant-time comparison → 401
│   ├── rate_limiter.py   # Redis sorted set + Lua atomic → 429
│   ├── cost_guard.py     # Giữ trước/quyết toán ngân sách ngày UTC → 402
│   └── redis_client.py   # Lazy connection, timeout, fail closed → 503
├── utils/mock_llm.py     # Mock LLM — có sẵn, không cần sửa
├── Dockerfile            # Multi-stage slim, non-root, PID 1 uvicorn, PORT từ env
├── docker-compose.yml    # Agent + Redis AOF, volume, noeviction
├── .dockerignore         # Loại secrets, venv, cache và Part 7
├── .env.example          # Cấu hình mẫu, API key để trống
├── railway.toml          # DOCKERFILE + /health; deploy với service root ở thư mục này
├── render.yaml           # Chỉ comment; lựa chọn deploy là Railway
├── tests/test_shared_limits.py # Integration tests với Redis thật
├── requirements.txt      # Có sẵn
├── check_production_ready.py   # Script chấm — không sửa
└── benchmark-observability/    # Part 7 — làm sau khi xong Part 6
```

Rate limit dùng cửa sổ trượt 60 giây theo hash API key và Redis TIME. Ngân sách dùng chung cho service theo `ENVIRONMENT`, reset bằng key ngày UTC; tiền lưu bằng số nguyên nano-USD. Trước mỗi lần gọi mock, hệ thống giữ trước chi phí input và output dài nhất có thể trong `MOCK_RESPONSES`, sau đó hoàn phần chênh lệch theo câu trả lời thực tế. Token được ước tính bằng số từ nhân 2, phục vụ mock của lab. Khi thay bằng LLM thật cần dùng token usage từ nhà cung cấp và giới hạn output tương ứng.

Nếu process bị kill hoặc mất Redis sau khi giữ tiền, phần giữ chưa quyết toán còn lại để tránh tiêu không được ghi nhận; có thể cần cơ chế đối soát cho production thực tế. Key cũ giữ tới hết ngày kế tiếp để request chạy qua nửa đêm quyết toán đúng ngày. Redis không tự fallback sang RAM.

---

## Chạy local

```bash
pip install -r requirements.txt
cp -n .env.example .env
# Điền AGENT_API_KEY bằng key local ngẫu nhiên của bạn trong .env.
# Không commit .env. ENVIRONMENT=production bắt buộc có key.

# Chạy nhanh không cần Docker (cần Redis riêng nếu muốn test rate limit thật)
uvicorn app.main:app --reload

# Chạy cả agent + redis
docker compose -p k5-day14-final up --build

# Chạy ở terminal khác, cùng thư mục và virtualenv:
AGENT_API_KEY=$(python -c 'from dotenv import dotenv_values; print(dotenv_values(".env")["AGENT_API_KEY"])')
curl http://localhost:8000/health
curl -X POST http://localhost:8000/ask \
     -H "X-API-Key: $AGENT_API_KEY" -H "Content-Type: application/json" \
     -d '{"question": "What is deployment?"}'
unset AGENT_API_KEY
```

Chọn chạy local hoặc Compose; dừng server cũ trước vì cùng dùng cổng 8000. Sau khi chạy Compose, dọn bằng `docker compose -p k5-day14-final down` (thêm `-v` nếu chủ động muốn xóa cả dữ liệu Redis của lab).

---

## Chấm bài

```bash
python check_production_ready.py                 # chấm đầy đủ — cần Docker đang chạy
python check_production_ready.py --skip-docker   # chế độ nhanh khi đang làm (bỏ build image)
python check_production_ready.py --static-only   # chỉ đọc file, không chạy agent
python check_production_ready.py --public-url https://your-app.railway.app   # thêm kiểm tra URL đã deploy
```

Integration tests bổ sung (cần Redis thật theo `REDIS_URL`; dùng key prefix riêng, không FLUSHDB):

```bash
python -m unittest discover -s tests -v
```

Máy Windows này chưa kết nối Docker daemon từ Ubuntu. Lần chấm đầy đủ dùng container Linux với requirements của Part 6, Docker CLI và socket Docker Desktop, giữ nguyên script chấm. Từ gốc repo, PowerShell:

```powershell
docker build -f reports/cp5-checker.Dockerfile -t k5-day14-cp5-checker 06-lab-complete
$cp5Workspace = (Get-Location).Path
docker run --rm --network host --mount "type=bind,source=$cp5Workspace,target=/workspace,readonly" --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock k5-day14-cp5-checker python check_production_ready.py
```

Container này chỉ là công cụ chấm local, có quyền dùng Docker daemon để script tự build/chạy/dọn các container kiểm tra. Image agent production không chứa Docker CLI và chạy bằng user `agent`.

- Kết quả in theo từng tiêu chí: ✅ đạt · ❌ chưa đạt · ⚠️ chưa kiểm tra được.
- **Chỉ PASS khi cả 12 tiêu chí ✅.** Mục ⚠️ (vd máy chưa bật Docker) cũng tính là chưa đạt, nên khi nộp bài phải chạy chế độ đầy đủ.
- Lần đầu chạy, script build Docker image nên mất vài phút. Bài test stateless cần Redis: script dùng `REDIS_URL` nếu có, không thì tự bật container `redis:7-alpine` tạm thời.

---

## Deploy

**Railway**

```bash
npm i -g @railway/cli
railway login
railway init
railway variables set AGENT_API_KEY=your-secret-key
railway up
railway domain        # nhận public URL
```

Chọn service root `06-lab-complete/`, đặt `AGENT_API_KEY` bằng secret trên nền tảng và `REDIS_URL` trỏ tới Redis cloud. Kiểm tra cả `/health` và `/ready` sau deploy. Chưa có Render Blueprint; nếu đổi nền tảng cần viết `render.yaml` trước.

Sau khi deploy: `python check_production_ready.py --public-url <URL>` và ghi URL vào `DEPLOYMENT.md` (xem [DAY14_DELIVERY_CHECKLIST.md](../DAY14_DELIVERY_CHECKLIST.md)).

---

## Part 7 — Benchmark & Observability

Agent đã chạy được, bước tiếp theo là đo xem nó **nhanh** và **đúng** tới đâu, rồi **giám sát** khi chạy thật:

```bash
cd benchmark-observability
```

| Thư mục | Nội dung |
|---------|----------|
| `develop/` | Agent có `/metrics`, load test (p50/p95/p99, SLO), eval trên golden dataset + quality gate |
| `production/` | Docker Compose: agent x2 + Nginx + Prometheus + Grafana + Jaeger + Locust, 4 alert rules |

Hướng dẫn đầy đủ: [benchmark-observability/README.md](benchmark-observability/README.md). Nộp kèm `BENCHMARK_REPORT.md` theo [mẫu](benchmark-observability/BENCHMARK_REPORT_TEMPLATE.md).
