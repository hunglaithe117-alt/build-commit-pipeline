# Build Commit Pipeline

FastAPI + Celery pipeline giúp thu thập TravisTorrent CSV, chạy SonarQube cho từng commit và xuất metrics kèm giao diện Next.js để quản lý toàn bộ vòng đời.

## Kiến trúc

```
frontend (Next.js 14)
  ├── Upload CSV, hiển thị thống kê, trigger pipeline
  └── Bảng theo dõi job, Sonar runs, dataset đầu ra

backend (FastAPI + Celery)
  ├── REST API: /data-sources, /jobs, /sonar, /outputs
  ├── Celery worker: ingest CSV, chạy SonarCommitRunner, export metrics
  ├── Redis: broker + queue chính + DLQ
  ├── MongoDB: metadata (data_sources, jobs, sonar_runs, outputs, dead_letters, instance_locks)
  └── `pipeline/sonar.py`: tái hiện logic `sonar_scan_csv_multi.py` (clone repo, checkout commit, sonar-scanner)

sonarqube/
  └── Có thể chạy nhiều instance (ví dụ sonarqube1, sonarqube2). Mỗi instance xử lý độc quyền một CSV tại một thời điểm.
```

## Thư mục chính

| Path | Nội dung |
| --- | --- |
| `backend/` | FastAPI app, Celery config, Mongo/FS services, pipeline logic |
| `frontend/` | Next.js app với 4 màn hình (Nguồn dữ liệu, Thu thập, SonarQube, Dữ liệu đầu ra) |
| `config/pipeline.yml` | Cấu hình duy nhất cho Mongo/Redis/Sonar/paths/metrics |
| `docker-compose.yml` | Dev stack: FastAPI API + worker + beat + frontend + Redis + Mongo + (tuỳ chọn) SonarQube |
| `data/` | Upload CSV, dead-letter artifacts, xuất metrics CSV |

## Cấu hình (`config/pipeline.yml`)

1. Sao chép `config/pipeline.example.yml` → `config/pipeline.yml`.
2. Thông tin cần sửa:
   - `paths.*`: mount path của thư mục dữ liệu.
   - `mongo`: URI, database name, options.
   - `redis`: broker URL (mặc định `redis://redis:6379/0`) + tên queue.
   - `pipeline`: `ingestion_chunk_size`, `csv_encoding`, ….
   - `sonarqube.instances`: danh sách SonarQube server. Mỗi entry gồm `name`, `host`, `token_env` (hoặc `token`) và `scanner_bin`. `default_instance` cho trường hợp chỉ có một server.
   - `storage.instance_locks_collection`: collection dùng để lock instance, đảm bảo một Sonar chỉ chạy tối đa một CSV tại cùng thời điểm.
   - `web.base_url`: domain của frontend để thiết lập CORS.
3. Export token SonarQube tương ứng với `token_env` trước khi chạy Docker compose hoặc ghi trực tiếp vào file.

## Chạy stack

```bash
# 1) chuẩn bị token Sonar
export SONARQUBE_TOKEN_PRIMARY=xxxx
export SONARQUBE_TOKEN_SECONDARY=yyyy  # nếu dùng 2 instance

# 2) build + chạy toàn bộ stack (API, worker, beat, frontend, redis, mongo)
cd build-commit-pipeline
docker compose up --build
```

Dịch vụ chính mặc định:

| Service | Port | Ghi chú |
| --- | --- | --- |
| FastAPI | `http://localhost:8000` | REST API, webhook endpoint |
| Frontend | `http://localhost:3000` | UI Next.js chạy 4 màn hình |
| Redis | `redis://localhost:6379` | Broker cho Celery |
| Mongo | `mongodb://travis:travis@localhost:27017` | Metadata |

### Chạy backend cục bộ bằng uv

```bash
cd build-commit-pipeline/backend
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --frozen --no-dev
source .venv/bin/activate
uv run uvicorn app.main:app --reload
# terminal khác
uv run celery -A app.celery_app.celery_app worker -l info
```

### Frontend dev

```bash
cd build-commit-pipeline/frontend
npm install
npm run dev
```

## Luồng sử dụng UI

1. **Nguồn dữ liệu (`/data-sources`)**  
   Upload CSV (ví dụ `ruby_per_project_csv/ryanb_cancan.csv`). Backend tính thống kê (số build, commit, repo) và cho phép bấm “Thu thập dữ liệu”.  
   *Pagination mặc định: 20 hàng.*

2. **Thu thập (`/jobs`)**  
   Hiển thị job Celery: số commit xử lý / tổng, commit đang chạy, Sonar instance đang phục vụ. Job list giới hạn 20 hàng.

3. **SonarQube (`/sonar-runs`)**  
   Liệt kê lịch sử quét (50 hàng): project key, commit SHA, component key `{project}_{commit}`, instance phụ trách, trạng thái (running/skipped/submitted/succeeded/failed), log path, metrics path, analysis id.

4. **Dữ liệu đầu ra (`/outputs`)**  
   Danh sách dataset enriched (20 hàng). Có sẵn link tải `GET /api/outputs/{id}/download`.

## Cơ chế scale nhiều SonarQube

- `ingest_data_source` sẽ tìm một SonarQube instance rảnh (`instance_locks` collection). Nếu tất cả bận, job sẽ retry sau 60 giây.  
- Khi lock thành công, **toàn bộ commit trong CSV chạy tuần tự trên instance đó** bằng `SonarCommitRunner`. Sau khi CSV hoàn tất (hoặc lỗi) lock mới được giải phóng.  
- Nếu bạn có 2 instance, có thể xử lý đồng thời 2 CSV; CSV thứ 3 sẽ chờ tới khi có instance rảnh.  
- UI hiển thị trường `sonar_instance` để bạn biết dataset nào đang chiếm Sonar nào.

## SonarQube webhook

1. Trong SonarQube → Administration → Configuration → Webhooks → Add:
   - URL: `http://<host>:8000/api/sonar/webhook`
   - Secret: giá trị `sonarqube.webhook_secret`.
2. Mỗi analysis thành công/sai được ghi vào `sonar_runs`. Nếu status “OK/SUCCESS”, backend tự động queue export metrics (CSV trong `data/exports` + record `outputs`).

## Troubleshooting nhanh

| Vấn đề | Cách xử lý |
| --- | --- |
| Không thấy job chạy | Kiểm tra Redis, Celery worker log (`docker compose logs worker`). |
| Job mắc kẹt ở “queued” | Tất cả Sonar instances đang bận. Chờ instance rảnh hoặc tăng số instance trong `sonarqube.instances`. |
| Sonar webhook 401 | Sai `sonarqube.webhook_secret`. Sửa config & restart API. |
| Không export metrics | Xem `data/dead_letter` và collection `dead_letters` để biết lý do. |

## Các file hữu ích

- `backend/app/tasks/ingestion.py`: gán CSV → Sonar instance, xử lý tuần tự.
- `backend/app/tasks/sonar.py`: `process_commit`, webhook handler, export metrics.
- `backend/pipeline/sonar.py`: SonarCommitRunner + MetricsExporter (wrapper từ script gốc).
- `config/pipeline.example.yml`: mẫu cấu hình mới nhất (Redis + multi-instance + instance locks).

---

Chúc bạn build pipeline thuận lợi! Thắc mắc cứ mở issue/ghi chú ngay trong repo để tiện trao đổi. 🙂
