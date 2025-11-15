from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import ReturnDocument

from app.services.repository_base import MongoRepositoryBase

_UNSET = object()


class ScanJobsRepository(MongoRepositoryBase):
    def create_scan_job(
        self,
        *,
        project_id: str,
        commit_sha: str,
        repository_url: Optional[str] = None,
        repo_slug: Optional[str] = None,
        project_key: Optional[str] = None,
        max_retries: int = 5,
        status: str = "PENDING",
    ) -> Dict[str, Any]:
        now = datetime.utcnow()
        payload = {
            "project_id": project_id,
            "commit_sha": commit_sha,
            "repository_url": repository_url,
            "repo_slug": repo_slug,
            "project_key": project_key,
            "component_key": None,
            "status": status,
            "retry_count": 0,
            "max_retries": max_retries,
            "last_error": None,
            "last_worker_id": None,
            "sonar_instance": None,
            "s3_log_key": None,
            "log_path": None,
            "config_override": None,
            "config_source": None,
            "created_at": now,
            "updated_at": now,
            "last_started_at": None,
            "last_finished_at": None,
        }
        result = self.db[self.collections.scan_jobs_collection].insert_one(payload)
        payload["id"] = str(result.inserted_id)
        return payload

    def get_scan_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.scan_jobs_collection].find_one(
            {"_id": ObjectId(job_id)}
        )
        return self._serialize(doc) if doc else None

    def claim_job(self, job_id: str, worker_id: str) -> Optional[Dict[str, Any]]:
        query: Dict[str, Any] = {
            "_id": ObjectId(job_id),
            "status": {"$in": ["PENDING", "FAILED_TEMP"]},
        }
        now = datetime.utcnow()
        update_doc = {
            "$set": {
                "status": "RUNNING",
                "last_worker_id": worker_id,
                "last_started_at": now,
                "updated_at": now,
            }
        }
        doc = self.db[self.collections.scan_jobs_collection].find_one_and_update(
            query,
            update_doc,
            return_document=ReturnDocument.AFTER,
        )
        return self._serialize(doc) if doc else None

    def update_scan_job(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        last_error: Any = _UNSET,
        retry_count_delta: Optional[int] = None,
        retry_count: Optional[int] = None,
        repository_url: Any = _UNSET,
        last_worker_id: Any = _UNSET,
        last_started_at: Any = _UNSET,
        last_finished_at: Any = _UNSET,
        component_key: Any = _UNSET,
        sonar_instance: Any = _UNSET,
        s3_log_key: Any = _UNSET,
        log_path: Any = _UNSET,
        config_override: Any = _UNSET,
        config_source: Any = _UNSET,
    ) -> Optional[Dict[str, Any]]:
        set_updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        if status:
            set_updates["status"] = status
        if last_error is not _UNSET:
            set_updates["last_error"] = last_error
        if repository_url is not _UNSET:
            set_updates["repository_url"] = repository_url
        if last_worker_id is not _UNSET:
            set_updates["last_worker_id"] = last_worker_id
        if last_started_at is not _UNSET:
            set_updates["last_started_at"] = last_started_at
        if last_finished_at is not _UNSET:
            set_updates["last_finished_at"] = last_finished_at
        if component_key is not _UNSET:
            set_updates["component_key"] = component_key
        if sonar_instance is not _UNSET:
            set_updates["sonar_instance"] = sonar_instance
        if s3_log_key is not _UNSET:
            set_updates["s3_log_key"] = s3_log_key
        if log_path is not _UNSET:
            set_updates["log_path"] = log_path
        if config_override is not _UNSET:
            set_updates["config_override"] = config_override
        if config_source is not _UNSET:
            set_updates["config_source"] = config_source

        update_doc: Dict[str, Any] = {"$set": set_updates}
        if retry_count_delta:
            update_doc["$inc"] = {"retry_count": retry_count_delta}
        if retry_count is not None:
            update_doc.setdefault("$set", {})
            update_doc["$set"]["retry_count"] = retry_count

        doc = self.db[self.collections.scan_jobs_collection].find_one_and_update(
            {"_id": ObjectId(job_id)},
            update_doc,
            return_document=ReturnDocument.AFTER,
        )
        return self._serialize(doc) if doc else None

    def list_jobs_by_status(
        self, project_id: str, statuses: List[str]
    ) -> List[Dict[str, Any]]:
        cursor = self.db[self.collections.scan_jobs_collection].find(
            {"project_id": project_id, "status": {"$in": statuses}}
        )
        return [self._serialize(doc) for doc in cursor]

    def list_scan_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        cursor = (
            self.db[self.collections.scan_jobs_collection]
            .find()
            .sort("created_at", -1)
            .limit(limit)
        )
        return [self._serialize(doc) for doc in cursor]

    def list_scan_jobs_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        sort_by: Optional[str] = None,
        sort_dir: str = "desc",
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return paginated scan jobs and total count (page is 1-based)."""
        if page < 1:
            page = 1
        skip = (page - 1) * page_size
        collection = self.db[self.collections.scan_jobs_collection]
        query = filters or {}

        allowed = {"created_at", "status", "project_id", "commit_sha"}
        sort_field = sort_by if sort_by in allowed else "created_at"
        sort_direction = -1 if sort_dir.lower() == "desc" else 1

        total = collection.count_documents(query)
        cursor = (
            collection.find(query)
            .sort(sort_field, sort_direction)
            .skip(skip)
            .limit(page_size)
        )
        items = [self._serialize(doc) for doc in cursor]
        return {"items": items, "total": total}

    def find_stalled_jobs(
        self,
        *,
        running_stale_before: Optional[datetime] = None,
        pending_before: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Find jobs that have been pending or running for too long."""
        clauses: List[Dict[str, Any]] = []
        if running_stale_before:
            clauses.append(
                {
                    "status": "RUNNING",
                    "last_started_at": {"$lt": running_stale_before},
                }
            )
        if pending_before:
            clauses.append(
                {
                    "status": {"$in": ["PENDING", "FAILED_TEMP"]},
                    "updated_at": {"$lt": pending_before},
                }
            )
        if not clauses:
            return []
        query = {"$or": clauses}
        cursor = (
            self.db[self.collections.scan_jobs_collection]
            .find(query)
            .sort("updated_at", 1)
            .limit(limit)
        )
        return [self._serialize(doc) for doc in cursor]

    def find_job_by_component_key(self, component_key: str) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.scan_jobs_collection].find_one(
            {"component_key": component_key}
        )
        return self._serialize(doc) if doc else None
