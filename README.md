# Build Commit Pipeline

Pipeline for TravisTorrent data ingestion and SonarQube enrichment.

## Features

- **Project-centric ingestion**: Upload một CSV là tạo ngay record `Project`, Celery tự sinh `ScanJob` cho từng commit và theo dõi tiến độ/ thống kê.
- **Multi-Instance SonarQube Pool**: Process commits across multiple SonarQube instances in parallel.
- **At-least-once scan jobs**: Từng job luôn nằm trong Mongo với trạng thái rõ ràng (`PENDING/RUNNING/SUCCESS/FAILED_TEMP/FAILED_PERMANENT`). Những commit `FAILED_PERMANENT` tự động xuất hiện ở trang “Failed commits” để chỉnh sonar.properties và retry.
- **Persistent metrics**: Kết quả SonarQube cho từng commit được lưu trong `scan_results`. API `/projects/{id}/results/export` để bạn tải toàn bộ metrics cho một project.
- **Fault Tolerant**: Auto-retry với giới hạn `max_retries`, worker chết không làm mất job (Celery `acks_late + reject_on_worker_lost`).
- **Observable**: UI hiển thị workers stats, scan jobs, failed commits và export kết quả.

### Thành phần chính

| Thành phần | Ý nghĩa |
|------------|---------|
| `projects` | Metadata dataset (CSV path, tổng commits/builds, sonar config). |
| `scan_jobs` | Một commit cần quét Sonar. Thay vì queue ẩn, mọi trạng thái lưu trong Mongo. |
| `scan_results` | Metrics lấy từ Sonar API (bugs, vulnerabilities, coverage, …). |
| `failed_commits` | Nhật ký các job `FAILED_PERMANENT` kèm payload + config override để người vận hành retry thủ công. |

API chính:

- `POST /projects` tải CSV + sonar.properties (tuỳ chọn). Trả về project và số commit sẽ được tạo.
- `POST /projects/{id}/collect` tạo scan jobs cho toàn bộ commit trong CSV.
- `GET /scan-jobs` phân trang scan job (lọc theo trạng thái, project, v.v…).
- `POST /scan-jobs/{id}/retry` nạp lại commit với sonar config mới.
- `GET /failed-commits` thay thế dead-letter cũ; trả về payload thất bại để giám sát/ghi chú.
- `GET /projects/{id}/results/export` stream CSV metrics đã thu thập.

````markdown
# Build Commit Pipeline (Hướng dẫn nhanh)

Repository này cung cấp một pipeline gồm API + Celery workers để clone repository, chạy SonarQube analysis và xuất metrics.

Mục tiêu của bản README này:
- Liệt kê những gì cần tải/cài đặt
- Hướng dẫn cấu hình cơ bản
- Giải thích cách SonarScanner được chạy và các phương án (khuyến nghị)
- Các lệnh để khởi động và kiểm tra dịch vụ

**1) Yêu cầu trước khi chạy (host)**
- Docker Desktop (macOS) / Docker Engine và `docker compose` (https://docs.docker.com/get-docker/)
- Git (để worker clone repo)
- (Tùy chọn) Node.js >= 18 + npm/yarn nếu muốn chạy frontend cục bộ

**2) Tệp cấu hình chính**
- `config/pipeline.yml` — cấu hình pipeline (Mongo, RabbitMQ, SonarQube instances, đường dẫn lưu trữ).


Hãy chắc chắn bạn đã chỉnh `config/pipeline.yml`:
- `sonarqube.instances[].host` → URL SonarQube (ví dụ `http://sonarqube:9001`)
- `sonarqube.instances[].token` → token truy cập SonarQube (bắt buộc khi gọi API)
- `paths.default_workdir` → nơi lưu các clone/worktree (mặc định `/app/data/sonar-work`), đảm bảo `./data` trên host có quyền ghi.

**3. Khởi động nhanh (docker compose)**
1) Cập nhật token Sonar trong `config/pipeline.yml`.
2) Khởi động core infra (SonarQube cần thời gian để khởi tạo DB và web):

```bash
docker compose up -d mongo rabbitmq db sonarqube loki promtail grafana
# chờ SonarQube khởi động (có thể mất vài phút)
docker compose up -d api worker_ingest worker_scan worker_exports beat frontend
```

**Cài Đặt — Hướng Dẫn Từng Bước (macOS / Linux)**

- **Bước 0 — Yêu cầu trước:**
  - Docker & Docker Compose v2+ đã cài đặt và đang chạy.
  - Git được cài đặt.
  - (Tùy chọn) Nếu bạn dùng macOS hoặc Linux và muốn chạy build cục bộ, đảm bảo bạn có quyền chạy Docker.

- **Bước 1 — Clone repo và chuyển vào thư mục dự án**

