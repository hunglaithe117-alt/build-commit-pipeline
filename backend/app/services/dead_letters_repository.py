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
