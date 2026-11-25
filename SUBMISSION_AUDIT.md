# Kiểm tra SUBMISSION trước commit/push

Ngày kiểm tra: **25/11/2026 (GMT+7)**. Đối chiếu `SUBMISSION.md`, `CHECKPOINTS.md` và `RULES.md`.

**Kết quả: hồ sơ local đủ điều kiện commit/push. Audit tự động PASS 29/29.** CP1–CP8 đã thực hiện, agent và Redis đã deploy trên Railway bằng Trial credit. Chưa commit/push các thay đổi; GitHub chưa có đầy đủ bản local này, GitHub Actions chưa chạy trên remote và chưa nộp link LMS.

| Yêu cầu | Kết quả và bằng chứng |
| --- | --- |
| Đúng tên repo, Public | Origin đúng tên lớp/họ tên/MSSV; truy cập GitHub ẩn danh HTTP 200, có nhãn Public. [Bằng chứng](reports/submission-github.json) |
| Part 6 đúng thư mục, chấm đầy đủ có Docker | **PASS 12/12, 42/42 checks**, exit 0, có URL public. [Output gốc](reports/submission-production-ready.txt) |
| Trả lời và AI log | [MISSION_ANSWERS.md](MISSION_ANSWERS.md) có Part 1–5, checklist, CP7/8, AI log |
| Cloud chạy thật | [DEPLOYMENT.md](DEPLOYMENT.md); HTTPS `/health` 200, `/ready` 200, `/ask` không key 401, có key 200. [Kiểm tra lúc 17:49 GMT+7](reports/submission-public-checks.json) |
| Báo cáo hoàn chỉnh, số liệu khớp | [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md); giữ nguyên các lượt SLO FAIL và giải thích giới hạn đo |
| JSON bắt buộc | Đủ 10 file trong `reports/`, byte-identical với bản develop; 7 lượt load × 300 request |
| Eval và CI | v1 1/23; v2 21/23; fixed và production **23/23**, không regression. Workflow gate 100% đã kiểm tra local; chạy GitHub Actions sau push |
| Locust headless 1/3 agent | CSV có ở gốc và production, khớp nhau; 100 users, ramp 10/s, 2 phút. p95 aggregate **340 → 230 ms**, RPS **65.62 → 65.42** |
| Screenshot | Đủ 7 PNG deploy/observability; đã mở và kiểm tra nội dung |
| Tracing, log và alert | Hai trace chậm/lỗi khớp log theo trace_id; exception 503 hiện trong trace. Hai alert cùng firing, lần đầu quan sát sau **82.67s / 142.90s** |
| Rule và file bảo vệ | Promtool SUCCESS; script chấm, golden dataset, script eval/load không sửa |
| Env và secret | Không có env thật trong index/lịch sử Git; không tìm thấy giá trị key local/cloud hoặc mẫu token/private key trong file dự kiến commit. `.env.example` là template được phép |
| Dữ liệu liên hệ | Không tìm thấy email hoặc mẫu số điện thoại Việt Nam trong tài liệu/báo cáo tự viết; ảnh đã kiểm tra trực quan. Scan không bảo đảm phát hiện mọi loại secret hay số điện thoại |
| File và whitespace | `git diff --check` đạt; không file dự kiến commit nào ≥100 MiB |
| Dọn tài nguyên | Stack Docker CP8 đã `down -v`, không còn container/network thuộc project; browser riêng đã đóng. Railway giữ online để chấm |

Các lỗi đã sửa trong CP8: Python non-root không tìm package do thiếu `PYTHONUSERBASE`; KB production thiếu JWT/HPA; lệnh Locust khởi động dependency làm reset replica (đã đổi `run --no-deps` và đo lại); thiếu bằng chứng/báo cáo production. Đã hoàn thiện các phần này và copy artifact đúng cấu trúc nộp.

Chi tiết từng phép kiểm tra: [reports/submission-audit.json](reports/submission-audit.json). Chạy lại từ gốc repo bằng Python 3.11+:

```bash
python scripts/check_submission.py
```

Script audit đọc artifact đã đo, không tự chạy lại Docker/cloud/load test. Kết quả public phản ánh thời điểm ghi trong JSON; Trial credit và tình trạng service có thể thay đổi. Các phép đo lỗi mock và chi phí mock không phát sinh phí LLM thật.

Sau khi commit/push, kiểm tra GitHub có đủ file, workflow eval xanh, mở lại URL public và nộp link repo trên LMS. Không force-push hoặc sửa ngày commit. Người học cần tự đọc và giải thích code/số liệu theo RULES.