```bash
git clone https://github.com/<your-org>/build-commit-pipeline.git
cd build-commit-pipeline
git checkout -b my-local-setup
```

- **Bước 2 — Chuẩn bị cấu hình**
  - Mở file `config/pipeline.yml` (hoặc `config/pipeline.example.yml`) và sửa các trường sau:
    - `paths.default_workdir`: đường dẫn nơi Sonar và worktrees sẽ được lưu (theo mặc định là `/app/data/sonar-work` trong container).
    - `sonarqube.instances[0].host`: địa chỉ SonarQube (vd: `http://localhost:9001`).
    - `sonarqube.instances[0].token`: đặt token truy cập cho API SonarQube (tạo token trong UI SonarQube — xem Bước 6).
    - `sonarqube.webhook_secret`: một chuỗi bí mật cho webhook (ví dụ: `my-webhook-secret`).
    - `sonarqube.webhook_public_url`: URL công khai mà Sonar sẽ gọi (vd `https://my.example.com/sonar/webhook`).

  - Lưu file khi hoàn tất.

- **Bước 3 — Tạo thư mục dữ liệu local và cấp quyền (nếu cần)**

```bash
mkdir -p ./data/sonar-work ./data/uploads ./data/exports ./data/failed_commits ./data/promtail
# (Tùy chọn) nếu cần thay đổi quyền để Docker có thể ghi
sudo chown -R $USER:$(id -g -n) ./data
```

- **Bước 4 — Build image backend (chứa `sonar-scanner`)**
  - Image backend cần Java + SonarScanner được cài sẵn. Build image bằng lệnh:

```bash
docker compose build backend
```

- **Bước 5 — Khởi động các dịch vụ nền**
  - Khởi MongoDB, RabbitMQ và SonarQube trước, chờ cho SonarQube sẵn sàng:

```bash
docker compose up -d mongo rabbitmq sonarqube
# kiểm tra logs/health của SonarQube (chờ cho đến khi UI sẵn sàng ở :9001)
docker compose logs -f sonarqube
```

- **Bước 6 — Tạo token truy cập SonarQube (manual)**
  - Đăng nhập vào SonarQube UI (vd `http://localhost:9001`).
  - Vào **My Account → Security → Generate Tokens**.
  - Tạo token mới (ví dụ tên `pipeline-token`) và copy token đó.
  - Dán token vào `config/pipeline.yml` tại `sonarqube.instances[0].token`.

- **Bước 7 — Tạo Webhook trong SonarQube (manual)**
  - Vào **Administration → Configuration → Webhooks** trong SonarQube.
  - Tạo webhook mới:
    - `URL`: đặt là `http(s)://<your-public-host>/api/sonarqube/webhook` hoặc giá trị bạn cấu hình tại `sonarqube.webhook_public_url`.
    - `Secret`: nhập chính xác `sonarqube.webhook_secret` từ `pipeline.yml`.
  - Lưu webhook.

- **Bước 8 — Khởi động API + workers**

```bash
docker compose up -d api worker_ingest worker_scan worker_exports beat frontend
```

- **Bước 9 — Kiểm tra hoạt động**
  - Kiểm tra log của `worker_scan` để thấy lệnh `sonar-scanner` được chạy khi có job quét:

```bash
docker compose logs -f worker_scan
```

  - Để chạy một job thử nghiệm, tạo một commit mẫu hoặc gửi request qua API (tham khảo `README` phần API usage).

- **Bước 10 — Điều chỉnh `SONAR_SCANNER_OPTS` (nếu cần)**
  - Mặc định `worker_scan` nhận biến môi trường `SONAR_SCANNER_OPTS` để tinh chỉnh heap JVM cho `sonar-scanner`.
  - Nếu máy host có nhiều RAM, tăng `-Xmx` ví dụ `-Xmx2g` trong `docker-compose.yml` cho `worker_scan`.

Tips & Notes:
 - Nếu bạn chạy trên môi trường CI hoặc muốn tách biệt, có thể cài đặt SonarScanner trên máy host thay vì trong image; chỉ cần đảm bảo `sonar-scanner` có thể được gọi từ worker.
 - Nếu không muốn dùng SonarScanner binary trong image, có thể cấu hình worker để gọi SonarScanner container (yêu cầu mount socket và quyền), nhưng phương án này đã bị loại bỏ trong cấu hình hiện tại.


3) Kiểm tra:
- API: http://localhost:8000
- Frontend: http://localhost:3000
- SonarQube: http://localhost:9001
- RabbitMQ UI: http://localhost:15672 (pipeline/pipeline)
- Grafana (logs): http://localhost:3001 (admin/admin). Thêm Loki datasource trỏ `http://loki:3100` rồi chạy truy vấn `{service="worker_scan"}` để xem log.

## Giám sát log với Loki + Grafana

