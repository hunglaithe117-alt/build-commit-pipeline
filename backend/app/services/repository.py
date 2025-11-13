from __future__ import annotations


from app.services.data_sources_repository import DataSourceRepository
from app.services.jobs_repository import JobRepository
from app.services.sonar_runs_repository import SonarRunsRepository
from app.services.dead_letters_repository import DeadLettersRepository
from app.services.outputs_repository import OutputsRepository


class Repository:
    def __init__(self) -> None:
        self.data_sources = DataSourceRepository()
        self.jobs = JobRepository()
        self.sonar_runs = SonarRunsRepository()
        self.dead_letters = DeadLettersRepository()
        self.outputs = OutputsRepository()

    # Data source proxies
    def create_data_source(self, *a, **k):
        return self.data_sources.create_data_source(*a, **k)

    def list_data_sources(self, *a, **k):
        return self.data_sources.list_data_sources(*a, **k)

    def list_data_sources_paginated(self, *a, **k):
        return self.data_sources.list_data_sources_paginated(*a, **k)

    def list_jobs_paginated(self, *a, **k):
        return self.jobs.list_jobs_paginated(*a, **k)

    def get_data_source(self, *a, **k):
        return self.data_sources.get_data_source(*a, **k)

    def find_data_source_by_project_key(self, *a, **k):
        return self.data_sources.find_data_source_by_project_key(*a, **k)

    def update_data_source(self, *a, **k):
        return self.data_sources.update_data_source(*a, **k)

    # Jobs
    def create_job(self, *a, **k):
        return self.jobs.create_job(*a, **k)

    def get_job(self, *a, **k):
        return self.jobs.get_job(*a, **k)

    def update_job(self, *a, **k):
        return self.jobs.update_job(*a, **k)

    def list_jobs(self, *a, **k):
        return self.jobs.list_jobs(*a, **k)

    # Sonar runs
    def upsert_sonar_run(self, *a, **k):
        return self.sonar_runs.upsert_sonar_run(*a, **k)

    def list_sonar_runs(self, *a, **k):
        return self.sonar_runs.list_sonar_runs(*a, **k)

    def list_sonar_runs_paginated(self, *a, **k):
        return self.sonar_runs.list_sonar_runs_paginated(*a, **k)

    def find_sonar_run_by_component(self, *a, **k):
        return self.sonar_runs.find_sonar_run_by_component(*a, **k)

    # Dead letters
    def insert_dead_letter(self, *a, **k):
        return self.dead_letters.insert_dead_letter(*a, **k)

    def list_dead_letters(self, *a, **k):
        return self.dead_letters.list_dead_letters(*a, **k)

    def list_dead_letters_paginated(self, *a, **k):
        return self.dead_letters.list_dead_letters_paginated(*a, **k)

    def get_dead_letter(self, *a, **k):
        return self.dead_letters.get_dead_letter(*a, **k)

    def update_dead_letter(self, *a, **k):
        return self.dead_letters.update_dead_letter(*a, **k)

    # Outputs
    def add_output(self, *a, **k):
        return self.outputs.add_output(*a, **k)

    def list_outputs(self, *a, **k):
        return self.outputs.list_outputs(*a, **k)

    def list_outputs_paginated(self, *a, **k):
        return self.outputs.list_outputs_paginated(*a, **k)

    def get_output(self, *a, **k):
        return self.outputs.get_output(*a, **k)

    def update_output(self, *a, **k):
        return self.outputs.update_output(*a, **k)

    def find_output_by_job_and_path(self, *a, **k):
        return self.outputs.find_output_by_job_and_path(*a, **k)


repository = Repository()
