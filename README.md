# Sonarqube Scan Pipeline

Pipeline for commit data ingestion and SonarQube enrichment.

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
