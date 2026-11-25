# Deployment — Agent Part 6 (CP6)

**Đã deploy thành công trên Railway ngày 25/11/2026.** Agent và Redis đều ở trạng thái `SUCCESS` / Online. Bốn kiểm tra public đạt **200 / 200 / 401 / 200**. Script chấm gốc có `--public-url` đạt **PASS 12/12 — 42/42 checks passed**, exit code 0.

## URL và tài nguyên thực tế

- **Public URL:** https://agent-production-702ecd1c.up.railway.app
- [Health](https://agent-production-702ecd1c.up.railway.app/health), [readiness](https://agent-production-702ecd1c.up.railway.app/ready).
- [Dashboard project](https://railway.com/project/93b45f7d-c21d-4c37-bcff-a2d81d9e28f3?environmentId=50a43efb-2781-4b9e-9f1f-8200297ee45f).
- [Deployment agent đang Active](https://railway.com/project/93b45f7d-c21d-4c37-bcff-a2d81d9e28f3/service/f757017e-8d72-4ee3-83a6-346d81c53057?id=a4f5b9cd-a4e4-4b57-b0ba-4eb42bd053c0).

| Thành phần | Giá trị |
| --- | --- |
| Project | `day14-production-agent` |
| Project ID | `93b45f7d-c21d-4c37-bcff-a2d81d9e28f3` |
| Environment | `production`, ID `50a43efb-2781-4b9e-9f1f-8200297ee45f` |
| Agent service ID | `f757017e-8d72-4ee3-83a6-346d81c53057` |
| Agent deployment ID | `a4f5b9cd-a4e4-4b57-b0ba-4eb42bd053c0` |
| Redis service ID | `09e90357-2a6b-4cef-a4cb-e1434bd01fdd` |
| Redis deployment ID | `26b413fb-07d3-40ed-8ca6-a92c63fc02c8` |
| Redis | Railway template, `redis:8.2`, volume 500 MB mount `/data` |
| Agent runtime | 1 replica, Uvicorn 2 workers, domain forward tới PORT 8000 |
| Source | Nội dung `06-lab-complete/`, upload trực tiếp từ bản local |
| Kiểm tra public | **17:06:22 GMT+7, 25/11/2026**; timestamp UTC đầy đủ nằm trong JSON report |

```text
Client -- HTTPS --> Railway public domain --> agent:8000
                                               |
                                               +-- private network --> Redis:6379
```

Redis không có domain web hoặc public TCP proxy (`railway tcp-proxy list --service Redis --json` trả danh sách trống). Agent dùng URL private có xác thực do Railway reference cung cấp; không dùng Redis localhost của máy lab.

## Gói và credit: chỉ dùng Trial

Trước khi tạo tài nguyên đã xác minh `isTrialing: true`, **30 ngày**, **5 USD credit**, không có payment method và không có subscription trả phí. Không mua gói, không thêm thẻ, không nâng cấp tài khoản.

API hiển thị tên plan `HOBBY` cho các quyền của Trial, đồng thời `isTrialing: true` và `subscriptions: []`; đây là Trial đang hoạt động, không phải hành động đăng ký Hobby trả phí. Sau deploy, snapshot ghi usage **0.0003125609351851851 USD**, credit còn **4.9996874390648145 USD**, vẫn không có payment method/subscription. Usage có thể cập nhật trễ và tiếp tục tăng khi dịch vụ chạy; không diễn giải snapshot thành chi phí cố định.

Bằng chứng: [billing trước deploy](reports/cp6-billing-before.json), [billing sau deploy](reports/cp6-billing-after.json). Theo [Railway Free/Trial](https://docs.railway.com/pricing/free-plan), Trial có giới hạn thời gian/credit; khi hết cần xử lý theo gói miễn phí hiện hành hoặc dừng dịch vụ, không tự động nâng cấp. Giữ deployment online để chấm bài; sau khi được chấm có thể dừng/xóa tài nguyên lab.

## Biến môi trường đã đặt trên agent

| Biến | Cấu hình cloud |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `PORT` | `8000` |
| `AGENT_API_KEY` | Secret ngẫu nhiên riêng cho cloud, đặt qua CLI stdin; không ghi giá trị vào repo/report |
| `REDIS_URL` | Reference `${{Redis.REDIS_URL}}` tới service Redis trong cùng environment |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` cho chi phí mock/ngày UTC |

Key cloud được giữ tại `06-lab-complete/.env.cloud` trên máy làm bài, đã được Git ignore và không upload. Nó khác key local trong `.env`. Không gửi giá trị key/token vào chat hay ảnh chụp. Budget mock của agent không phải giới hạn chi phí hạ tầng Railway.

## Kiểm tra public thực tế

[Report JSON](reports/cp6-public-checks.json) chứa timestamp, URL, status và body thực tế; [output terminal](reports/cp6-public-checks.txt) không chứa API key.

| Request | Authentication | Status thực tế | Kết quả |
| --- | --- | --- | --- |
| GET /health | Public | 200 | `{"status":"ok","environment":"production"}` |
| GET /ready | Public | 200 | `{"ready":true}`, Redis kết nối thật |
| POST /ask | Không có key | 401 | Bị từ chối |
| POST /ask | Có key cloud | 200 | Có answer và usage JSON |

Chạy lại từ gốc repo trong WSL2 bằng key cloud đã lưu local, không in key:

```bash
set -a
source 06-lab-complete/.env.cloud
set +a
BASE=https://agent-production-702ecd1c.up.railway.app

curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -d '{"question":"Hello"}'
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'

.venv/bin/python 06-lab-complete/verify_public_deployment.py \
  --url "$BASE" --out reports/cp6-public-checks.json
unset AGENT_API_KEY
```

Script không chuyển secret theo redirect, yêu cầu environment production, readiness true và answer hợp lệ. Không gọi `GET /ask` vì endpoint này yêu cầu POST.

## Script chấm gốc với URL cloud

Đã chạy trong container Linux có Docker CLI/daemon để kiểm tra POSIX SIGTERM và build Docker, giữ nguyên script chấm:

```text
Public URL: GET https://agent-production-702ecd1c.up.railway.app/health → 200
Result: 12/12 tiêu chí đạt · 42/42 checks passed
PASS 12/12 — PRODUCTION READY!
```

Output đầy đủ: [cp6-production-ready.txt](reports/cp6-production-ready.txt); [exit code 0](reports/cp6-production-ready.exitcode). Lần này image local 274 MB, Docker stop exit 0 trong 0.9 giây. Script tự dọn tài nguyên Docker kiểm tra; giữ nguyên hai service cloud để URL tiếp tục hoạt động.

## Cấu hình deploy và cách upload lại

Railway API hiện thông báo `railway.toml / railway.json` đã deprecated khi đặt `railwayConfigFile`. Vì vậy giữ `railway.toml` theo hợp đồng chấm của lab, đồng thời đã cấu hình trực tiếp service agent: Dockerfile, `healthcheckPath=/health`, timeout 60 giây, restart ON_FAILURE tối đa 3, một replica. Không dựa vào TOML để khẳng định cấu hình cloud đang được áp dụng. Xem [Railway IaC migration](https://docs.railway.com/infrastructure-as-code#migrating-from-config-as-code).

Lần upload từ đường dẫn Windows mount trong WSL gặp lỗi BuildKit `exclude-patterns ... non-printable ASCII`. Upload lại cùng source từ thư mục Linux-native đã thành công; không sửa app hoặc bỏ kiểm tra để vượt lỗi. [Manifest SHA-256 source](reports/cp6-source-manifest.json), [ghi nhận staging](reports/cp6-staging.txt), [log build thành công](reports/cp6-build-native.txt), [trạng thái deployment](reports/cp6-deployment-status.json), [log agent](reports/cp6-agent.log).

Có thể upload lại đúng service đang có bằng allowlist chỉ gồm source runtime, từ terminal WSL2 đã đăng nhập:

```bash
cd 06-lab-complete
CP6_STAGE=$(mktemp -d /tmp/day14-agent-XXXXXX)
cp Dockerfile requirements.txt railway.toml .dockerignore .env.example "$CP6_STAGE/"
mkdir "$CP6_STAGE/app" "$CP6_STAGE/utils"
cp app/*.py "$CP6_STAGE/app/"
cp utils/*.py "$CP6_STAGE/utils/"
cd "$CP6_STAGE"
railway up --project 93b45f7d-c21d-4c37-bcff-a2d81d9e28f3 \
  --service agent --environment production --ci
```

Không copy `.env`, `.env.cloud`, token CLI, venv hoặc benchmark code. Không cần tạo lại project/Redis/domain. Deployment dùng source local; các thay đổi repo chưa commit/push nên chưa có GitHub auto-deploy cho phiên bản này.

## Screenshots

- [Dashboard](screenshots/dashboard.png): project thật, agent và Redis Online, hiển thị Trial.
- [Service running](screenshots/running.png): deployment `a4f5b9cd` Active, cả hai service Online và log public API.
- [Kết quả test](screenshots/test.png): ảnh browser của [báo cáo API](reports/cp6-public-checks.html) dựng từ JSON đo thật, có URL/timestamp và bốn mã HTTP; không giả làm dashboard Railway.

Đã kiểm tra ảnh không chứa API key, token, email hoặc thanh bookmark/profile cá nhân.

## Kiểm tra cuối sau CP8

Ngày 25/11/2026 đã kiểm tra lại HTTPS: **200/200/401/200**, xem [JSON đo thật](reports/submission-public-checks.json). Script chấm gốc có URL public tiếp tục **PASS 12/12, 42/42 checks**, xem [output](reports/submission-production-ready.txt). CP8 chạy local, không tạo tải Locust lên Railway. Stack local đã dọn; cloud vẫn giữ online. Hồ sơ commit/push được đối chiếu trong [SUBMISSION_AUDIT.md](SUBMISSION_AUDIT.md).
