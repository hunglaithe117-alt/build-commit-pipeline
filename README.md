# Build Commit Pipeline

Pipeline orchestrator for TravisTorrent data ingestion and SonarQube enrichment with **distributed instance pooling**.

## Features

- **Project-centric ingestion**: Upload một CSV là tạo ngay record `Project`, Celery tự sinh `ScanJob` cho từng commit và theo dõi tiến độ/ thống kê.
- **Multi-Instance SonarQube Pool**: Process commits across multiple SonarQube instances in parallel.
- **At-least-once scan jobs**: Từng job luôn nằm trong Mongo với trạng thái rõ ràng (`PENDING/RUNNING/SUCCESS/FAILED_TEMP/FAILED_PERMANENT`). Những commit `FAILED_PERMANENT` tự động xuất hiện ở trang “Failed commits” để chỉnh sonar.properties và retry.
- **Persistent metrics**: Kết quả SonarQube cho từng commit được lưu trong `scan_results`. API `/projects/{id}/results/export` stream CSV để bạn tải toàn bộ metrics cho một project.
- **High Throughput**: Process multiple commits simultaneously with automatic load balancing.
- **Fault Tolerant**: Auto-retry với giới hạn `max_retries`, worker chết không làm mất job (Celery `acks_late + reject_on_worker_lost`).
- **Observable**: UI hiển thị workers stats, scan jobs, failed commits và export kết quả ngay trong trình duyệt.

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

**3) Cách SonarScanner được thực thi trong hiện tại (quan trọng)**
- Hiện tại `backend/pipeline/sonar.py` gọi `docker run sonarsource/sonar-scanner-cli` từ bên trong container (sử dụng Docker CLI).
- Điều này đưa ra hai lựa chọn:
  A) Mount socket Docker vào container và cài Docker CLI trong image (container sẽ gọi Docker trên host). Yêu cầu xử lý quyền truy cập socket hoặc chạy container dưới user có quyền.
  B) Khuyến nghị: cài trực tiếp `sonar-scanner` (binary) vào image backend và chạy lệnh local (không cần socket Docker). An toàn hơn và dễ cấu hình.
  
Ghi chú: dự án hiện được cấu hình để chạy SonarScanner bằng binary (SonarScanner đã cài sẵn trong `backend` image). Việc khởi container `sonarsource/sonar-scanner-cli` từ trong worker (qua Docker socket) đã được loại bỏ để tránh phụ thuộc vào quyền truy cập Docker daemon và để đơn giản hoá triển khai.

Nếu bạn cần lại phương án container trong tương lai, tôi có thể thêm hướng dẫn riêng; hiện tại không cần mount `/var/run/docker.sock`.

**4) Khởi động nhanh (docker compose)**
1) Cập nhật token Sonar trong `config/pipeline.yml`.
2) Khởi động core infra (SonarQube cần thời gian để khởi tạo DB và web):

```bash
docker compose up -d mongo rabbitmq db sonarqube
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
mkdir -p ./data/sonar-work ./data/uploads ./data/exports ./data/failed_commits
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
