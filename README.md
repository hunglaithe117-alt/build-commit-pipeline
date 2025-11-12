# build-commit-pipeline

Pipeline thu thập & làm giàu TravisTorrent với FastAPI + Celery + RabbitMQ + MongoDB, tích hợp SonarQube webhook và giao diện Next.js để quản lý toàn bộ quy trình.

## Kiến trúc tổng quan

```
frontend (Next.js)
    └── gọi REST API để upload CSV, giám sát job, tải metrics
backend (FastAPI)
    ├── API đồng bộ (upload CSV, trigger job, liệt kê SonarQube runs, tải output)
    ├── Celery worker xử lý ingestion + scan + export metrics
    ├── RabbitMQ làm broker/queue + Dead Letter Queue (Mongo)
    ├── MongoDB lưu metadata dataset, job queue, DLQ, đường dẫn output
    └── Module `pipeline/sonar.py` tái hiện logic của `sonar_scan_csv_multi.py` để clone repo, checkout commit và chạy sonar-scanner
SonarQube
    └── Khởi chạy bằng docker-compose.sonarqube.yml (thư mục sonar-scan/) và cấu hình webhook → backend
Observability
    └── Grafana Loki + Promtail + Grafana theo dõi stdout containers và file log trong `data/`
```

## Thư mục quan trọng

- `backend/` – FastAPI app (`app/main.py`), cấu hình Celery (`app/celery_app.py`), service layer (`app/services/*`), pipelines (`backend/pipeline/*`).
- `frontend/` – Next.js 14 app cung cấp 4 màn hình: nguồn dữ liệu, job thu thập, SonarQube runs, output.
- `config/pipeline.yml` – YAML cấu hình duy nhất cho kết nối Mongo/RabbitMQ, đường dẫn Sonar script, các metric keys muốn export.
- `docker-compose.yml` – Khởi chạy API + worker + beat + frontend + RabbitMQ + Mongo. Mặc định mount thư mục `../sonar-scan` để tái sử dụng các script hiện có, đồng thời tạo hai database Postgres riêng cho từng SonarQube instance.
- `config/postgres-init.sql` – Script khởi tạo `sonar_primary` và `sonar_secondary` để mỗi SonarQube dùng database riêng, tránh xung đột migration.
- `data/` – Lưu file upload, dead-letter artifact, và CSV metrics sau khi export (được mount vào containers).

## Quick start (chạy nhanh)

Chạy toàn bộ stack bằng Docker (gồm API, worker, frontend, RabbitMQ, Mongo, SonarQube nếu bạn có cấu hình):

```bash
cp .env.example .env                            # sau đó chỉnh APP_UID/APP_GID theo máy của bạn
# hoặc một dòng: APP_UID=$(id -u) APP_GID=$(id -g) envsubst < .env.example > .env
# chỉnh token SonarQube trong config/pipeline.yml trước khi khởi động
docker compose up --build
```

Chỉ chạy backend cục bộ (phát triển API):

```bash
cd backend
curl -LsSf https://astral.sh/uv/install.sh | sh  # nếu chưa có uv
uv sync --frozen --no-dev                        # tạo .venv theo lockfile
source .venv/bin/activate
uv run uvicorn app.main:app --reload
# chạy celery worker trong terminal khác
uv run celery -A app.celery_app.celery_app worker -l info
```

Frontend (cục bộ):

```bash
cd frontend
npm install
npm run dev
```

## Troubleshooting

- SonarQube không gửi webhook: kiểm tra `sonarqube.webhook_secret` trong `config/pipeline.yml` và đảm bảo endpoint `http://<host>:8000/api/sonar/webhook` có thể truy cập từ SonarQube container.
- Celery không thực thi task: kiểm tra broker (RabbitMQ) URL và rằng worker đang chạy (`uv run celery -A app.celery_app.celery_app worker -l info`).
- Kết nối Mongo thất bại: kiểm tra chuỗi kết nối trong `config/pipeline.yml` và đảm bảo Mongo đã khởi động trước khi API kết nối.
- SonarScanner không chạy: đảm bảo SonarScanner CLI có sẵn trên host/container và mỗi instance trong `config/pipeline.yml` có token hợp lệ.

## Chuẩn bị

