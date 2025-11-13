from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import ReturnDocument

from app.services.repository_base import MongoRepositoryBase


class DeadLettersRepository(MongoRepositoryBase):
    def insert_dead_letter(self, payload: Dict[str, Any], reason: str) -> Dict[str, Any]:
        now = datetime.utcnow()
        doc = {
            "payload": payload,
            "reason": reason,
            "status": "pending",
            "config_override": payload.get("commit", {}).get("config_override"),
            "config_source": payload.get("commit", {}).get("config_source"),
            "created_at": now,
            "updated_at": now,
        }
        result = self.db[self.collections.dead_letter_collection].insert_one(doc)
        doc["id"] = str(result.inserted_id)
        return doc

    def list_dead_letters(self, limit: int = 200) -> List[Dict[str, Any]]:
        cursor = (
            self.db[self.collections.dead_letter_collection]
            .find()
            .sort("created_at", -1)
            .limit(limit)
        )
        return [self._serialize(doc) for doc in cursor]

    def list_dead_letters_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        sort_by: Optional[str] = None,
        sort_dir: str = "desc",
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return paginated dead letters and total count (page is 1-based)."""
        if page < 1:
            page = 1
        skip = (page - 1) * page_size
        collection = self.db[self.collections.dead_letter_collection]
        query = filters or {}

        allowed = {"created_at", "status"}
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

    def get_dead_letter(self, dead_letter_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.dead_letter_collection].find_one(
            {"_id": ObjectId(dead_letter_id)}
        )
        return self._serialize(doc) if doc else None

    def update_dead_letter(
        self,
        dead_letter_id: str,
        *,
        config_override: Any = None,
        config_source: Any = None,
        status: Optional[str] = None,
        resolved_at: Any = None,
        payload: Any = None,
    ) -> Optional[Dict[str, Any]]:
        updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        if config_override is not None:
            updates["config_override"] = config_override
        if config_source is not None:
            updates["config_source"] = config_source
        if status:
            updates["status"] = status
        if resolved_at is not None:
            updates["resolved_at"] = resolved_at
        if payload is not None:
            updates["payload"] = payload
        doc = self.db[self.collections.dead_letter_collection].find_one_and_update(
            {"_id": ObjectId(dead_letter_id)},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return self._serialize(doc) if doc else None

    def count_by_job_id(self, job_id: str) -> int:
        """Count dead letters for a specific job."""
        return self.db[self.collections.dead_letter_collection].count_documents(
            {"payload.job_id": job_id}
        )

    def count_by_data_source_id(self, data_source_id: str) -> int:
        """Count dead letters for a specific data source."""
        return self.db[self.collections.dead_letter_collection].count_documents(
            {"payload.data_source_id": data_source_id}
        )
