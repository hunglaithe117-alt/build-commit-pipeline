from __future__ import annotations


from app.services.projects_repository import ProjectsRepository
from app.services.scan_jobs_repository import ScanJobsRepository
from app.services.scan_results_repository import ScanResultsRepository
from app.services.failed_commits_repository import FailedCommitsRepository


class Repository:
    def __init__(self) -> None:
        self.projects = ProjectsRepository()
        self.scan_jobs = ScanJobsRepository()
        self.scan_results = ScanResultsRepository()
        self.failed_commits = FailedCommitsRepository()

    # Project proxies
    def create_project(self, *a, **k):
        return self.projects.create_project(*a, **k)

    def list_projects(self, *a, **k):
        return self.projects.list_projects(*a, **k)

    def list_projects_paginated(self, *a, **k):
        return self.projects.list_projects_paginated(*a, **k)

    def get_project(self, *a, **k):
        return self.projects.get_project(*a, **k)

    def find_project_by_key(self, *a, **k):
        return self.projects.find_project_by_key(*a, **k)

    def update_project(self, *a, **k):
        return self.projects.update_project(*a, **k)

    # Scan jobs
    def create_scan_job(self, *a, **k):
        return self.scan_jobs.create_scan_job(*a, **k)

    def get_scan_job(self, *a, **k):
        return self.scan_jobs.get_scan_job(*a, **k)

    def claim_scan_job(self, *a, **k):
        return self.scan_jobs.claim_job(*a, **k)

    def update_scan_job(self, *a, **k):
        return self.scan_jobs.update_scan_job(*a, **k)

    def list_scan_jobs(self, *a, **k):
        return self.scan_jobs.list_scan_jobs(*a, **k)

    def list_scan_jobs_paginated(self, *a, **k):
        return self.scan_jobs.list_scan_jobs_paginated(*a, **k)

    def find_scan_job_by_component(self, *a, **k):
        return self.scan_jobs.find_job_by_component_key(*a, **k)

    def find_stalled_scan_jobs(self, *a, **k):
        return self.scan_jobs.find_stalled_jobs(*a, **k)

    def list_scan_jobs_by_status(self, *a, **k):
        return self.scan_jobs.list_jobs_by_status(*a, **k)

    # Scan results
    def upsert_scan_result(self, *a, **k):
        return self.scan_results.upsert_result(*a, **k)

    def list_scan_results(self, *a, **k):
        return self.scan_results.list_results(*a, **k)

    def list_scan_results_paginated(self, *a, **k):
        return self.scan_results.list_results_paginated(*a, **k)

    def get_scan_result_by_job(self, *a, **k):
        return self.scan_results.get_by_job_id(*a, **k)

    def get_scan_result(self, *a, **k):
        return self.scan_results.get_result(*a, **k)

    def list_scan_results_by_project(self, *a, **k):
        return self.scan_results.list_by_project(*a, **k)

    # Failed commits
    def insert_failed_commit(self, *a, **k):
        return self.failed_commits.insert_failed_commit(*a, **k)

    def list_failed_commits(self, *a, **k):
        return self.failed_commits.list_failed_commits(*a, **k)

    def list_failed_commits_paginated(self, *a, **k):
        return self.failed_commits.list_failed_commits_paginated(*a, **k)

    def get_failed_commit(self, *a, **k):
        return self.failed_commits.get_failed_commit(*a, **k)

    def get_failed_commit_by_job(self, *a, **k):
        return self.failed_commits.get_failed_commit_by_job(*a, **k)

    def update_failed_commit(self, *a, **k):
        return self.failed_commits.update_failed_commit(*a, **k)

    def count_failed_commits_by_job(self, *a, **k):
        return self.failed_commits.count_by_job_id(*a, **k)

    def count_failed_commits_by_project(self, *a, **k):
        return self.failed_commits.count_by_project_id(*a, **k)


repository = Repository()