Repo đã bao gồm stack `loki` + `promtail` + `grafana` để gom log của toàn bộ container:

1. Đảm bảo đã tạo thư mục lưu vị trí đọc log: `mkdir -p ./data/promtail` (đã liệt kê trong phần chuẩn bị dữ liệu).
2. Khởi động stack log bất kỳ lúc nào:

   ```bash
   docker compose up -d loki promtail grafana
   ```

   Promtail tự động đọc stdout/stderr của mọi container thông qua socket Docker, vì vậy không cần cấu hình file log riêng.
3. Mở Grafana tại http://localhost:3001, đăng nhập `admin/admin`, sau đó thêm Loki datasource trỏ `http://loki:3100`.
4. Tạo dashboard mới và chạy truy vấn ví dụ `{service="api"}` hoặc `{service="worker_scan"}` để xem log realtime, thêm bộ lọc `compose_project="build-commit-pipeline"` nếu chạy nhiều project Docker cùng lúc.

Khi triển khai trên server (EC2, bare-metal), thao tác hoàn toàn tương tự. Bạn có thể import các dashboard Grafana khác hoặc thiết lập alert dựa trên nguồn Loki này.

## Triển khai Docker trên EC2 & lưu log Sonar lên S3

> Các bước này mô tả cách chạy toàn bộ stack trên Amazon EC2, kết nối S3 để lưu log quét.

### 1. Chuẩn bị máy EC2
1. Tạo EC2 instance (Ubuntu 22.04 hoặc Amazon Linux 2). Khuyến nghị ít nhất `t3.xlarge` (4 vCPU / 16GB RAM) cho worker scan.
2. Mở các port cần thiết: 22 (SSH), 80/443 (API/Frontend), 9001 (SonarQube nếu chạy chung), 5672/15672 (RabbitMQ nếu cần truy cập UI).
3. Cài Docker & docker compose:
   ```bash
   sudo apt-get update -y
   sudo apt-get install -y docker.io git
   sudo usermod -aG docker $USER
   newgrp docker
   DOCKER_COMPOSE_VERSION=v2.24.7
   sudo curl -SL https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-linux-x86_64 -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   sudo systemctl enable --now docker
   ```

### 2. Clone repo & chuẩn bị thư mục dữ liệu
```bash
git clone https://github.com/<your-org>/build-commit-pipeline.git
cd build-commit-pipeline
mkdir -p ./data/sonar-work ./data/uploads ./data/exports ./data/failed_commits ./data/promtail
```

### 3. Cấu hình SonarQube
1. **Tạo token**  
   - Truy cập UI SonarQube (ví dụ `http://<ec2-ip>:9001`).  
   - `Administration → Security → Users/Tokens → Generate Token`. Token này map vào `sonarqube.instances[].token`.
2. **Tạo webhook**  
   - `Administration → Configuration → Webhooks → Create`.  
   - URL: `https://<domain-or-ip>/api/sonar/webhook`.  
   - Secret: copy vào `sonarqube.webhook_secret`.  
3. (Nếu chạy Sonar trong docker-compose) chỉnh `docker-compose.yml` để expose port 9001 và map volume `./data/sonarqube` nếu muốn giữ dữ liệu.

### 4. Kết nối S3 để lưu log scan
1. Tạo S3 bucket (ví dụ `build-commit-pipeline-logs`).  
2. Tạo IAM user/role với quyền `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` cho bucket.  
3. Cập nhật phần `s3` trong `config/pipeline.yml`:
   ```yaml
   s3:
     enabled: true
     bucket_name: build-commit-pipeline-logs
     region: ap-southeast-1
     access_key_id: <AWS_ACCESS_KEY_ID>      # bỏ nếu dùng IAM role EC2
     secret_access_key: <AWS_SECRET_ACCESS_KEY>
     endpoint_url: null                     # giữ null trừ khi dùng MinIO
     sonar_logs_prefix: sonar-logs
     error_logs_prefix: error-logs
   ```
   Nếu EC2 có IAM role, bỏ `access_key_id` và `secret_access_key`.

### 5. Chỉnh `config/pipeline.yml`
- Sao chép `config/pipeline.example.yml` → `config/pipeline.yml`.  
- Quan trọng:
  - `mongo.uri`: nếu dùng MongoDB Atlas, cập nhật URI + user.  
  - `broker.url`: RabbitMQ URI.  
  - `sonarqube.instances`: host + token.  
  - `paths.*`: giữ mặc định `/app/data/...` vì compose đã mount `./data`.  
  - `web.base_url`: domain dùng cho frontend (để trong email/link nếu cần).

### 6. Build & chạy docker trên EC2
```bash
docker compose build
docker compose up -d mongo rabbitmq db sonarqube loki promtail grafana
# chờ SonarQube khởi động
docker compose up -d api worker_ingest worker_scan worker_exports beat frontend
```

