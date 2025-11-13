from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument

from app.services.repository_base import MongoRepositoryBase


class SonarRunsRepository(MongoRepositoryBase):
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
        query: Dict[str, Any] = {
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
