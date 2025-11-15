from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel


class ProjectStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    finished = "finished"


class ScanJobStatus(str, Enum):
    pending = "PENDING"
    running = "RUNNING"
    success = "SUCCESS"
    failed_temp = "FAILED_TEMP"
    failed_permanent = "FAILED_PERMANENT"


class SonarConfig(BaseModel):
    filename: str
    file_path: str
    updated_at: datetime


class Project(BaseModel):
    id: str
    project_name: str
    project_key: str
    total_builds: str
    total_commits: str
    processed_commits: int = 0
    failed_commits: int = 0
    sonar_config: Optional[SonarConfig] = None
    status: ProjectStatus = ProjectStatus.pending
    source_filename: Optional[str] = None
    source_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ScanJob(BaseModel):
    id: str
    project_id: str
    commit_sha: str
    status: ScanJobStatus
    retry_count: int = 0
    max_retries: int = 3
    last_error: Optional[str] = None
    last_worker_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_started_at: Optional[datetime] = None
    last_finished_at: Optional[datetime] = None
    repository_url: Optional[str] = None
    repo_slug: Optional[str] = None
    project_key: Optional[str] = None
    component_key: Optional[str] = None
    sonar_instance: Optional[str] = None
    s3_log_key: Optional[str] = None
    log_path: Optional[str] = None
    config_override: Optional[str] = None
    config_source: Optional[str] = None


class ScanMetrics(BaseModel):
    bugs: int = 0
    vulnerabilities: int = 0
    code_smells: int = 0
    coverage: float = 0.0
    duplicated_lines_density: float = 0.0

    class Config:
        extra = "allow"


class ScanResult(BaseModel):
    id: str
    project_id: str
    job_id: str
    sonar_project_key: str
    metrics: ScanMetrics | Dict[str, float | int | str]
    created_at: datetime


class FailedCommit(BaseModel):
    id: str
    payload: dict
    reason: str
    status: str = "pending"
    config_override: Optional[str] = None
    config_source: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
