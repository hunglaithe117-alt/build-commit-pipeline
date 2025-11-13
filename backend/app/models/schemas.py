from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DataSourceStatus(str, Enum):
    pending = "pending"
    ready = "ready"
    succeeded = "succeeded"
    processing = "processing"
    failed = "failed"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class CSVSummary(BaseModel):
    project_name: Optional[str] = None
    project_key: Optional[str] = None
    total_builds: int = 0
    total_commits: int = 0
    unique_branches: int = 0
    first_commit: Optional[str] = None
    last_commit: Optional[str] = None


class SonarConfig(BaseModel):
    content: str
    source: str = Field(default="text")
    filename: Optional[str] = None
    file_path: Optional[str] = None
    updated_at: datetime


class DataSource(BaseModel):
    id: str
    name: str
    filename: str
    file_path: str
    status: DataSourceStatus
    created_at: datetime
    updated_at: datetime
    stats: Optional[CSVSummary] = None
    sonar_config: Optional[SonarConfig] = None


class Job(BaseModel):
    id: str
    data_source_id: str
    status: JobStatus
    processed: int = 0
    total: int = 0
    failed_count: int = 0
    last_error: Optional[str] = None
    current_commit: Optional[str] = None
    sonar_instance: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @property
    def progress(self) -> float:
        if self.total == 0:
            return 0.0
        return min(1.0, self.processed / self.total)


class SonarRun(BaseModel):
    id: str
    data_source_id: str
    project_key: str
    commit_sha: Optional[str] = None
    job_id: Optional[str] = None
    component_key: Optional[str] = None
    sonar_instance: Optional[str] = None
    sonar_host: Optional[str] = None
    analysis_id: Optional[str] = None
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    metrics_path: Optional[str] = None
    log_path: Optional[str] = None
    message: Optional[str] = None


class DeadLetter(BaseModel):
    id: str
    payload: dict
    reason: str
    status: str = "pending"
    config_override: Optional[str] = None
    config_source: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class OutputDataset(BaseModel):
    id: str
    job_id: str
    data_source_id: Optional[str] = None
    project_key: Optional[str] = None
    repo_name: Optional[str] = None
    path: str
    metrics: list[str] = Field(default_factory=list)
    record_count: int = 0
    created_at: datetime
