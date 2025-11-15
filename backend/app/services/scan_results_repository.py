from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument
from bson import ObjectId

from app.services.repository_base import MongoRepositoryBase


class ScanResultsRepository(MongoRepositoryBase):
    def upsert_result(
        self,
        *,
        project_id: str,
        job_id: str,
        sonar_project_key: str,
        sonar_analysis_id: str,
        metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = datetime.utcnow()
        collection = self.db[self.collections.scan_results_collection]
        doc = collection.find_one_and_update(
            {"job_id": job_id},
            {
                "$set": {
                    "project_id": project_id,
                    "sonar_project_key": sonar_project_key,
                    "sonar_analysis_id": sonar_analysis_id,
                    "metrics": metrics,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return self._serialize(doc)

    def list_results(self, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = (
            self.db[self.collections.scan_results_collection]
            .find()
            .sort("created_at", -1)
            .limit(limit)
        )
        return [self._serialize(doc) for doc in cursor]

    def list_results_paginated(
        self,
        page: int = 1,
        page_size: int = 50,
        sort_by: Optional[str] = None,
        sort_dir: str = "desc",
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if page < 1:
            page = 1
        skip = (page - 1) * page_size
        collection = self.db[self.collections.scan_results_collection]
        query = filters or {}

        allowed = {"created_at", "sonar_project_key", "sonar_analysis_id"}
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

    def get_by_job_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.scan_results_collection].find_one(
            {"job_id": job_id}
        )
        return self._serialize(doc) if doc else None

    def get_result(self, result_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.scan_results_collection].find_one(
            {"_id": ObjectId(result_id)}
        )
        return self._serialize(doc) if doc else None

    def list_by_project(self, project_id: str) -> List[Dict[str, Any]]:
        cursor = (
            self.db[self.collections.scan_results_collection]
            .find({"project_id": project_id})
            .sort("created_at", 1)
        )
        return [self._serialize(doc) for doc in cursor]