1. **Chạy SonarQube**: dùng `sonar-scan/docker-compose.sonarqube.yml` như bạn đã có để bật SonarQube và SonarScanner CLI.
2. **Tạo `.env`**: sao chép `.env.example` thành `.env`, đặt `APP_UID` và `APP_GID` (thường là kết quả của `id -u` và `id -g`). Docker Compose sẽ chạy các service backend bằng UID/GID này để mọi file trong `./data` luôn thuộc sở hữu user hiện tại, không phải chạy `sudo chown` sau mỗi lần pull. Nếu trước đây thư mục `data/` đã bị root chiếm quyền, chỉ cần `sudo chown -R $(id -u):$(id -g) data` **một lần** để đồng bộ lại.
3. **Điền config**:
   - Sao chép `config/pipeline.example.yml` thành `config/pipeline.yml` (đã thực hiện với cấu hình mặc định). Cập nhật:
     - `sonarqube.instances`: danh sách SonarQube bạn muốn dùng (mỗi entry cần `host` và `token`). Worker sẽ round-robin commit qua các instance này.
     - `sonarqube.max_concurrent_jobs_per_instance`: số commit song song tối đa trên mỗi instance (Community Edition = 1).
     - `sonarqube.webhook_secret`: chuỗi bí mật để SonarQube gửi webhook.
4. **Logging (tùy chọn)**: Nếu sử dụng Loki + Promtail + Grafana trong `docker-compose.yml`, giữ nguyên `config/promtail-config.yml` hoặc chỉnh lại đường log mong muốn.

## Backend dùng uv

