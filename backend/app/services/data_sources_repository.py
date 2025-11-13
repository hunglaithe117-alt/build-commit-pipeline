from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument
from bson import ObjectId

from app.services.repository_base import MongoRepositoryBase


class DataSourceRepository(MongoRepositoryBase):
    def create_data_source(
        self,
        *,
        name: str,
        filename: str,
        file_path: str,
        stats: Optional[Dict[str, Any]] = None,
        sonar_config: Optional[Dict[str, Any]] = None,
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
        if sonar_config:
            payload["sonar_config"] = sonar_config
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

    def list_data_sources_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        sort_by: Optional[str] = None,
        sort_dir: str = "desc",
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return paginated data sources and total count (page is 1-based)."""
        if page < 1:
            page = 1
        skip = (page - 1) * page_size
        collection = self.db[self.collections.data_sources_collection]
        query = filters or {}

        allowed = {"created_at", "name"}
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
        sonar_config: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        if status:
            updates["status"] = status
        if stats:
            updates["stats"] = stats
        if sonar_config is not None:
            updates["sonar_config"] = sonar_config
        doc = self.db[self.collections.data_sources_collection].find_one_and_update(
            {"_id": ObjectId(data_source_id)},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return self._serialize(doc) if doc else None
