from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import ReturnDocument

from app.services.repository_base import MongoRepositoryBase

_UNSET = object()


class FailedCommitsRepository(MongoRepositoryBase):
    def insert_failed_commit(self, payload: Dict[str, Any], reason: str) -> Dict[str, Any]:
        now = datetime.utcnow()
        doc = {
            "payload": payload,
            "reason": reason,
            "status": "pending",
            "config_override": payload.get("commit", {}).get("config_override"),
            "config_source": payload.get("commit", {}).get("config_source"),
            "counted": True,
            "fork_search": None,
            "created_at": now,
            "updated_at": now,
        }
        result = self.db[self.collections.failed_commits_collection].insert_one(doc)
        doc["id"] = str(result.inserted_id)
        return doc

    def list_failed_commits(self, limit: int = 200) -> List[Dict[str, Any]]:
        cursor = (
            self.db[self.collections.failed_commits_collection]
            .find()
            .sort("created_at", -1)
            .limit(limit)
        )
        return [self._serialize(doc) for doc in cursor]

    def list_failed_commits_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        sort_by: Optional[str] = None,
        sort_dir: str = "desc",
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return paginated failed commits and total count (page is 1-based)."""
        if page < 1:
            page = 1
        skip = (page - 1) * page_size
        collection = self.db[self.collections.failed_commits_collection]
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

    def get_failed_commit(self, record_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.failed_commits_collection].find_one(
            {"_id": ObjectId(record_id)}
        )
        return self._serialize(doc) if doc else None

    def get_failed_commit_by_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Return the failed commit record created for a specific scan job."""
        doc = self.db[self.collections.failed_commits_collection].find_one(
            {"payload.job_id": job_id}
        )
        return self._serialize(doc) if doc else None

    def update_failed_commit(
        self,
        record_id: str,
        *,
        config_override: Any = None,
        config_source: Any = None,
        status: Optional[str] = None,
        resolved_at: Any = None,
        payload: Any = None,
        counted: Optional[bool] = None,
        fork_search: Any = _UNSET,
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
        if counted is not None:
            updates["counted"] = counted
        if fork_search is not _UNSET:
            updates["fork_search"] = fork_search
        doc = self.db[self.collections.failed_commits_collection].find_one_and_update(
            {"_id": ObjectId(record_id)},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return self._serialize(doc) if doc else None

    def aggregate_missing_forks(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        pipeline = [
            {
                "$match": {
                    "reason": "missing-fork",
                    "payload.repo_slug": {"$ne": None},
                }
            },
            {
                "$group": {
                    "_id": "$payload.repo_slug",
                    "count": {"$sum": 1},
                    "commits": {"$push": "$payload.commit_sha"},
                    "record_ids": {"$push": "$_id"},
                    "updated_at": {"$max": "$updated_at"},
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": limit},
        ]
        cursor = self.db[self.collections.failed_commits_collection].aggregate(
            pipeline
        )
        results = []
        for doc in cursor:
            repo_slug = doc.get("_id")
            results.append(
                {
                    "repo_slug": repo_slug,
                    "count": doc.get("count", 0),
                    "commit_shas": [sha for sha in doc.get("commits", []) if sha],
                    "record_ids": [str(rid) for rid in doc.get("record_ids", [])],
                    "updated_at": doc.get("updated_at"),
                }
            )
        return results

    def list_failed_commits_by_repo(
        self, repo_slug: str, *, reason: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"payload.repo_slug": repo_slug}
        if reason:
            query["reason"] = reason
        cursor = self.db[self.collections.failed_commits_collection].find(query)
        return [self._serialize(doc) for doc in cursor]

    def count_by_job_id(self, job_id: str) -> int:
        """Count failed commits for a specific job."""
        return self.db[self.collections.failed_commits_collection].count_documents(
            {"payload.job_id": job_id}
        )

    def count_by_project_id(self, project_id: str) -> int:
        """Count failed commits for a specific project."""
        return self.db[self.collections.failed_commits_collection].count_documents(
            {"payload.project_id": project_id}
        )
