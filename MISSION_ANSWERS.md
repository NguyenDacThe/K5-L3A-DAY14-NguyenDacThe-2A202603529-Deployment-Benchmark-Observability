# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns phát hiện trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets ngay trong mã nguồn (`app.py` dòng 17–18):**
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`.
   - Khi push code lên GitHub (đặc biệt repo public), API key và mật khẩu database bị lộ ngay lập tức và vẫn tồn tại trong lịch sử Git kể cả khi xóa ở commit sau.
   - **Bản `production` đã sửa:** `production/config.py` (dòng 27, 32) đọc qua `os.getenv("OPENAI_API_KEY", "")` và `os.getenv("AGENT_API_KEY", "")`, kèm `Settings.validate()` fail-fast khi `ENVIRONMENT=production` mà thiếu `AGENT_API_KEY`; mẫu biến môi trường đặt ở `production/.env.example`.

2. **Không quản lý cấu hình theo môi trường & bật cứng `DEBUG = True` (`app.py` dòng 21–22, 53):**
   - `DEBUG = True`, `MAX_TOKENS = 500`, và `reload=True` trong `uvicorn.run(...)` được gán cứng. Chế độ reload/debug làm tốn tài nguyên, dễ lộ thông tin lỗi nội bộ và không thay đổi được giữa dev/staging/production nếu không sửa code.
   - **Bản `production` đã sửa:** `production/config.py` (dòng 17–35) tập trung toàn bộ cấu hình vào class `Settings` đọc từ biến môi trường; `production/app.py` (dòng 198) chỉ bật `reload=settings.debug` khi `DEBUG=true`.

3. **Dùng `print()` thay cho structured logging và làm lộ secret ra log (`app.py` dòng 33–38):**
   - Dùng `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` in thẳng API key ra stdout dưới dạng plain text, không có timestamp, log level hay định dạng JSON để hệ thống thu thập log (Loki, Datadog...) phân tích.
   - **Bản `production` đã sửa:** `production/app.py` (dòng 28–32, 49–55, 111–122) cấu hình `logging` theo format JSON và chỉ log metadata an toàn (`question_length`, `client_ip`, `response_length`), tuyệt đối không log secret.

4. **Thiếu Health Check & Readiness Check (`app.py` dòng 42–43):**
   - Không có `GET /health` hay `GET /ready`. Khi deploy lên cloud hoặc chạy sau Load Balancer, nền tảng không thể kiểm tra tiến trình còn sống hay đã sẵn sàng nhận traffic để tự động restart hoặc điều hướng request.
   - **Bản `production` đã sửa:** `production/app.py` bổ sung `GET /health` (dòng 135–149, liveness probe trả uptime/version/environment/timestamp) và `GET /ready` (dòng 152–161, readiness probe trả `503` khi `is_ready` là `False`).

5. **Bind cứng `host="localhost"` và `port=8000` (`app.py` dòng 51–52):**
   - `host="localhost"` (`127.0.0.1`) chỉ nhận kết nối từ bên trong chính máy/container đó, khi đóng gói Docker hoặc đưa lên cloud sẽ không nhận được request từ ngoài. `port=8000` cố định không đọc biến `PORT` do các nền tảng PaaS (Railway/Render) cấp phát tự động.
   - **Bản `production` đã sửa:** `production/config.py` (dòng 17–18) mặc định `HOST="0.0.0.0"` và đọc `PORT` từ env; `production/app.py` (dòng 196–197) truyền `host=settings.host, port=settings.port`.

6. **Không xử lý Graceful Shutdown (`SIGTERM`) & thiếu kiểm soát input/CORS:**
   - Bản `develop` tắt đột ngột khi nhận tín hiệu dừng, có thể cắt ngang request đang xử lý; đồng thời nhận `question` qua query parameter (`POST /ask?question=...`) và chưa cấu hình CORS.
   - **Bản `production` đã sửa:** Dùng `lifespan` (dòng 39–68) đặt `is_ready = False` khi shutdown để hoàn thành request đang chạy, đăng ký `signal.signal(signal.SIGTERM, handle_sigterm)` (dòng 180–189), đọc JSON body kèm validate trả `422` nếu thiếu `question` (dòng 103–108), và cấu hình `CORSMiddleware` (dòng 77–82).

---

### Exercise 1.2: Kết quả chạy thử bản `develop` và `production`

**Chạy bản `develop` (`01-localhost-vs-production/develop/app.py`):**

* Endpoint `GET /`:
  ```text
  Status: 200
  Body:   {"message":"Hello! Agent is running on my machine :)"}
  ```
* Endpoint `POST /ask?question=Hello`:
  ```text
  Status: 200
  Body:   {"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
  ```
* Endpoint `GET /health`:
  ```text
  Status: 404
  Body:   {"detail":"Not Found"}
  ```
* Log console của bản `develop` (cho thấy rõ lỗi in secret ra stdout):
  ```text
  [DEBUG] Got question: Hello
  [DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
  [DEBUG] Response: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.
  ```

**Chạy bản `production` (`01-localhost-vs-production/production/app.py`):**

* `GET /health` → `200`: `{"status":"ok","uptime_seconds":0.2,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T08:37:07.931135+00:00"}`
* `GET /ready` → `200`: `{"ready":true}`
* `POST /ask` (`{"question": "Hello"}`) → `200`: `{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","model":"gpt-4o-mini"}`
* Log startup cảnh báo rõ khi chưa đặt key thật: `WARNING:root:OPENAI_API_KEY not set — using mock LLM`

---

### Exercise 1.3: Bảng so sánh `develop` vs `production`

| Feature | Develop (`basic`) | Production (`advanced`) | Tại sao quan trọng? |
| :--- | :--- | :--- | :--- |
| **Config** | Hardcode `DEBUG = True`, `MAX_TOKENS = 500` trong code | Đọc từ environment variables qua `Settings` (`config.py`), có `validate()` fail-fast | Tách biệt code và config theo nguyên tắc 12-Factor; thay đổi hành vi giữa dev/staging/prod không cần sửa hay build lại code. |
| **Secrets** | Gán trực tiếp `OPENAI_API_KEY`, `DATABASE_URL` trong `app.py` | Đọc qua `os.getenv(...)`, mẫu đặt trong `.env.example`, `.env` nằm trong `.gitignore` | Tránh rò rỉ thông tin nhạy cảm lên Git/GitHub và dễ xoay vòng (rotate) key độc lập trên từng môi trường. |
| **Host & Port** | `host="localhost"`, `port=8000` cố định, `reload=True` | `HOST` mặc định `0.0.0.0`, `PORT` từ env var, `reload=settings.debug` | `0.0.0.0` cho phép nhận traffic từ ngoài container; đọc `PORT` động là bắt buộc trên Railway/Render/Cloud Run. |
| **Health & Readiness check** | Không có (`GET /health` trả `404`) | Có `GET /health` (liveness) và `GET /ready` (readiness, trả `503` khi chưa sẵn sàng) | Platform dựa vào `/health` để tự restart khi app treo; Load Balancer dựa vào `/ready` để chỉ gửi traffic khi app đã khởi tạo xong. |
| **Logging** | Dùng `print()` plain text và in cả API key ra stdout | Structured JSON logging qua module `logging`, chỉ log metadata không nhạy cảm | Log JSON dễ parse, lọc, tìm kiếm và tạo cảnh báo trên hệ thống giám sát tập trung; không làm lộ secret qua log. |
| **Shutdown** | Tắt đột ngột | `lifespan` context manager + xử lý `SIGTERM` (`handle_sigterm`) | Khi container bị stop/redeploy, app ngừng nhận traffic mới và hoàn tất các request đang xử lý trước khi thoát, tránh lỗi `5xx` cho người dùng. |
| **CORS & Input** | Không có CORS; nhận `question` qua query string | `CORSMiddleware` giới hạn origins/methods; nhận JSON body, trả `422` nếu thiếu `question` | Kiểm soát domain được phép gọi API từ trình duyệt và chuẩn hóa contract JSON cho client/gateway. |

---

## Part 2: Docker

### Exercise 2.1: Phân tích `02-docker/develop/Dockerfile`

1. **Base image là gì?**
   - `python:3.11` (bản Python 3.11 đầy đủ kèm nhiều công cụ hệ thống trên nền Debian, dung lượng rất lớn).
2. **Working directory là gì?**
   - `/app` (đặt bằng chỉ thị `WORKDIR /app`).
3. **Tại sao `COPY requirements.txt` trước khi `COPY` source code (`app.py`)?**
   - Để tận dụng **Docker layer cache**. Docker cache từng layer theo thứ tự từ trên xuống dưới; khi một layer thay đổi, toàn bộ các layer phía sau bị invalidate và chạy lại. Đặt `COPY 02-docker/develop/requirements.txt .` và `RUN pip install --no-cache-dir -r requirements.txt` lên trước `COPY 02-docker/develop/app.py .` giúp bước cài thư viện nặng được tái sử dụng từ cache mỗi khi bạn chỉ sửa code ứng dụng.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - `CMD` định nghĩa lệnh và tham số mặc định khi container khởi động, nhưng **dễ dàng bị ghi đè** nếu người dùng truyền lệnh ở cuối `docker run <image> <lệnh_mới>`.
   - `ENTRYPOINT` định nghĩa tiến trình thực thi cố định của container (khó bị ghi đè trừ khi dùng cờ `--entrypoint`). Khi kết hợp cả hai, `ENTRYPOINT` là lệnh chính còn `CMD` đóng vai trò tham số mặc định truyền vào `ENTRYPOINT`.

---

### Exercise 2.2: Build và chạy thử `my-agent:develop`

Build từ gốc repo (`docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .`), chạy container map cổng `8000:8000` và kiểm tra:

* `GET http://127.0.0.1:8000/` → `200`:
  ```json
  {"message":"Agent is running in a Docker container!"}
  ```
* `GET http://127.0.0.1:8000/health` → `200`:
  ```json
  {"status":"ok","uptime_seconds":2.7,"container":true}
  ```
* `POST http://127.0.0.1:8000/ask?question=What%20is%20Docker%3F` → `200`:
  ```json
  {"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
  ```

---

### Exercise 2.3: Multi-stage build & so sánh dung lượng image

* **Phân tích `02-docker/production/Dockerfile`:**
  * **Stage 1 (`builder`):** Dùng `python:3.11-slim`, cài công cụ biên dịch (`gcc`, `libpq-dev`) và chạy `pip install --no-cache-dir --user -r requirements.txt` vào `/root/.local`.
  * **Stage 2 (`runtime`):** Bắt đầu lại từ `python:3.11-slim` sạch, tạo user non-root `appuser`, chỉ `COPY --from=builder /root/.local /home/appuser/.local` cùng `main.py` và `utils/mock_llm.py`, thiết lập `HEALTHCHECK` và chạy `uvicorn` bằng `appuser`.
  * **Tại sao nhỏ và an toàn hơn:** Image cuối loại bỏ hoàn toàn `gcc`, `libpq-dev`, headers hệ thống và cache build trung gian từ Stage 1, đồng thời không chạy dưới quyền `root`.

* **Kết quả đo thực tế (`docker images my-agent` và `docker image inspect`):**

  | Image | Base / Kiểu build | Disk Usage (`docker images`) | Exact Size (bytes) | Content Size |
  | :--- | :--- | :---: | :---: | :---: |
  | `my-agent:develop` | Single-stage (`python:3.11`) | **1.67 GB** (~1,667.8 MB) | `1,667,784,201` | 426 MB |
  | `my-agent:advanced` | Multi-stage (`python:3.11-slim`) | **240 MB** (~239.8 MB) | `239,815,461` | 57.4 MB |

  * **Chênh lệch:** Giảm **~1,428 MB**, tương đương giảm **85.62%** dung lượng (nhỏ hơn gần **7 lần**).

---

### Exercise 2.4: Docker Compose Stack (`02-docker/production/docker-compose.yml`)

* **Sơ đồ kiến trúc các services & luồng giao tiếp:**

```text
                      Port 80 / 443 (Host)
                               │
                               ▼
                    ┌─────────────────────┐
                    │        nginx        │  (Reverse proxy, rate limit 10r/s,
                    │   (nginx:alpine)    │   security headers, proxy → agent:8000)
                    └──────────┬──────────┘
                               │  network: internal (bridge)
                               ▼
                    ┌─────────────────────┐
                    │        agent        │  (FastAPI + Uvicorn 2 workers, port 8000,
                    │ (multi-stage build) │   không mở port trực tiếp ra host)
                    └───┬─────────────┬───┘
         REDIS_URL      │             │   QDRANT_URL
    redis://redis:6379/0│             │http://qdrant:6333
                        ▼             ▼
          ┌─────────────────┐     ┌──────────────────┐
          │      redis      │     │      qdrant      │
          │ (redis:7-alpine)│     │(qdrant:v1.9.0)   │
          │  vol: redis_data│     │ vol: qdrant_data │
          └─────────────────┘     └──────────────────┘
```

* **Cách giao tiếp giữa các service:**
  * Tất cả 4 service (`nginx`, `agent`, `redis`, `qdrant`) nằm chung trong Docker bridge network `internal` nên gọi nhau trực tiếp qua tên service (Docker DNS: `agent:8000`, `redis:6379`, `qdrant:6333`).
  * Chỉ `nginx` publish cổng `80` và `443` ra ngoài host; `agent`, `redis`, `qdrant` đều cô lập bên trong network `internal`.
  * `agent` có `depends_on` với điều kiện `service_healthy` cho cả `redis` (healthcheck `redis-cli ping`) và `qdrant` (TCP port `6333`).

* **Kết quả chạy stack (`docker compose -p k5-day14-docker -f 02-docker/production/docker-compose.yml ps`) và test qua Nginx:**
  * 4 container khởi chạy: `k5-day14-docker-nginx-1`, `k5-day14-docker-agent-1`, `k5-day14-docker-redis-1` (`healthy`), `k5-day14-docker-qdrant-1` (`healthy`).
  * `GET http://127.0.0.1/` → `200`: `{"app":"AI Agent","version":"2.0.0","environment":"staging"}`
  * `GET http://127.0.0.1/health` → `200`: `{"status":"ok","uptime_seconds":0.3,"version":"2.0.0","timestamp":"2026-11-25T09:19:32.588808"}`
  * `GET http://127.0.0.1/ready` → `200`: `{"ready":true}`
  * `POST http://127.0.0.1/ask` (`{"question": "Explain microservices"}`) → `200`: `{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}`
  * Đã dọn dẹp stack sau khi kiểm tra xong bằng `docker compose -p k5-day14-docker -f 02-docker/production/docker-compose.yml down -v`.

---

## Part 3: Cloud Deployment (CP6)

### Exercise 3.1: Railway — trạng thái triển khai

Đã deploy **agent Part 6** từ `06-lab-complete/` lên Railway cùng Redis, environment `production`, ngày **25/11/2026**. Public URL: **https://agent-production-702ecd1c.up.railway.app**. Không deploy app mẫu Part 3 hoặc Dockerfile Go ở gốc repo.

Project `day14-production-agent` có ID `93b45f7d-c21d-4c37-bcff-a2d81d9e28f3`; agent deployment `a4f5b9cd-a4e4-4b57-b0ba-4eb42bd053c0` và Redis deployment `26b413fb-07d3-40ed-8ca6-a92c63fc02c8` đều `SUCCESS`. Redis template `redis:8.2`, volume 500 MB; agent dùng reference `${{Redis.REDIS_URL}}` qua private network. Redis không có public TCP proxy.

Đã kiểm tra tài khoản trước khi tạo tài nguyên: Trial còn 5 USD/30 ngày, không có phương thức thanh toán hoặc subscription trả phí; không nâng cấp gói. API trả tên plan HOBBY cùng `isTrialing: true` vì Trial dùng quyền tương ứng, không phải đã mua gói. Snapshot sau deploy ghi usage `0.0003125609351851851` USD, credit còn `4.9996874390648145` USD; số này tiếp tục thay đổi khi service chạy. Xem [billing trước](reports/cp6-billing-before.json), [billing sau](reports/cp6-billing-after.json).

**Kiểm tra public lúc 17:06:22 GMT+7:**

| Request | Status thực tế |
| --- | --- |
| `GET /health` | **200**, `status: ok`, `environment: production` |
| `GET /ready` | **200**, `ready: true`, Redis kết nối thật |
| `POST /ask` không key | **401** |
| `POST /ask` có key cloud | **200**, trả answer/usage JSON |

[Report JSON](reports/cp6-public-checks.json) và [output](reports/cp6-public-checks.txt) do [verify_public_deployment.py](06-lab-complete/verify_public_deployment.py) ghi từ request HTTPS thật, không chứa key. Chạy script chấm gốc thêm `--public-url` đạt **PASS 12/12 — 42/42 checks passed**, exit 0; [output đầy đủ](reports/cp6-production-ready.txt).

Đã có [dashboard.png](screenshots/dashboard.png), [running.png](screenshots/running.png) và [test.png](screenshots/test.png). Hai ảnh đầu chụp Railway thật; ảnh test chụp trang báo cáo hiển thị JSON đo thực tế, không phải ảnh dashboard. [DEPLOYMENT.md](DEPLOYMENT.md) ghi đủ URL, service/deployment ID, cấu hình, cách chạy lại và bằng chứng. API key riêng cloud giữ trong `.env.cloud` đã Git ignore, không upload source.

Lần upload đầu từ Windows mount gặp lỗi BuildKit; upload allowlist source từ filesystem Linux-native đã thành công. Railway API hiện từ chối cấu hình đường dẫn TOML cũ, nên đã đặt healthcheck `/health`, timeout 60 giây và restart policy trực tiếp trên service; vẫn giữ TOML theo hợp đồng lab. [Manifest SHA-256](reports/cp6-source-manifest.json) ghi source local đã deploy; chưa commit/push nên không khẳng định phiên bản này đã có trên GitHub.

### Exercise 3.2: So sánh Railway TOML và Render YAML

| Nội dung | Railway | Render |
| --- | --- | --- |
| File | `railway.toml` của lab có `[build]`, `[deploy]`; API hiện hành đã deprecated việc đặt file này, deployment thực tế dùng cấu hình service trực tiếp | `render.yaml`, danh sách `services` và `envVars` của Blueprint |
| Build agent Part 6 | Cấu hình hiện có dùng `builder = "DOCKERFILE"`; Dockerfile cài dependencies và chạy Uvicorn | Với cùng agent cần `runtime: docker` và Dockerfile Part 6; mẫu `03-cloud-deployment/render/render.yaml` đang dùng `runtime: python`, `buildCommand`, `startCommand` cho app mẫu |
| Health check | File lab và service cloud cùng cấu hình `/health`, timeout 60 giây; đã xác nhận qua deployment metadata | `healthCheckPath: /health` nằm trong web service |
| Runtime PORT | Docker CMD đọc `${PORT:-8000}` | Docker CMD cũng phải đọc PORT của service; mẫu Python cũ dùng `$PORT` trong startCommand |
| Redis | Tạo service Redis cùng project, agent dùng reference tới `Redis.REDIS_URL` | Khai báo service Redis/Key Value và nối URL private vào env của web service; không lấy mặc định localhost |
| Secrets | Đặt qua Railway Variables/secret hoặc CLI stdin; không ghi secret trong TOML | Blueprint hỗ trợ `generateValue: true` hoặc `sync: false`; mẫu repo đã minh họa cả hai |
| Phạm vi cấu hình | File hiện tại cấu hình build/deploy cho service agent; Redis được tạo riêng trong project | Blueprint mô tả nhiều service và có thể khai báo region/plan/env cùng trong một YAML |

Tên field health check và cấu trúc file khác nhau vì hai nền tảng có schema riêng; không đổi đuôi file rồi dùng nguyên nội dung. `06-lab-complete/render.yaml` hiện chỉ là comment, chưa bật Blueprint Render. Bảng trên so sánh cấu hình Railway thực tế với mẫu Render đã đọc trong repo, không khẳng định đã deploy lên Render. Tham khảo [Render Blueprint](https://render.com/docs/blueprint-spec), [Railway Redis](https://docs.railway.com/databases/redis) và [Railway chuyển từ TOML sang IaC](https://docs.railway.com/infrastructure-as-code#migrating-from-config-as-code).

### Exercise 3.3: Pipeline Cloud Run (đọc cấu hình, không deploy GCP)

1. `cloudbuild.yaml` mô tả pipeline dùng khi cấu hình Cloud Build trigger cho source: bước `test` cài requirements và chạy `pytest tests/ -v --tb=short`.
2. Bước test hiện chạy `echo` sau `pytest` mà chưa có `set -e`/`&&`, nên cần sửa cách fail-fast nếu sử dụng thật để lỗi pytest không bị mã thoát thành công của echo che mất.
3. `build` chờ `test`, build Docker image gắn tag `$COMMIT_SHA` và `latest`; `push` chờ build rồi đẩy các tag lên `gcr.io/$PROJECT_ID/ai-agent`.
4. `deploy` chờ push, chạy `gcloud run deploy` tại `asia-southeast1`, cấu hình public endpoint, min/max instance 1/10, CPU 1, RAM 512 MiB, timeout 60 giây, env production và secret từ Secret Manager.
5. `service.yaml` mô tả ingress, concurrency 80, tài nguyên, `/health` liveness, `/ready` startup probe và secret reference; nếu dùng cho agent Part 6 cần bổ sung Redis cloud. CP6 chỉ yêu cầu giải thích các file này, chưa tạo tài khoản/tài nguyên GCP.

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

* **API key được kiểm tra ở đâu?**
  * Khai báo `API_KEY = os.getenv("AGENT_API_KEY", ...)` và `api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)` (dòng 35–36).
  * Hàm dependency `verify_api_key` (dòng 39–54) thực hiện kiểm tra giá trị header `X-API-Key`, sau đó được gắn vào endpoint `POST /ask` thông qua `_key: str = Depends(verify_api_key)` (dòng 70). Các endpoint public như `/` và `/health` không gắn dependency này.
* **Điều gì xảy ra nếu thiếu hoặc sai key?**
  * Thiếu header `X-API-Key` → trả về **`401 Unauthorized`** (`"Missing API key..."`).
  * Có header nhưng giá trị không khớp `API_KEY` → trả về **`403 Forbidden`** (`"Invalid API key."`).
* **Làm sao rotate (xoay vòng) key an toàn?**
  * Không hardcode key trong code; nạp key từ biến môi trường / Secret Manager. Khi cần rotate không downtime, hệ thống hỗ trợ đồng thời tập key hợp lệ (vd biến `AGENT_API_KEYS` chứa cả key cũ và key mới), phát hành key mới cho client chuyển dần sang, sau đó gỡ key cũ khỏi env và restart/reload cấu hình.

**Kết quả test bản `develop` (`AGENT_API_KEY=secret-key-123`):**

* **Không có key (`401`):**
  ```http
  HTTP/1.1 401 Unauthorized
  date: Wed, 25 Nov 2026 09:21:32 GMT
  server: uvicorn
  content-length: 67
  content-type: application/json

  {"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
  ```
* **Sai key (`403`):**
  ```http
  HTTP/1.1 403 Forbidden
  date: Wed, 25 Nov 2026 09:21:32 GMT
  server: uvicorn
  content-length: 29
  content-type: application/json

  {"detail":"Invalid API key."}
  ```
* **Đúng key (`200`):**
  ```http
  HTTP/1.1 200 OK
  date: Wed, 25 Nov 2026 09:21:32 GMT
  server: uvicorn
  content-length: 145
  content-type: application/json

  {"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
  ```

---

### Exercise 4.2: JWT Authentication (`04-api-gateway/production/auth.py`)

* **Luồng hoạt động JWT:**
  1. Client gửi `POST /auth/token` kèm `username` / `password` (`student` / `demo123`).
  2. `authenticate_user` xác thực thông tin, `create_token` ký JWT bằng thuật toán `HS256` (`SECRET_KEY` từ `JWT_SECRET`), nhúng `sub` (username), `role`, `iat`, `exp` (hết hạn sau 60 phút).
  3. Các request tới `POST /ask` gửi kèm header `Authorization: Bearer <MASKED>`.
  4. Dependency `verify_token` giải mã và xác minh chữ ký/thời hạn (stateless, không cần truy vấn DB mỗi request): thiếu hoặc hết hạn trả **`401`**, token giả/sai chữ ký trả **`403`**.

* **Kết quả test không có token (`401`):**
  ```http
  HTTP/1.1 401 Unauthorized
  date: Wed, 25 Nov 2026 09:24:37 GMT
  server: uvicorn
  www-authenticate: Bearer
  content-length: 76
  content-type: application/json
  x-content-type-options: nosniff
  x-frame-options: DENY
  x-xss-protection: 1; mode=block
  referrer-policy: strict-origin-when-cross-origin

  {"detail":"Authentication required. Include: Authorization: Bearer <token>"}
  ```

* **Lấy token (`POST /auth/token` với `student` / `demo123`, đã che token):**
  ```json
  {"access_token": "<MASKED>", "token_type": "bearer", "expires_in_minutes": 60, "hint": "Include in header: Authorization: Bearer <MASKED>"}
  ```

---

### Exercise 4.3: Rate Limiting (`04-api-gateway/production/rate_limiter.py`)

* **Thuật toán sử dụng:** **Sliding Window** (cửa sổ trượt). Mỗi `user_id` có một `deque` lưu các mốc thời gian (`timestamp`) của những request gần nhất; mỗi lần kiểm tra `check()`, hệ thống loại bỏ các timestamp cũ hơn `now - window_seconds` rồi so sánh `len(window) >= max_requests`.
* **Giới hạn mặc định:**
  * User thường (`rate_limiter_user`, vd `student`): **10 requests / 60 giây**.
  * Admin (`rate_limiter_admin`, vd `teacher`): **100 requests / 60 giây**.
* **Cách bypass / nới limit cho admin:** Trong `app.py` (dòng 141) kiểm tra `role == "admin"` để chuyển sang `rate_limiter_admin` (100 req/phút); nếu muốn bypass hoàn toàn cho admin thì bỏ qua bước gọi `limiter.check(username)` khi `role == "admin"`.

**Kết quả test vòng lặp 12 request liên tiếp bằng JWT của `student` (token đã che):**

* **Request 1 (`200 OK`):**
  ```http
  HTTP/1.1 200 OK
  date: Wed, 25 Nov 2026 09:24:37 GMT
  server: uvicorn
  content-length: 210
  content-type: application/json
  x-content-type-options: nosniff
  x-frame-options: DENY
  x-xss-protection: 1; mode=block
  referrer-policy: strict-origin-when-cross-origin

  {"question":"Test 1","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","usage":{"requests_remaining":9,"budget_remaining_usd":2.1e-05}}
  ```
* Request 2 → Request 9: đều trả `HTTP/1.1 200 OK`.
* **Request 10 (`200 OK`, hết quota trong cửa sổ 60s):**
  ```http
  HTTP/1.1 200 OK
  date: Wed, 25 Nov 2026 09:24:39 GMT
  server: uvicorn
  content-length: 189
  content-type: application/json
  x-content-type-options: nosniff
  x-frame-options: DENY
  x-xss-protection: 1; mode=block
  referrer-policy: strict-origin-when-cross-origin

  {"question":"Test 10","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":0,"budget_remaining_usd":0.000191}}
  ```
* **Request 11 (`429 Too Many Requests`):**
  ```http
  HTTP/1.1 429 Too Many Requests
  date: Wed, 25 Nov 2026 09:24:39 GMT
  server: uvicorn
  x-ratelimit-limit: 10
  x-ratelimit-remaining: 0
  x-ratelimit-reset: 1795598739
  retry-after: 59
  content-length: 98
  content-type: application/json
  x-content-type-options: nosniff
  x-frame-options: DENY
  x-xss-protection: 1; mode=block
  referrer-policy: strict-origin-when-cross-origin

  {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
  ```
* **Request 12 (`429 Too Many Requests`):** tiếp tục bị chặn với `retry-after: 59`.

---

### Exercise 4.4: Cost Guard & Tại sao cần cả Rate Limit lẫn Cost Guard

* **Cách hoạt động của Cost Guard (`04-api-gateway/production/cost_guard.py`):**
  1. **Kiểm tra trước khi gọi LLM (`check_budget`):**
     * Kiểm tra tổng chi phí toàn hệ thống trong ngày (`_global_cost >= global_daily_budget_usd`, mặc định `$10.0`) → nếu vượt trả **`503 Service Unavailable`**.
     * Kiểm tra chi phí của từng user (`record.total_cost_usd >= daily_budget_usd`, mặc định `$1.0`) → nếu vượt trả **`402 Payment Required`**.
     * Nếu đạt từ `80%` ngân sách (`warn_at_pct = 0.8`) → ghi `logger.warning(...)` để cảnh báo sớm.
  2. **Ghi nhận sau khi gọi LLM (`record_usage`):**
     * Cộng dồn `input_tokens`, `output_tokens` và tính tiền theo đơn giá (`PRICE_PER_1K_INPUT_TOKENS = 0.00015`, `PRICE_PER_1K_OUTPUT_TOKENS = 0.0006`).
  3. **Triển khai trong Production (Stateless với Redis):**
     * Bản demo lưu trong RAM (`self._records`) nên mất state khi restart và không đồng bộ giữa nhiều instance. Khi đưa vào production (như Part 6), chuyển sang lưu trong **Redis** theo key chứa chu kỳ ngày/tháng (ví dụ `budget:{user_id}:{YYYY-MM-DD}` hoặc `YYYY-MM`), dùng `INCRBYFLOAT` để cộng chi phí atomic và đặt `EXPIRE` tự hết hạn sau chu kỳ.

* **Vì sao phải kết hợp cả Rate Limit và Cost Guard?**
  * **Rate Limit bảo vệ tốc độ (throughput/RPM):** chặn spam, DDoS, vòng lặp vô hạn từ client và ngăn quá tải CPU/worker. Tuy nhiên, Rate Limit không biết mỗi request tốn bao nhiêu token — một user chỉ gọi 2–3 request/phút (nằm dưới rate limit) nhưng gửi prompt rất dài hoặc sinh output lớn vẫn có thể làm hóa đơn LLM tăng vọt.
  * **Cost Guard bảo vệ tiền (budget USD):** chặn chi tiêu vượt trần theo ngày/tháng (`402`), nhưng lại không ngăn được hàng nghìn request nhẹ đập vào server cùng lúc khi tổng tiền chưa chạm ngưỡng. Kết hợp cả hai mới bảo vệ trọn vẹn cả **tài nguyên hạ tầng** lẫn **chi phí vận hành**.

---

### Kiểm tra lại CP3 và lệnh tái hiện

Đã chạy lại trên Python trong WSL2 ngày 25/11/2026. Output `curl -i` đầy đủ nằm trong [reports/cp3-security.txt](reports/cp3-security.txt); JWT và phần hint chứa token đã được che. Hai server kiểm tra dùng cổng localhost do hệ điều hành cấp để tránh chiếm cổng của ứng dụng đang chạy, và đã được dừng sau kiểm tra.

| Trường hợp | Kết quả thực tế |
| --- | --- |
| Develop: thiếu / sai / đúng API key | 401 / 403 / 200 |
| Production: thiếu JWT | 401, có `WWW-Authenticate: Bearer` |
| Đăng nhập `student` tại `POST /auth/token` | 200, nhận JWT |
| Vòng lặp 12 request trong cùng cửa sổ 60 giây | Request 1–10: 200; request 11–12: 429, `Retry-After: 59` |
| `GET /me/usage` sau vòng lặp | 200, `requests: 10`, `cost_usd: 0.000174`, còn `0.999826` USD |
| `student` gọi `GET /admin/stats` | 403 (`Admin only`) |
| Cost guard: chưa dùng ngân sách | Cho phép |
| Cost guard: dùng `0.00075` USD, budget user `0.0005` USD | Ném `HTTPException` 402 |
| Cost guard: dùng `0.00075` USD, budget toàn hệ thống `0.0005` USD | Ném `HTTPException` 503 |

Hai kiểm tra vượt budget gọi trực tiếp các instance `CostGuard` riêng với `record_usage(..., 1000, 1000)` rồi `check_budget(...)`, không phải response HTTP từ server và không thay đổi budget mặc định của code mẫu. Các số USD là phép tính theo đơn giá mock trong repo, không phát sinh phí LLM thật.

**Lệnh tự chạy lại Exercise 4.1 (Bash trong WSL2, từ gốc repo):**

```bash
source .venv/bin/activate
cd 04-api-gateway/develop
AGENT_API_KEY=secret-key-123 uvicorn app:app --host 127.0.0.1 --port 8000
```

Ở terminal WSL2 khác:

```bash
curl -i -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' -d '{"question":"Hello"}'
curl -i -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' -H 'X-API-Key: wrong-key' \
  -d '{"question":"Hello"}'
curl -i -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' -H 'X-API-Key: secret-key-123' \
  -d '{"question":"Hello"}'
```

**Exercise 4.2–4.3:** dừng server develop bằng Ctrl+C. Trong terminal đã kích hoạt `.venv`, chạy `cd ../production` rồi `uvicorn app:app --host 127.0.0.1 --port 8000`. Terminal WSL2 thứ hai cũng kích hoạt `.venv`, sau đó chạy:

```bash
# Lưu JWT vào biến, không in token hoặc hint ra màn hình.
TOKEN=$(curl -fsS -X POST http://localhost:8000/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"student","password":"demo123"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

# Thiếu JWT: 401; không tiêu quota của student.
curl -i -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' -d '{"question":"Hello"}'

# Chạy ngay sau khi server production vừa khởi động:
# 1–10 trả 200, 11–12 trả 429. Request đầu cũng là test dùng JWT của 4.2.
for i in $(seq 1 12); do
  printf '\nRequest %s\n' "$i"
  curl -sS -i -X POST http://localhost:8000/ask \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' -d "{\"question\":\"Test $i\"}"
done
curl -i http://localhost:8000/me/usage -H "Authorization: Bearer $TOKEN"
unset TOKEN
```

Nếu đã gọi `/ask` bằng `student` trước vòng lặp, các lần gọi đó cũng chiếm quota; chờ hết cửa sổ 60 giây hoặc khởi động lại server demo để đo từ đầu. Dừng server bằng Ctrl+C sau khi kiểm tra.

**Điểm cần hiểu từ code mẫu:**

- `usage.budget_remaining_usd` trong response `/ask` đang được gán `usage.total_cost_usd`, nên thực tế là **chi phí đã dùng**. Muốn xem ngân sách còn lại đúng, gọi `/me/usage`; lần kiểm tra này cho `1.0 - 0.000174 = 0.999826` USD.
- Cost guard demo kiểm tra số tiền đã dùng trước request, chưa cộng chi phí dự kiến của request sắp chạy; do đó một request vẫn có thể làm vượt trần. Khi triển khai Redis, cần kiểm tra và giữ chỗ chi phí dự kiến trong cùng một thao tác atomic (ví dụ Lua), rồi quyết toán theo usage thực tế. Chỉ `GET` rồi `INCRBYFLOAT` riêng lẻ vẫn có thể vượt budget khi nhiều request chạy đồng thời.
- Bản demo reset record từng user theo ngày hệ thống, nhưng `_global_today` chưa được dùng để reset `_global_cost`. Không nên coi đây là triển khai đầy đủ ngân sách ngày. Thiết kế Redis theo tháng của Exercise 4.4 dùng key `budget:{user_id}:{YYYY-MM}` để sang tháng mới có ngân sách mới; TTL dọn key cũ. CP3 theo hướng dẫn K5 chỉ chạy và phân tích ví dụ có sẵn; phần tự triển khai production thuộc CP5.

---

## Part 5: Scaling & Reliability (CP4)

Thực hiện ngày 25/11/2026 theo `CHECKPOINTS.md`: chạy và phân tích ví dụ có sẵn trong `05-scaling-reliability/`. Dùng Python `.venv` trong WSL2 cho kiểm tra Linux/SIGTERM; chạy Docker Compose bằng Docker Desktop từ PowerShell vì Docker CLI trong Ubuntu chưa kết nối được `/var/run/docker.sock`.

### Exercise 5.1: Health check và readiness

| Probe | Câu hỏi cần trả lời | Khi không đạt |
| --- | --- | --- |
| Liveness — `GET /health` | Tiến trình còn hoạt động và trả lời được không? | Nền tảng có thể restart instance nếu probe thất bại |
| Readiness — `GET /ready` | Instance đã sẵn sàng phục vụ traffic chưa? | Load balancer/orchestrator ngừng đưa traffic mới vào instance |

Trong `develop/app.py`, lifespan đặt `_is_ready = True` sau startup, đặt lại `False` khi vào phần shutdown. `/ready` kiểm tra cờ này và ném 503 nếu chưa sẵn sàng. `/health` trả metadata về uptime, phiên bản, môi trường, bộ nhớ. Một dependency tạm hỏng không nhất thiết có nghĩa process cần restart: liveness nên tiếp tục 200 nếu process còn sống, readiness mới từ chối traffic phụ thuộc dependency đó.

**Kết quả thực tế bản develop** — output đầy đủ: [cp4-develop.txt](reports/cp4-develop.txt).

```text
GET /health -> HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":1.4,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T09:31:30.429495+00:00","checks":{"memory":{"status":"ok","used_percent":12.9}}}

GET /ready -> HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}
```

`in_flight_requests: 1` bao gồm chính request `/ready` đang chạy qua middleware, không có nghĩa có một request nghiệp vụ khác bị kẹt.

Trong bản production, khi Redis đã kết nối từ startup nhưng ping thất bại về sau, `/health` vẫn trả HTTP 200 với `status: degraded`, còn `/ready` trả 503. Đây là phân tích từ code, chưa thực hiện thí nghiệm dừng Redis. Nếu Redis không có ngay lúc import, ví dụ này fallback sang RAM và `/ready` vẫn có thể trả 200; vì vậy chỉ readiness 200 chưa đủ chứng minh stack đang dùng shared state. Lần chạy này đã kiểm tra thêm `storage: redis` và `redis_connected: true`.

### Exercise 5.2: Graceful shutdown

Chạy `develop/app.py` trong WSL2 với một cổng trống được hệ điều hành cấp, gửi hai request `POST /ask?question=hello`, sau 0.5 giây gửi SIGTERM đến đúng PID server. Endpoint develop nhận `question` qua query, không phải JSON.

**Kết quả đo:**

```text
Request 1: curl exit=0, HTTP/1.1 200 OK
Request 2: curl exit=0, HTTP/1.1 200 OK
Server exit code: 0
Elapsed from request launch to exit: 6.267 seconds
```

Log đối chiếu trong [cp4-develop-server.log](reports/cp4-develop-server.log):

```text
INFO:     Shutting down
INFO:     ... "POST /ask?question=hello HTTP/1.1" 200 OK
INFO:     ... "POST /ask?question=hello HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
... INFO 🔄 Graceful shutdown initiated...
... INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [433]
```

Uvicorn ngừng nhận kết nối mới và chờ request đã nhận hoàn tất trước khi shutdown ứng dụng. SIGKILL không cho phép luồng dọn dẹp này. Timeout graceful của ví dụ là 30 giây; nền tảng cần cho ứng dụng đủ thời gian trước khi buộc dừng.

Hai request được gửi đồng thời nhưng mock `ask()` dùng `time.sleep()` đồng bộ ngay trong endpoint `async`, nên chặn event loop và xử lý mất khoảng 6 giây tổng cộng. Kết quả chứng minh request không bị cắt, chưa chứng minh xử lý song song. Ngoài ra, cờ `_is_ready` chỉ chuyển `False` trong phần shutdown của lifespan, sau bước Uvicorn drain request; không khẳng định đã quan sát `/ready` trả 503 qua mạng ngay tại thời điểm nhận SIGTERM.

### Exercise 5.3: Stateless design

Nếu giữ `conversation_history = {}` trong RAM, mỗi process/container có một bản riêng. Request đầu tới instance A, request sau tới B thì B không thấy lịch sử của A; restart A cũng làm mất dữ liệu trong RAM. Sticky session chỉ giữ client ở một instance, vẫn không giải quyết được mất dữ liệu khi instance chết.

`production/app.py` dùng `save_session()` / `load_session()` với Redis chung:

- Key: `session:{session_id}`; value: JSON chứa history.
- `SETEX` lưu dữ liệu và TTL mặc định 3600 giây; mỗi lần ghi lại gia hạn TTL.
- Mỗi lượt hỏi ghi một message `user` và một message `assistant`; giữ tối đa 20 message.
- Agent chỉ giữ logic xử lý, session nằm ngoài instance nên instance khác đọc tiếp được.

Redis giúp session tồn tại khi **agent** restart; chưa bảo đảm dữ liệu tồn tại khi **Redis** restart. Compose mẫu này không cấu hình volume/AOF và dùng `allkeys-lru`, nên key cũng có thể bị loại bỏ khi thiếu bộ nhớ. Chuỗi load JSON → sửa history → SETEX chưa atomic: nhiều request đồng thời trên cùng session có thể ghi đè nhau. Test dưới đây dùng các lượt hội thoại tuần tự.

### Exercise 5.4: Load balancing qua Nginx

Đã tạo `.env.local` rỗng nếu chưa có (file được Git ignore), rồi chạy đúng project riêng để tránh dùng nhầm image của Part 2:

```powershell
# Từ gốc repo, PowerShell / Docker Desktop:
docker compose -p k5-day14-scaling -f 05-scaling-reliability/production/docker-compose.yml up -d --build --scale agent=3
docker compose -p k5-day14-scaling -f 05-scaling-reliability/production/docker-compose.yml ps
```

```text
Client -> localhost:8080 -> Nginx:80 -> agent-1:8000
                                    -> agent-2:8000
                                    -> agent-3:8000
                                       | shared session state
                                       v
                                    Redis:6379
```

`agent`, `redis`, `nginx` cùng network `agent_net`; chỉ Nginx publish cổng 8080 ra host. Upstream Nginx dùng `agent:8000`, phân phối các request tới các địa chỉ agent. `X-Served-By` cho biết địa chỉ upstream; body `/chat` có `served_by` là ID instance.

**Kết quả:** cả 3 agent và Redis báo healthy, Nginx hoạt động trên cổng 8080. `/health` qua Nginx trả 200 với `storage: redis`, `redis_connected: true`; `/ready` trả 200. Trạng thái và output kiểm tra lưu trong [cp4-production.txt](reports/cp4-production.txt) và [cp4-production-checks.txt](reports/cp4-production-checks.txt).

### Exercise 5.5: Test stateless

Chạy script gốc, không sửa nội dung:

```bash
# Từ gốc repo, terminal WSL2:
.venv/bin/python 05-scaling-reliability/production/test_stateless.py
```

Output của lần chạy có lưu bằng chứng trong [cp4-stateless.txt](reports/cp4-stateless.txt):

```text
Session ID: 2fe0e81d-41ce-463d-a686-da01190b7f94
Request 1: [instance-5b81e2]
Request 2: [instance-ce3e0c]
Request 3: [instance-63d15d]
Request 4: [instance-5b81e2]
Request 5: [instance-ce3e0c]
Total requests: 5
Instances used: {'instance-5b81e2', 'instance-63d15d', 'instance-ce3e0c'}
✅ All requests served despite different instances!
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

Kiểm tra bổ sung bằng assert xác nhận đủ **3 instance**, history có **10 message** và thứ tự role là `user, assistant` lặp lại 5 lần. Bản JSON đầy đủ lưu tại [cp4-session.json](reports/cp4-session.json). `redis-cli TTL session:<id>` đo được **3600 giây**, lưu tại [cp4-redis-ttl.txt](reports/cp4-redis-ttl.txt).

**Thử dừng một instance ngoài kịch bản script gốc:** `test_stateless.py` thực tế không kill container nào. Sau khi script hoàn tất, đã chạy riêng `docker stop k5-day14-scaling-agent-1`:

1. Đọc history vẫn nhận đủ 10 message ban đầu.
2. Gửi thêm `/chat` cùng session nhận HTTP 200, `served_by: instance-ce3e0c`, `storage: redis`.
3. Lần đọc history tiếp theo timeout ở giới hạn client 15 giây; log Nginx ghi 499 sau khi client ngắt. Do đó **chưa chứng minh failover liên tục không gián đoạn** của cấu hình mẫu.
4. Restart riêng Nginx để nạp lại upstream; đọc history nhận 200, đủ **12 message**, 10 message ban đầu giữ nguyên. Bằng chứng: [cp4-failover.txt](reports/cp4-failover.txt), [cp4-failover-recovery.txt](reports/cp4-failover-recovery.txt), [cp4-session-after-stop.json](reports/cp4-session-after-stop.json) và [log Nginx](reports/cp4-nginx-after-stop.log).

Kết quả xác nhận shared state Redis không mất khi một agent dừng. Cấu hình `proxy_next_upstream` có retry khi lỗi/timeout/503, nhưng việc chuyển sang backend khác vẫn phụ thuộc thời gian phát hiện lỗi và danh sách upstream; khai báo `resolver` đơn thuần chưa chứng minh upstream tự cập nhật khi số instance thay đổi. Response `turn: 7` ở lượt hỏi thứ 6 cũng là lỗi đếm của ví dụ (`history` đã chứa câu hỏi mới rồi lại cộng 1); việc kiểm tra số lượt dựa trên history thực tế, không dựa vào trường `turn`.

Đã lưu [log toàn stack](reports/cp4-production-server.log) rồi dọn stack theo yêu cầu CP4:

```powershell
docker compose -p k5-day14-scaling -f 05-scaling-reliability/production/docker-compose.yml down
```

Lệnh kiểm tra container theo label project sau dọn không còn kết quả; cổng 8080 đã được trả lại. Không sửa code mẫu Part 5.

---

## Part 6: Final Project (CP5)

Đã hoàn thành các TODO trong `06-lab-complete/`, giữ nguyên script chấm và golden dataset. Ngày kiểm tra: **25/11/2026**. Lần chấm đầy đủ dùng script gốc `python check_production_ready.py`, không có `--static-only` / `--skip-docker`, kết quả **PASS 12/12 — 41/41 checks passed**, exit code **0**.

### Các thành phần đã triển khai

| Thành phần | Cách thực hiện |
| --- | --- |
| `app/config.py` | Đọc env và `.env` (không ghi đè env nền tảng), validate PORT/rate/budget; production bắt buộc API key |
| `app/auth.py` | Header `X-API-Key`, so sánh constant-time, thiếu/sai/chưa cấu hình key đều 401 |
| `app/redis_client.py` | Kết nối lazy, timeout 1 giây, không ping lúc import, không fallback sang RAM |
| `/health`, `/ready` | Liveness luôn 200; readiness ping Redis, lỗi trả 503 |
| `app/rate_limiter.py` | Redis sorted set + Lua atomic + Redis TIME; sliding window 60 giây, hash API key, vượt trả 429 kèm Retry-After |
| `app/cost_guard.py` | Budget ngày UTC dùng chung theo ENVIRONMENT; Lua giữ trước tiền atomic, quyết toán actual mock usage, thiếu budget trả 402 |
| `app/main.py` | JSON body, input validation, endpoint sync chạy trong thread pool, log JSON không chứa key/prompt/answer; lifespan đóng Redis sau khi Uvicorn drain request |
| `Dockerfile` | Builder cài venv, runtime `python:3.11-slim`, user `agent`, HEALTHCHECK, `exec uvicorn` PID 1, 2 worker, PORT từ env |
| `docker-compose.yml` | Agent + Redis healthcheck/dependency, env_file optional, Redis volume/AOF/noeviction, chỉ publish agent lên localhost |
| `.dockerignore`, `.env.example` | Loại secrets/cache/venv/Part 7 khỏi build context, liệt kê đủ biến cấu hình, không có key thật trong template |
| `railway.toml` | Builder DOCKERFILE và healthcheck `/health`; dùng service root `06-lab-complete/` khi làm CP6 |

### Output script chấm

Output đầy đủ lưu tại [cp5-production-ready.txt](reports/cp5-production-ready.txt); exit code tại [cp5-production-ready.exitcode](reports/cp5-production-ready.exitcode). Phần checklist được trích nguyên từ lần chạy đầy đủ:

```text
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 41/41 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
```

Một số bằng chứng runtime trong report:

- Image **274 MB** theo script chấm (tính từ bytes / 1024²), build thành công trong **49 giây**.
- Uvicorn **2 worker**: key đúng trả 200; rate limit env 5/phút chặn ở request sau 5 lần thành công; restart agent vẫn trả 429 vì state ở Redis.
- Redis không kết nối được: `/health` 200, `/ready` 503; container vẫn khởi động được khi không có Redis.
- Budget `0.000001` USD: trả **402 ngay request đầu** vì không đủ tiền giữ trước cho request.
- Có **17 dòng log JSON** hợp lệ trong lần kiểm tra log.
- SIGTERM khi đang có request: request vẫn 200, process thoát **exit code 0**.
- Docker stop: **exit code 0, 0.8 giây**, dưới giới hạn 10 giây.

### Kiểm tra bổ sung

[tests/test_shared_limits.py](06-lab-complete/tests/test_shared_limits.py) chạy với Redis thật trên mạng Docker riêng, mỗi test dùng prefix key riêng và chỉ xóa key của nó; không FLUSHDB:

| Test | Kết quả |
| --- | --- |
| 40 request cạnh tranh quota 5 | Đúng 5 thành công, 35 bị 429; API key khác có quota riêng |
| Entry đã quá cửa sổ 60 giây | Bị loại khỏi sorted set, không chiếm quota |
| 20 request giữ ngân sách đồng thời | Chỉ 1 reservation 0.00075 USD được cấp khi budget 0.001 USD; quyết toán và hoàn tiền đúng |
| Chuyển qua ngày UTC mới | Dùng key/budget ngày mới; request cũ quyết toán vào key ngày cũ |
| Redis lỗi khi kiểm tra rate/budget | Đều trả 503, không cho gọi LLM không được kiểm soát |

Output cuối: **Ran 5 tests in 0.082s — OK**, lưu tại [cp5-shared-limits-tests.txt](reports/cp5-shared-limits-tests.txt).

Đã chạy Compose thực tế với `.env` local chứa key ngẫu nhiên (được Git ignore, không in key vào report). `/health` và `/ready` trả 200; `/ask` thiếu/sai key trả 401; key đúng trả 200. Bằng chứng: [cp5-compose-smoke.txt](reports/cp5-compose-smoke.txt), [trạng thái stack](reports/cp5-compose-status.txt), [log JSON](reports/cp5-compose-server.log).

Đã chạy thêm image với **PORT=18005**, `/health` tại cổng đó trả 200; process listing cho thấy Uvicorn chạy cổng 18005 và container dừng với exit code 0. Output: [cp5-custom-port.txt](reports/cp5-custom-port.txt). Đã dọn container, network và volume test bằng đúng project `k5-day14-final`; `.env` local được giữ để tự chạy lại, không đưa vào Git.

### Cách chấm lại trên máy này

WSL2 hiện có Python nhưng Docker daemon chưa được tích hợp: lần kiểm tra tĩnh đầu gặp lỗi chuyển đường dẫn Linux sang Windows khi gọi Compose. Để kiểm tra đủ runtime POSIX/SIGTERM và Docker mà không sửa script chấm, dùng container Linux chuyên cho kiểm tra, mount repo **chỉ đọc** và Docker socket. Chạy từ gốc repo bằng PowerShell:

```powershell
docker build -f reports/cp5-checker.Dockerfile -t k5-day14-cp5-checker 06-lab-complete
$cp5Workspace = (Get-Location).Path
docker run --rm --network host --mount "type=bind,source=$cp5Workspace,target=/workspace,readonly" --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock k5-day14-cp5-checker python check_production_ready.py
```

Image kiểm tra dùng đúng `requirements.txt` Part 6 và có thêm Docker CLI/Compose để script tự build/chạy/dọn container. Image agent triển khai không chứa các công cụ kiểm tra này. Nếu WSL đã kết nối Docker bình thường, vẫn dùng lệnh chuẩn trong `06-lab-complete/`: `python check_production_ready.py`.

### Giải thích và giới hạn

Rate limit kiểm soát số lần gọi trong 60 giây; cost guard kiểm soát tổng tiền. Hai thao tác Redis được thực hiện bằng Lua atomic nên nhiều worker không thể cùng kiểm tra một quota cũ rồi đồng loạt vượt trần. Rate limit tính cả request bị từ chối vì thiếu ngân sách sau bước rate check; request thiếu/sai API key không chiếm quota.

Tiền được lưu bằng số nguyên **nano-USD**, không cộng float trong Redis. Token mock ước tính bằng số từ nhân 2; chi phí giữ trước gồm input và câu trả lời dài nhất có thể trong `MOCK_RESPONSES`. Khi mock thành công, hệ thống chỉ giữ chi phí thực tế; khi mock lỗi thì hoàn reservation. Nếu bị kill hoặc mất Redis sau reservation, tiền giữ có thể còn lại để tránh chi tiêu không được ghi nhận; production thực tế cần đối soát reservation bị bỏ dở. Khi thay mock bằng LLM thật phải áp dụng giới hạn output và usage từ provider tương ứng.

Budget được reset theo **ngày UTC** bằng key chứa ngày, không phải reset biến trong RAM. Giữ key ngày cũ đến hết ngày tiếp theo để quyết toán request qua nửa đêm. Cấu hình Redis `noeviction` tránh tự đẩy key quota/budget ra khi đầy bộ nhớ; lỗi Redis trả 503 thay vì bỏ qua kiểm soát.

**CP5 hoàn thành local; sau đó CP6 đã deploy cloud tại URL ghi trong Part 3 và DEPLOYMENT.md.** Dấu ✅ “Public URL ready” trong lần chấm CP5 chỉ xác nhận cấu hình nền tảng khi không truyền `--public-url`; lần chấm CP6 có URL public đã đạt 42/42 checks.

---

## Part 7: Benchmark local (CP7)

Đã thực hiện Exercise 7.1–7.3 trong `06-lab-complete/benchmark-observability/develop/` trên WSL2 ngày 25/11/2026. Báo cáo chi tiết và các bảng số liệu: [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md). Đây là benchmark local với mock LLM, không phát sinh phí LLM thật.

### Exercise 7.1: Metrics

Đã thêm histogram `agent_question_length_chars` với các bucket 20/50/100/200/500/1000/2000 vào `develop/app.py`, observe `len(body.question)` ở đầu endpoint `/ask`. Sau một câu hỏi 27 ký tự, `/metrics` ghi `count=1`, `sum=27`, bucket `le=50` có 1 mẫu. Counter ví dụ là `http_requests_total`, gauge là `agent_in_flight_requests`, histogram latency là `http_request_duration_seconds`.

Ba URL không tồn tại được ghi chung thành `http_requests_total{method="GET",route="unmatched",status="404"} 3.0`. Dùng URL thực làm label sẽ tạo time series mới cho mỗi URL bot sinh ra; route template và `unmatched` giữ cardinality hữu hạn. [Snapshot metrics thật](06-lab-complete/benchmark-observability/develop/reports/metrics_sample.prom).

### Exercise 7.2: Load test và SLO

Chạy đúng 300 request/lượt cho concurrency 1/10/50/100 và ba mức slow rate 0/0.03/0.1 ở concurrency 20. Cấu hình mock baseline giữ latency 120 ms, jitter 60 ms, slow thêm 1500 ms, retrieval 20 ms và error rate 1%.

- Concurrency 1/10/50 đạt SLO p95 ≤ 500 ms và error rate ≤ 2%.
- Concurrency 100: RPS 51.68, p95 **3781.3 ms**, SLO latency **FAIL**, error rate 0.67% vẫn đạt.
- Slow rate 0/0.03/0.1: p95 **274.3 / 306.5 / 1706.0 ms**, p99 **304.3 / 1734.5 / 1726.7 ms**. Lượt 0.1 FAIL SLO latency.

Với 3% slow, p95 vẫn đạt nhưng p99 khoảng 1.73 giây, nên average không mô tả đủ trải nghiệm nhóm chờ lâu. Throughput không tăng tuyến tính: ở mức 100, latency và thời gian hoàn tất batch tăng. Chưa profile CPU/I/O nên chưa khẳng định một nguyên nhân duy nhất; báo cáo nêu rõ giới hạn đo một lượt/batch ngắn và log I/O trên Windows mount. Giữ các lượt FAIL cùng file/exit code thực tế, không đổi ngưỡng để làm đẹp kết quả.

### Exercise 7.3: Eval, sửa knowledge base và CI

Eval dùng cùng cấu hình cho v1/v2/fixed nhưng tắt lỗi upstream ngẫu nhiên (`MOCK_ERROR_RATE=0`) để cô lập chất lượng, vẫn giữ slow rate 0.03:

| Phiên bản | Accuracy | Cost/câu đúng (USD) | Quality gate |
| --- | --- | --- | --- |
| [v1](reports/eval_v1.json) | 1/23, 4.35% | 0.00040395 | FAIL, ngưỡng mặc định 80% |
| [v2 trước sửa](reports/eval_v2.json) | 21/23, 91.30% | 0.00003627 | PASS 80%, 0 regression so với v1 |
| [v2 sau sửa](reports/eval_v2_fixed.json) | **23/23, 100%** | 0.00003427 | **PASS 100%, 0 regression so với v2** |

Hai câu sai ban đầu đều score 0: `security-02` thiếu `token`, `hết hạn`, `chữ ký`; `scaling-03` thiếu `cpu`, `memory`, `custom metrics`. Đã thêm đúng hai entry kiến thức JWT và Kubernetes HPA vào `develop/utils/mock_llm.py`, dừng/bật lại v2 rồi chạy lệnh bắt buộc:

```bash
python eval/run_eval.py --url http://localhost:8002 --min-accuracy 1.0 \
  --baseline reports/eval_v2.json --out reports/eval_v2_fixed.json
```

Output cuối: `Quality gate (accuracy ≥ 100%, không regression): ✅ PASS`, cả 23 câu score 1.0, exit 0. Không sửa golden dataset hoặc script chấm/eval.

Đã viết [.github/workflows/eval.yml](.github/workflows/eval.yml), dùng Python 3.11, chờ readiness, chạy gate 100% với baseline v2, giữ report/log bằng artifact và dừng server bằng trap. Gate này chặt hơn mức 85% của bài tập. Đã parse YAML, kiểm tra Bash syntax và chạy nguyên shell step trên local với virtualenv trong PATH: [ci-local.txt](06-lab-complete/benchmark-observability/develop/reports/ci-local.txt), [eval_ci.json](06-lab-complete/benchmark-observability/develop/reports/eval_ci.json), 23/23, exit 0. Chưa push/chạy trên GitHub; muốn chặn merge phải yêu cầu status check trong branch protection/ruleset của repo.

### Bằng chứng và trạng thái

Đủ **7 load JSON + 3 eval JSON** trong `develop/reports/` và bản sao y hệt trong `reports/` gốc repo. [cp7-environment.json](reports/cp7-environment.json) ghi cấu hình, phần cứng/runtime và hash; [cp7-commands.json](reports/cp7-commands.json) ghi lệnh, timestamp, exit code, kể cả lỗi PATH của lần thử CI local đầu trước khi thêm virtualenv vào PATH. Log/output từng lượt nằm cạnh JSON trong `develop/reports/`.

Server v1/v2 và server CI local đã được dừng sau kiểm tra. Tại thời điểm hoàn thành CP7, observability production thuộc bước tiếp theo. Hiện CP8 đã hoàn thành; xem phần tiếp dưới đây và mục 4–5 trong `BENCHMARK_REPORT.md`.

---

## Part 7 tiếp: Production observability (CP8)

Đã hoàn thành Exercise 7.4–7.7 ngày 25/11/2026. Số đo, cấu hình, giới hạn và bằng chứng đầy đủ ở [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md), mục 4–5.

- **7.4 — Locust và scaling:** 100 users, ramp 10 users/s, 2 phút, đo riêng đúng 1 rồi 3 agent. Aggregated RPS 65.62 → 65.42; p95 340 → 230 ms; p99 cùng 1700 ms. Giữ think time nên throughput không tăng tuyến tính. Dùng `run --no-deps` để Locust không vô tình reset số replica. CSV tại `benchmark-results/` và có snapshot container chứng minh số instance.
- **7.5 — Dashboard và tracing:** lưu ảnh Grafana, trace chậm và trace lỗi trong `screenshots/`. Trace chậm `6711d1947324fe1f016c563706254e29` mất 1723.87 ms, LLM chiếm 98.23%; trace lỗi `a7c7125ca07440b11dcbd031083fdfed` có exception upstream 503. Cả hai khớp log JSON theo trace_id trong [bằng chứng correlation](reports/cp8-trace-log-correlation.json).
- **7.6 — Alerts:** tiêm đồng thời A+B (`MOCK_SLOW_RATE=0.3`, `MOCK_ERROR_RATE=0.2`), không đổi rule. Error rate firing sau 82.67 giây; p95 firing sau 142.90 giây; có snapshot hai alert cùng firing. Cost alert đã firing từ baseline nên không nhận là kết quả experiment C. Không thực hiện C/D; E được giải thích bằng eval CP7. Không dùng lượt kết hợp A+B để suy luận tác động riêng từng biến.
- **7.7 — Phân tích và báo cáo:** phân biệt metric agent với lỗi 502 ở proxy trong lúc recreate/DNS cập nhật, phân biệt percentile Locust với histogram Prometheus và chi phí mock với tiền thật. Đã điền báo cáo và copy đầy đủ JSON/CSV về gốc repo.

Đã sửa `PYTHONUSERBASE` trong Dockerfile production để Python tìm được package khi chạy non-root, đồng bộ hai entry JWT/HPA sang KB production. Eval production sau khi tắt fault đạt **23/23**, không regression; promtool kiểm tra rule thành công. Script chấm cuối có URL Railway đạt **PASS 12/12, 42/42 checks**; public trả **200/200/401/200**. Đã `down -v` stack CP8 và đóng browser riêng sau khi chụp ảnh; Railway vẫn online. Xem [audit trước commit/push](SUBMISSION_AUDIT.md).

## AI log

- **CP8 và audit SUBMISSION (25/11/2026):** AI sửa đường dẫn package Docker non-root và đồng bộ KB production; chạy Locust scale 1/3, Grafana/Prometheus/Jaeger, fault A+B, thu trace/log và bốn ảnh observability thật. Phát hiện `compose run` reset replica nên bỏ lượt preflight và đo lại với `--no-deps`; chỉ báo cáo lượt có bằng chứng đúng số agent. Giữ nguyên ngưỡng alert, ghi thời gian firing thật và giới hạn thí nghiệm kết hợp. Eval production 23/23, script chấm gốc 12/12 (42/42), public 200/200/401/200. AI hoàn thiện báo cáo, kiểm tra file nộp/Git/secret và dọn stack local; chưa commit/push. Người học cần đọc, tự tái hiện và giải thích kết quả trước khi nộp LMS.

- **CP1 (Part 1 — Localhost vs Production):** Yêu cầu AI đọc hướng dẫn và thực hiện CP1. AI đã đọc mã nguồn `01-localhost-vs-production/develop/` và `production/`, chạy kiểm tra trực tiếp hai service trên cổng 8000 để lấy output thực tế (`GET /`, `POST /ask`, `GET /health`, `GET /ready` và log console), sau đó tổng hợp câu trả lời và bảng so sánh vào `MISSION_ANSWERS.md`. Đã đối chiếu trực tiếp từng dòng code trong `develop/app.py`, `production/app.py`, `production/config.py` và kết quả chạy thực tế.
- **CP2 (Part 2 — Docker):** Yêu cầu AI thực hiện CP2. AI đã tạo `02-docker/production/.env.local`, build `my-agent:develop` và `my-agent:advanced` từ gốc repo, chạy container `my-agent:develop` kiểm tra API, đo kích thước thực tế bằng `docker images` / `docker image inspect` (`1.67 GB` vs `240 MB`, giảm `85.62%`), chạy Docker Compose stack (`-p k5-day14-docker`) kiểm tra 4 services và test qua Nginx cổng 80 trước khi `down -v`. Đã tự kiểm tra toàn bộ câu trả lời Exercise 2.1–2.4 và số liệu đo thực tế trong `MISSION_ANSWERS.md`.
- **CP3 (Part 4 — API Security):** Yêu cầu AI thực hiện CP3. AI đã đọc `04-api-gateway/develop/` và `production/`, chạy test `curl -i` với bản `develop` (`AGENT_API_KEY=secret-key-123` → 401/403/200) và bản `production` trong `.venv` WSL2 (`student`/`demo123` tại `POST /auth/token`, lặp 12 request thấy request 1–10 trả 200 và request 11–12 trả 429), che token và ghi đầy đủ phân tích + output vào `MISSION_ANSWERS.md`. Đã đối chiếu lại mã HTTP, header rate-limit và logic `auth.py`, `rate_limiter.py`, `cost_guard.py`.
- **CP3 (tiếp tục, 25/11/2026):** Yêu cầu AI đọc repo và tiếp tục CP3. AI đối chiếu `CHECKPOINTS.md`, `RULES.md`, README và Part 4; chạy lại curl qua hai server WSL2 tạm thời, kiểm tra thêm `/me/usage`, quyền admin và hai nhánh chặn budget bằng lời gọi module. Lưu output thực tế đã che JWT vào `reports/cp3-security.txt`, bổ sung lệnh tự tái hiện và phân tích giới hạn của cost guard mẫu. Các assert trong lần chạy xác nhận mã 401/403/200/429, 10 request được xử lý và ngoại lệ budget 402/503; đã dừng cả hai server. Người học cần tự chạy lại các lệnh và giải thích kết quả trước khi nộp.
- **CP4 (Part 5 — Scaling & Reliability, 25/11/2026):** Yêu cầu AI thực hiện CP4. AI đọc hướng dẫn và code mẫu, chạy `/health`, `/ready`, hai request chậm rồi gửi SIGTERM trong WSL2 (cả hai 200, exit 0, tổng 6.267 giây); build stack `k5-day14-scaling` với 3 agent, Redis và Nginx; chạy script gốc `test_stateless.py`, thêm assert kiểm tra 3 instance/10 message/TTL. Thử dừng 1 agent riêng, ghi nhận timeout đọc history và xác minh dữ liệu còn nguyên sau restart Nginx (12 message). Output và log lưu trong `reports/cp4-*`, đã dọn stack. AI bổ sung câu trả lời Exercise 5.1–5.5 và các giới hạn quan sát được của code mẫu. Người học cần tự chạy lại và giải thích kết quả trước khi nộp.
- **CP5 (Part 6 — Final Project, 25/11/2026):** Yêu cầu AI thực hiện CP5. AI triển khai các module app, Redis Lua atomic cho rate limit và giữ/quyết toán budget, log JSON, graceful shutdown, Docker multi-stage/non-root, Compose, env template và Railway config. Script chấm gốc được chạy đầy đủ trong container Linux dùng requirements Part 6 và Docker CLI vì WSL chưa kết nối Docker daemon: PASS 12/12, 41/41 checks, image 274 MB, stop 0.8 giây. Bổ sung 5 integration test với Redis thật, kiểm tra Compose HTTP và PORT=18005; lưu output trong `reports/cp5-*`, cập nhật README và dọn tài nguyên test. Không sửa script chấm hoặc golden dataset. Người học cần tự chạy lại lệnh, đọc report và giải thích Lua, ngân sách UTC/reservation, readiness và SIGTERM trước khi nộp.
- **CP6 (hoàn thành, 25/11/2026):** Yêu cầu AI tiếp tục CP6, chỉ dùng miễn phí/Trial credit. Người học cài Railway và xác thực CLI qua luồng browserless; AI kiểm tra Trial 5 USD/30 ngày, không payment method/subscription, rồi tạo project, Redis và agent. AI đặt key cloud ngẫu nhiên qua stdin, nối Redis private, xử lý lỗi upload Windows/WSL bằng staging Linux allowlist, cấu hình service health check trực tiếp theo API hiện hành và deploy thành công. URL public kiểm tra 200/200/401/200; script chấm gốc có `--public-url` PASS 12/12, 42/42 checks. Đã lưu report/log/source hashes/billing, chụp dashboard và deployment thật, tạo ảnh test từ kết quả HTTPS thật, cập nhật DEPLOYMENT.md và phần so sánh/Cloud Run. Không nâng cấp gói, không commit secret, không sửa script chấm/golden dataset. Người học cần tự mở URL, chạy lại lệnh và giải thích cấu hình/chi phí/bằng chứng trước khi nộp.
- **CP7 (Benchmark local, 25/11/2026):** Yêu cầu AI tiếp tục CP7. AI đọc checklist/Part 7, thêm histogram độ dài câu hỏi và đo metrics thật; chạy 7 lượt load 300 request trong WSL2, lưu cả hai lượt SLO FAIL (concurrency 100 và slow rate 0.1). Eval baseline v1/v2 là 1/23 và 21/23; thêm tài liệu JWT/HPA vào KB develop, restart v2 và eval lại đạt 23/23, không regression. Viết workflow CI gate 100%, chạy nguyên shell step local sau khi thêm virtualenv vào PATH, đạt 23/23; chưa chạy trên GitHub. Đã cập nhật BENCHMARK_REPORT.md và phần Part 7, lưu cấu hình/lệnh/log, copy 10 JSON ra reports/ và dừng server. Không sửa golden dataset hoặc script chấm. Người học cần tự chạy lại lệnh, giải thích SLO/percentile/cost mỗi câu đúng và đối chiếu số liệu trước khi nộp.
