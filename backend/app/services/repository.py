from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import MongoClient, ReturnDocument

from app.core.config import settings

_UNSET = object()


class MongoRepository:

    def __init__(self) -> None:
        self.client = MongoClient(settings.mongo.uri, **settings.mongo.options)
        self.db = self.client[settings.mongo.database]
        self.collections = settings.storage

    @staticmethod
    def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
        if not doc:
            return doc
        doc = {**doc}
        if "_id" in doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    def create_data_source(
        self,
        *,
        name: str,
        filename: str,
        file_path: str,
        stats: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = datetime.utcnow()
        payload = {
            "name": name,
            "filename": filename,
            "file_path": file_path,
            "status": "pending",
            "stats": stats,
            "created_at": now,
            "updated_at": now,
        }
        result = self.db[self.collections.data_sources_collection].insert_one(payload)
        payload["id"] = str(result.inserted_id)
        return payload

    def list_data_sources(self, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = (
            self.db[self.collections.data_sources_collection]
            .find()
            .sort("created_at", -1)
            .limit(limit)
        )
        return [self._serialize(doc) for doc in cursor]

    def get_data_source(self, data_source_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.data_sources_collection].find_one(
            {"_id": ObjectId(data_source_id)}
        )
        return self._serialize(doc) if doc else None

    def find_data_source_by_project_key(
        self, project_key: str
    ) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.data_sources_collection].find_one(
            {"stats.project_key": project_key}
        )
        return self._serialize(doc) if doc else None

    def update_data_source(
        self,
        data_source_id: str,
        *,
        status: Optional[str] = None,
        stats: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        if status:
            updates["status"] = status
        if stats:
            updates["stats"] = stats
        doc = self.db[self.collections.data_sources_collection].find_one_and_update(
            {"_id": ObjectId(data_source_id)},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return self._serialize(doc) if doc else None

    def create_job(
        self,
        *,
        data_source_id: str,
        job_type: str,
        total: int,
        status: str = "queued",
        sonar_instance: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = datetime.utcnow()
        payload = {
            "data_source_id": data_source_id,
            "job_type": job_type,
            "status": status,
            "processed": 0,
            "total": total,
            "last_error": None,
            "current_commit": None,
            "sonar_instance": sonar_instance,
            "created_at": now,
            "updated_at": now,
        }
        result = self.db[self.collections.jobs_collection].insert_one(payload)
        payload["id"] = str(result.inserted_id)
        return payload

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.jobs_collection].find_one(
            {"_id": ObjectId(job_id)}
        )
        return self._serialize(doc) if doc else None

    def update_job(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        processed: Optional[int] = None,
        last_error: Optional[str] = None,
        processed_delta: Optional[int] = None,
        current_commit: Any = _UNSET,
        sonar_instance: Any = _UNSET,
    ) -> Optional[Dict[str, Any]]:
        set_updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        if status:
            set_updates["status"] = status
        if processed is not None:
            set_updates["processed"] = processed
        if last_error is not None:
            set_updates["last_error"] = last_error
        if current_commit is not _UNSET:
            set_updates["current_commit"] = current_commit
        if sonar_instance is not _UNSET:
            set_updates["sonar_instance"] = sonar_instance
        update_doc: Dict[str, Any] = {"$set": set_updates}
        if processed_delta is not None:
            update_doc["$inc"] = {"processed": processed_delta}
        doc = self.db[self.collections.jobs_collection].find_one_and_update(
            {"_id": ObjectId(job_id)},
            update_doc,
            return_document=ReturnDocument.AFTER,
        )
        return self._serialize(doc) if doc else None

    def acquire_instance_lock(
        self,
        instance_name: str,
        job_id: str,
        data_source_id: str,
        max_concurrent: int = 2,
    ) -> bool:
        """
        Acquire a lock slot for the given instance.
        Returns True if lock acquired, False if instance is at capacity.
        """
        from app.core.config import settings

        now = datetime.utcnow()
        collection = self.db[self.collections.instance_locks_collection]

        # Check if this job already has a lock
        existing = collection.find_one(
            {"instance": instance_name, "active_jobs.job_id": job_id}
        )
        if existing:
            return True

        max_jobs = max_concurrent or settings.sonarqube.max_concurrent_jobs_per_instance

        # Ensure the instance document exists first
        collection.update_one(
            {"instance": instance_name},
            {
                "$setOnInsert": {
                    "instance": instance_name,
                    "active_jobs": [],
                    "created_at": now,
                }
            },
            upsert=True,
        )

        # Try to acquire a slot by pushing to active_jobs only if under capacity
        # We can't use $expr with upsert, so we use a simple query and check size after
        result = collection.update_one(
            {
                "instance": instance_name,
                f"active_jobs.{max_jobs - 1}": {
                    "$exists": False
                },  # Array has less than max_jobs elements
            },
            {
                "$push": {
                    "active_jobs": {
                        "job_id": job_id,
                        "data_source_id": data_source_id,
                        "acquired_at": now,
                    }
                },
                "$set": {"updated_at": now},
            },
        )

        # Return True if we successfully added the job
        return result.modified_count > 0

    def release_instance_lock(
        self, instance_name: str, job_id: Optional[str] = None
    ) -> None:
        """
        Release a lock slot for the given instance.
        If job_id is provided, only that specific job is removed.
        """
        collection = self.db[self.collections.instance_locks_collection]

        if job_id:
            # Remove specific job from active_jobs array
            collection.update_one(
                {"instance": instance_name},
                {
                    "$pull": {"active_jobs": {"job_id": job_id}},
                    "$set": {"updated_at": datetime.utcnow()},
                },
            )
        else:
            # Legacy: clear all jobs (for backward compatibility)
            collection.update_one(
                {"instance": instance_name},
                {
                    "$set": {
                        "active_jobs": [],
                        "updated_at": datetime.utcnow(),
                    }
                },
            )

    def get_instance_capacity(self, instance_name: str) -> Dict[str, int]:
        """
        Get the current capacity status of a SonarQube instance.
        Returns dict with 'active_count' and 'max_concurrent'.
        """
        from app.core.config import settings

        collection = self.db[self.collections.instance_locks_collection]
        doc = collection.find_one({"instance": instance_name})

        active_jobs = doc.get("active_jobs", []) if doc else []
        return {
            "active_count": len(active_jobs),
            "max_concurrent": settings.sonarqube.max_concurrent_jobs_per_instance,
            "available_slots": settings.sonarqube.max_concurrent_jobs_per_instance
            - len(active_jobs),
            "active_jobs": [j.get("job_id") for j in active_jobs],
        }

    def list_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        cursor = (
            self.db[self.collections.jobs_collection]
            .find()
            .sort("created_at", -1)
            .limit(limit)
        )
        return [self._serialize(doc) for doc in cursor]

    def upsert_sonar_run(
        self,
        *,
        data_source_id: str,
        project_key: str,
        status: str,
        analysis_id: Optional[str] = None,
        metrics_path: Optional[str] = None,
        commit_sha: Optional[str] = None,
        job_id: Optional[str] = None,
        log_path: Optional[str] = None,
        message: Optional[str] = None,
        component_key: Optional[str] = None,
        sonar_instance: Optional[str] = None,
        sonar_host: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = datetime.utcnow()
        collection = self.db[self.collections.sonar_runs_collection]
        query = {
            "data_source_id": data_source_id,
            "project_key": project_key,
        }
        if commit_sha is not None:
            query["commit_sha"] = commit_sha
        if component_key is not None:
            query["component_key"] = component_key
        set_fields: Dict[str, Any] = {
            "status": status,
            "analysis_id": analysis_id,
            "metrics_path": metrics_path,
            "commit_sha": commit_sha,
            "job_id": job_id,
            "log_path": log_path,
            "message": message,
            "component_key": component_key,
            "finished_at": now if status in {"succeeded", "failed"} else None,
            "updated_at": now,
        }
        if sonar_instance is not None:
            set_fields["sonar_instance"] = sonar_instance
        if sonar_host is not None:
            set_fields["sonar_host"] = sonar_host
        doc = collection.find_one_and_update(
            query,
            {
                "$set": set_fields,
                "$setOnInsert": {"started_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return self._serialize(doc)

    def list_sonar_runs(self, limit: int = 100) -> List[Dict[str, Any]]:
        cursor = (
            self.db[self.collections.sonar_runs_collection]
            .find()
            .sort("started_at", -1)
            .limit(limit)
        )
        return [self._serialize(doc) for doc in cursor]

    def find_sonar_run_by_component(
        self, component_key: str
    ) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.sonar_runs_collection].find_one(
            {"component_key": component_key}
        )
        return self._serialize(doc) if doc else None

    def insert_dead_letter(
        self, payload: Dict[str, Any], reason: str
    ) -> Dict[str, Any]:
        now = datetime.utcnow()
        doc = {
            "payload": payload,
            "reason": reason,
            "created_at": now,
        }
        result = self.db[self.collections.dead_letter_collection].insert_one(doc)
        doc["id"] = str(result.inserted_id)
        return doc

    def add_output(
        self,
        *,
        job_id: str,
        path: str,
        metrics: List[str],
        record_count: int,
        data_source_id: Optional[str] = None,
        project_key: Optional[str] = None,
        repo_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = datetime.utcnow()
        doc = {
            "job_id": job_id,
            "path": path,
            "metrics": metrics,
            "record_count": record_count,
            "created_at": now,
        }
        if data_source_id:
            doc["data_source_id"] = data_source_id
        if project_key:
            doc["project_key"] = project_key
        if repo_name:
            doc["repo_name"] = repo_name
        result = self.db[self.collections.outputs_collection].insert_one(doc)
        doc["id"] = str(result.inserted_id)
        return doc

    def list_outputs(self, limit: int = 100) -> List[Dict[str, Any]]:
        cursor = (
            self.db[self.collections.outputs_collection]
            .find()
            .sort("created_at", -1)
            .limit(limit)
        )
        return [self._serialize(doc) for doc in cursor]

    def get_output(self, output_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.outputs_collection].find_one(
            {"_id": ObjectId(output_id)}
        )
        return self._serialize(doc) if doc else None

    def update_output(
        self,
        output_id: str,
        *,
        metrics: Optional[List[str]] = None,
        record_count: Optional[int] = None,
        data_source_id: Optional[str] = None,
        project_key: Optional[str] = None,
        repo_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update an existing output record."""
        updates: Dict[str, Any] = {}
        if metrics is not None:
            updates["metrics"] = metrics
        if record_count is not None:
            updates["record_count"] = record_count
        if data_source_id is not None:
            updates["data_source_id"] = data_source_id
        if project_key is not None:
            updates["project_key"] = project_key
        if repo_name is not None:
            updates["repo_name"] = repo_name
        if not updates:
            return self.get_output(output_id)
        doc = self.db[self.collections.outputs_collection].find_one_and_update(
            {"_id": ObjectId(output_id)},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return self._serialize(doc) if doc else None

    def find_output_by_job_and_path(
        self, job_id: str, path: str
    ) -> Optional[Dict[str, Any]]:
        """Find an output record by job_id and file path."""
        doc = self.db[self.collections.outputs_collection].find_one(
            {"job_id": job_id, "path": path}
        )
        return self._serialize(doc) if doc else None


repository = MongoRepository()