Toàn bộ dependencies Python được quản lý bằng [uv](https://github.com/astral-sh/uv) (đã khóa trong `backend/uv.lock`). Làm việc cục bộ:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh  # nếu chưa có uv
cd build-commit-pipeline/backend
uv sync --frozen --no-dev                        # tạo .venv theo lockfile
source .venv/bin/activate                        # hoặc dùng `uv run ...`
uv run uvicorn app.main:app --reload
uv run celery -A app.celery_app.celery_app worker -l info
```

Dockerfile backend cũng sử dụng `uv sync --frozen` nên build luôn bám sát `uv.lock`.

## Chạy toàn bộ stack

```bash
cd build-commit-pipeline
docker compose up --build
```

- API: <http://localhost:8000>
- Frontend: <http://localhost:3000>
- Mongo: mongodb://travis:travis@localhost:27017 (authSource=admin)
- RabbitMQ: amqp://pipeline:pipeline@localhost:5672//

## Quy trình sử dụng giao diện

1. **Nguồn dữ liệu** (`/data-sources`)
   - Upload file CSV (ví dụ từ `19314170/ruby_per_project_csv`). Backend tự động tóm tắt số build/commit, tạo record trong Mongo.
   - Bấm "Thu thập dữ liệu" để queue job Celery (`ingest_data_source`). Các commit trong CSV sẽ được đưa vào hàng đợi và phân phối lần lượt cho từng SonarQube instance, mỗi instance chỉ chạy tối đa 1 commit (Community) tại một thời điểm.

2. **Thu thập** (`/jobs`)
   - Theo dõi trạng thái job (queued/running/succeeded/failed), số commit đã xử lý / tổng và commit đang chạy. Progress bar cập nhật mỗi 5 giây với dữ liệu realtime từ Mongo.

3. **SonarQube runs** (`/sonar-runs`)
   - Hiển thị từng commit đã submit lên SonarQube (component key = `{project}_{commit}`), trạng thái webhook, log file path và đường dẫn metrics sau khi export. Khi webhook báo thành công, Celery sẽ tự động gọi task `export_metrics` để trích xuất measures và lưu file CSV vào `data/exports`.

4. **Dữ liệu đầu ra** (`/outputs`)
   - Liệt kê các bộ metric đã được export. Có link tải nhanh `api/outputs/{id}/download`.

## Scale nhiều SonarQube instance

Trong `config/pipeline.yml`, bạn có thể khai báo nhiều instance:

```yaml
sonarqube:
  max_concurrent_jobs_per_instance: 1
  instances:
    - name: primary
      host: http://sonarqube1:9000
      token: "token-primary"
    - name: secondary
      host: http://sonarqube2:9000
      token: "token-secondary"
```

Mỗi commit từ CSV sẽ được gán lần lượt cho từng instance. Thông tin `sonar_instance`, `sonar_host`, commit hiện tại và log file đều được hiển thị trên giao diện `/jobs` và `/sonar-runs` để dễ theo dõi realtime.

- Hệ thống sử dụng `instance_locks` trong Mongo để đảm bảo **mỗi SonarQube chỉ xử lý nhiều nhất `max_concurrent_jobs_per_instance` commit cùng lúc**. Nếu tất cả instance đều bận, Celery sẽ retry cho tới khi có slot trống.
- Round-robin + lock đảm bảo các commit được dàn đều trên các server hiện có mà không cần phải tách file CSV theo instance.
- Docker Compose đã cấu hình sẵn hai database Postgres (`sonar_primary`, `sonar_secondary`) thông qua `config/postgres-init.sql`, vì vậy mỗi SonarQube container sử dụng schema riêng biệt và không tranh chấp migration. Nếu bạn đã chạy phiên bản cũ (một database), hãy xóa volume `postgres_data` trước khi khởi động lại để script có cơ hội tạo schema mới.

## Observability (Grafana + Loki)

- `docker-compose.yml` bổ sung 3 dịch vụ:
  - `loki` (port 3100) lưu trữ log.
  - `promtail` tail stdout của Docker (`/var/lib/docker/containers/*`) và các file log trong `data/` (như `sonar-work/*/logs/*.log`, `dead_letter/*.json`, `error_logs/*.log`) theo cấu hình `config/promtail-config.yml`.
  - `grafana` (port 3001, admin/admin) để trực quan hóa.
- Sau khi `docker compose up -d loki promtail grafana`, vào Grafana → add data source → Loki (`http://loki:3100`).
- Các nhãn log quan trọng:
  - `job="docker-containers"`: log stdout của API, Celery worker/beat, frontend, RabbitMQ, Mongo, SonarQube, v.v.
  - `job="sonar-commit-logs"`: log từng commit (`data/sonar-work/<instance>/<project>/logs/*.log`).
  - `job="dead-letter"`: JSON payload commit lỗi trong `data/dead_letter`.
  - `job="pipeline-error-files"`: file `data/error_logs/*.log`.
- Nếu muốn bổ sung đường log khác (ví dụ upload tiến độ), chỉnh `config/promtail-config.yml` và reload Promtail.

## Hook SonarQube webhook

1. Trong SonarQube → Administration → Configuration → Webhooks → Add:
   - **URL**: `http://host-may-ban:8000/api/sonar/webhook`
   - **Secret**: dùng giá trị `sonarqube.webhook_secret` trong YAML.
2. Sau mỗi analysis thành công, SonarQube sẽ POST payload. Backend xác thực chữ ký (`X-Sonar-Webhook-HMAC-SHA256` hoặc `X-Sonar-Secret`). Nếu status = OK/SUCCESS, Celery `export_metrics` chạy ngay, ghi đường dẫn vào Mongo + outputs.

## Dead Letter Queue

- Khi Celery task thất bại (ví dụ Sonar scan lỗi), backend ghi lại payload vào collection `dead_letters` và trạng thái data source chuyển `failed`.
- File log/chi tiết cũng có thể ghi ra `data/dead_letter/` nếu cần mở rộng (`LocalFileService`).

## Tích hợp script hiện tại

- **Scanning**: `pipeline/sonar.py` chuyển logic từ `sonar-scan/sonar_scan_csv_multi.py` vào Python module. Một SonarCommitRunner được tạo cho từng instance và CSV; runner clone repo, checkout từng commit tuần tự và chạy `sonar-scanner`.
- **Metrics export**: `pipeline/sonar.py::MetricsExporter` lấy cảm hứng từ `sonar-scan/batch_fetch_all_measures.py`, nhưng gói gọn cho từng project key, chunk metric theo YAML.
- Nếu muốn chạy hàng loạt, chỉ cần đặt nhiều file CSV trong thư mục `data/uploads/` rồi queue nhiều data source.

## API chính (FastAPI)

| Method | Path | Mô tả |
|--------|------|-------|
| `POST /api/data-sources?name=` | Upload CSV (multipart). Trả về metadata + stats. |
| `POST /api/data-sources/{id}/collect` | Queue job Celery để scan + lấy metrics. |
| `GET /api/jobs` | Danh sách job ingest. |
| `GET /api/sonar/runs` | Lịch sử webhook/scan. |
| `POST /api/sonar/webhook` | Endpoint nhận webhook SonarQube. |
| `GET /api/outputs` | Danh sách dataset enriched. |
| `GET /api/outputs/{id}/download` | Tải file metrics CSV. |

## Mở rộng

- Thêm `app/tasks/sonar.py` để hỗ trợ queue retry thủ công hoặc cron refresh.
- Dễ dàng chuyển sang message broker khác (ví dụ đổi RabbitMQ host) bằng cách chỉnh `broker.url` trong YAML + Celery config.
- Có thể thêm trang quản lý DLQ bằng cách đọc collection `dead_letters`.
