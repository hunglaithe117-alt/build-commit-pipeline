from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument
from bson import ObjectId

from app.services.repository_base import MongoRepositoryBase

_UNSET = object()


class ProjectsRepository(MongoRepositoryBase):
    def create_project(
        self,
        *,
        project_name: str,
        project_key: str,
        total_builds: int | str,
        total_commits: int | str,
        source_filename: Optional[str] = None,
        source_path: Optional[str] = None,
        sonar_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = datetime.utcnow()
        payload = {
            "project_name": project_name,
            "project_key": project_key,
            "total_builds": str(total_builds),
            "total_commits": str(total_commits),
            "processed_commits": 0,
            "failed_commits": 0,
            "status": "pending",
            "source_filename": source_filename,
            "source_path": source_path,
            "created_at": now,
            "updated_at": now,
        }
        if sonar_config:
            payload["sonar_config"] = sonar_config
        result = self.db[self.collections.projects_collection].insert_one(payload)
        payload["id"] = str(result.inserted_id)
        return payload

    def list_projects(self, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = (
            self.db[self.collections.projects_collection]
            .find()
            .sort("created_at", -1)
            .limit(limit)
        )
        return [self._serialize(doc) for doc in cursor]

    def list_projects_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        sort_by: Optional[str] = None,
        sort_dir: str = "desc",
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return paginated projects and total count (page is 1-based)."""
        if page < 1:
            page = 1
        skip = (page - 1) * page_size
        collection = self.db[self.collections.projects_collection]
        query = filters or {}

        allowed = {"created_at", "project_name", "status"}
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

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.projects_collection].find_one(
            {"_id": ObjectId(project_id)}
        )
        return self._serialize(doc) if doc else None

    def find_project_by_key(self, project_key: str) -> Optional[Dict[str, Any]]:
        doc = self.db[self.collections.projects_collection].find_one(
            {"project_key": project_key}
        )
        return self._serialize(doc) if doc else None

    def update_project(
        self,
        project_id: str,
        *,
        status: Optional[str] = None,
        sonar_config: Any = _UNSET,
        processed_commits: Optional[int] = None,
        failed_commits: Optional[int] = None,
        processed_delta: Optional[int] = None,
        failed_delta: Optional[int] = None,
        total_builds: Any = _UNSET,
        total_commits: Any = _UNSET,
    ) -> Optional[Dict[str, Any]]:
        updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        if status:
            updates["status"] = status
        if processed_commits is not None:
            updates["processed_commits"] = processed_commits
        if failed_commits is not None:
            updates["failed_commits"] = failed_commits
        if sonar_config is not _UNSET:
            updates["sonar_config"] = sonar_config
        if total_builds is not _UNSET:
            updates["total_builds"] = str(total_builds)
        if total_commits is not _UNSET:
            updates["total_commits"] = str(total_commits)

        inc: Dict[str, Any] = {}
        if processed_delta:
            inc["processed_commits"] = processed_delta
        if failed_delta:
            inc["failed_commits"] = failed_delta

        update_doc: Dict[str, Any] = {"$set": updates}
        if inc:
            update_doc["$inc"] = inc

        doc = self.db[self.collections.projects_collection].find_one_and_update(
            {"_id": ObjectId(project_id)},
            update_doc,
            return_document=ReturnDocument.AFTER,
        )
        return self._serialize(doc) if doc else None