### 7. Thiết lập HTTPS / Reverse proxy (khuyến nghị)
- Dùng Nginx hoặc AWS Load Balancer đặt trước API/Frontend.  
- Cấu hình route `/api` → container `api:8000`, `/` → `frontend:3000`.  
- Bật HTTPS (Let’s Encrypt hoặc ACM).

### 8. Kiểm tra sau triển khai
1. `curl http://<ec2-ip>:8000/health` để sure API up.  
2. Mở `http://<ec2-ip>:3000` để truy cập UI.  
3. Upload một CSV nhỏ, trigger ingest.  
4. Theo dõi log `docker compose logs -f worker_scan`.  
5. Kiểm tra S3 bucket xem log `.txt` được đẩy vào đúng prefix.  
6. Đăng nhập Grafana `http://<ec2-ip>:3001`, thêm Loki datasource `http://loki:3100` và xác nhận nhìn thấy log `{service="worker_scan"}`.

### 9. Các lưu ý vận hành
- **Celery beat**: container `beat` phải chạy để task `reconcile_scan_jobs` tự động requeue job kẹt.  
- **Failed commits**: UI `/failed-commits` hiển thị job `FAILED_PERMANENT`. Dùng nút retry để cập nhật sonar.properties rồi enqueue lại.  
- **Backup**: MongoDB chứa toàn bộ state; nên dùng Atlas hoặc replica set + backup định kỳ.  
- **Scale**: tăng `worker_scan` và chỉnh `celery worker -c <n>` để nâng throughput.  
- **Logs**: stack Loki+Promtail+Grafana đã gom toàn bộ stdout container; vẫn có thể mirror sang CloudWatch/ELK nếu cần lưu trữ lâu dài.

**5) Chạy phát triển cục bộ (không Docker toàn bộ)**
- Backend (sử dụng `uv` như repo đã cấu hình):

```bash
cd backend
curl -LsSf https://astral.sh/uv/install.sh | sh   # nếu chưa có uv
uv sync --frozen --no-dev
source .venv/bin/activate
uv run uvicorn app.main:app --reload
# worker
uv run celery -A app.celery_app.celery_app worker -l info -Q pipeline.scan
```

- Frontend (local):

```bash
cd frontend
npm install
npm run dev
```

**6) Những cấu hình/tập tin đã thay đổi trong repo**
- `backend/app/core/config.py`: mặc định `sonar_instances_config` đã điểm tới `config/sonar_instances.example.json` (trong repo) — không cần mount `../sonar-scan` nữa.
- `docker-compose.yml`: các mount `../sonar-scan:/app/sonar-scan:ro` đã bị loại bỏ để đơn giản hoá. Nếu bạn thực sự cần script ngoài repo, có thể add lại mount này.

**7) Quyền truy cập Docker socket (nếu dùng)**
- Host: `ls -l /var/run/docker.sock` sẽ cho biết owner:group (thường `root:docker`). GID nhóm docker trên host cần được phản ánh trong container nếu bạn chạy non-root.
- Cách xử lý:
  - Chạy container là root (đơn giản nhưng kém an toàn)
  - Khi build image, tạo nhóm với cùng GID như host docker group và tạo user thuộc nhóm đó (phép so khớp GID để cho phép truy cập socket)
  - Dùng `--group-add <docker-gid>` trong compose để thêm quyền nhóm cho container (tùy Docker/Compose phiên bản)

Ví dụ ngắn (docker-compose snippet):

```yaml
  worker_scan:
    build: ./backend
    volumes:
      - ./backend:/app
      - ./config/pipeline.yml:/app/config/pipeline.yml:ro
      - ./data:/app/data
      - /var/run/docker.sock:/var/run/docker.sock   # cho phép dùng docker từ trong container
```

Và trong `backend/Dockerfile` (ví dụ nhanh):

```dockerfile
RUN apt-get update && apt-get install -y docker.io
```

**8) Lời khuyên và bước tiếp theo**
- Nếu bạn muốn tôi cập nhật repo để không cần Docker socket: tôi có thể chỉnh `backend/Dockerfile` để cài `sonar-scanner` binary và sửa `pipeline/sonar.py::build_scan_command` để chạy `sonar-scanner` trực tiếp (khuyến nghị).
- Nếu bạn muốn dùng socket approach, tôi có thể cập nhật `docker-compose.yml` và `backend/Dockerfile` để cài Docker CLI và thêm hướng dẫn khớp GID của group `docker`.

Nếu bạn đồng ý, chọn một phương án (A: mount socket, B: cài `sonar-scanner` vào image). Tôi sẽ thực hiện các thay đổi cần thiết (Dockerfile + compose + code) và test nhỏ để đảm bảo worker có thể chạy scan.

````

```bash
