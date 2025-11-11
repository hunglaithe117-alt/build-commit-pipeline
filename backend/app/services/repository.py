from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import MongoClient, ReturnDocument

from app.core.config import settings

_UNSET = object()


class MongoRepository:
    """MongoDB helper focused on pipeline collections."""

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

    def find_data_source_by_project_key(self, project_key: str) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.data_sources_collection].find_one(
            {"stats.project_key": project_key}
        )
        return self._serialize(doc) if doc else None

    def update_data_source(
        self, data_source_id: str, *, status: Optional[str] = None, stats: Optional[Dict[str, Any]] = None
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
            "created_at": now,
            "updated_at": now,
        }
        result = self.db[self.collections.jobs_collection].insert_one(payload)
        payload["id"] = str(result.inserted_id)
        return payload

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.jobs_collection].find_one({"_id": ObjectId(job_id)})
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
        update_doc: Dict[str, Any] = {"$set": set_updates}
        if processed_delta is not None:
            update_doc["$inc"] = {"processed": processed_delta}
        doc = self.db[self.collections.jobs_collection].find_one_and_update(
            {"_id": ObjectId(job_id)},
            update_doc,
            return_document=ReturnDocument.AFTER,
        )
        return self._serialize(doc) if doc else None

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
    ) -> Dict[str, Any]:
        now = datetime.utcnow()
        collection = self.db[self.collections.sonar_runs_collection]
        doc = collection.find_one_and_update(
            {
                "data_source_id": data_source_id,
                "project_key": project_key,
                "commit_sha": commit_sha,
            },
            {
                "$set": {
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
                },
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

    def find_sonar_run_by_component(self, component_key: str) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.sonar_runs_collection].find_one(
            {"component_key": component_key}
        )
        return self._serialize(doc) if doc else None

    def insert_dead_letter(self, payload: Dict[str, Any], reason: str) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
        now = datetime.utcnow()
        doc = {
            "job_id": job_id,
            "path": path,
            "metrics": metrics,
            "record_count": record_count,
            "created_at": now,
        }
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


repository = MongoRepository()
