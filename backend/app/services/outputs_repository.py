from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import ReturnDocument

from app.services.repository_base import MongoRepositoryBase


class OutputsRepository(MongoRepositoryBase):
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

    def list_outputs_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        sort_by: Optional[str] = None,
        sort_dir: str = "desc",
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return paginated outputs and total count (page is 1-based)."""
        if page < 1:
            page = 1
        skip = (page - 1) * page_size
        collection = self.db[self.collections.outputs_collection]
        query = filters or {}

        allowed = {"created_at", "record_count", "job_id"}
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
