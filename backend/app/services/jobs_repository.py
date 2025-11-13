from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import ReturnDocument

from app.services.repository_base import MongoRepositoryBase

_UNSET = object()


class JobRepository(MongoRepositoryBase):
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

    def list_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        cursor = (
            self.db[self.collections.jobs_collection]
            .find()
            .sort("created_at", -1)
            .limit(limit)
        )
        return [self._serialize(doc) for doc in cursor]
