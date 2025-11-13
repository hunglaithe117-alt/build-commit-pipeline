export type CSVSummary = {
  project_name?: string | null;
  project_key?: string | null;
  total_builds: number;
  total_commits: number;
  unique_branches: number;
  first_commit?: string | null;
  last_commit?: string | null;
};

export type SonarConfig = {
  content: string;
  source: string;
  filename?: string | null;
  updated_at?: string;
};

export type DataSource = {
  id: string;
  name: string;
  filename: string;
  status: string;
  file_path: string;
  stats?: CSVSummary;
  created_at: string;
  updated_at: string;
  sonar_config?: SonarConfig | null;
};

export type Job = {
  id: string;
  data_source_id: string;
  status: string;
  processed: number;
  total: number;
  failed_count?: number;
  last_error?: string | null;
  current_commit?: string | null;
  sonar_instance?: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkerTask = {
  id: string;
  name: string;
  current_commit?: string | null;
  current_repo?: string | null;
};

export type WorkerInfo = {
  name: string;
  active_tasks: number;
  max_concurrency: number;
  tasks: WorkerTask[];
};

export type WorkersStats = {
  total_workers: number;
  max_concurrency: number;
  active_scan_tasks: number;
  queued_scan_tasks: number;
  workers: WorkerInfo[];
  error?: string;
};

export type SonarRun = {
  id: string;
  data_source_id: string;
  project_key: string;
  commit_sha?: string | null;
  job_id?: string | null;
  component_key?: string | null;
  sonar_instance?: string | null;
  sonar_host?: string | null;
  status: string;
  analysis_id?: string | null;
  metrics_path?: string | null;
  log_path?: string | null;
  message?: string | null;
  started_at: string;
  finished_at?: string | null;
};

export type OutputDataset = {
  id: string;
  job_id: string;
  data_source_id?: string | null;
  project_key?: string | null;
  repo_name?: string | null;
  path: string;
  record_count: number;
  metrics: string[];
  created_at: string;
};

export type DeadLetter = {
  id: string;
  payload: Record<string, any>;
  reason: string;
  status: string;
  config_override?: string | null;
  config_source?: string | null;
  created_at: string;
  updated_at?: string | null;
  resolved_at?: string | null;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request to ${path} failed`);
  }
  if (response.status === 204) {
    return {} as T;
  }
  return (await response.json()) as T;
}

function buildPath(path: string, qs?: Record<string, any>) {
  if (!qs) return path;
  const params = new URLSearchParams();
  for (const k of Object.keys(qs)) {
    const v = qs[k];
    if (v === undefined || v === null) continue;
    params.append(k, String(v));
  }
  const suffix = params.toString();
  return suffix ? `${path}?${suffix}` : path;
}

export const api = {
  listDataSources: (limit?: number) => apiFetch<DataSource[]>(buildPath("/api/data-sources", { limit })),
  listDataSourcesPaginated: (
    page?: number,
    pageSize?: number,
    sortBy?: string,
    sortDir?: string,
    filters?: Record<string, any>
  ) =>
    apiFetch<{ items: DataSource[]; total: number }>(
      buildPath("/api/data-sources", { page: page ?? 1, page_size: pageSize, sort_by: sortBy, sort_dir: sortDir, filters: filters ? JSON.stringify(filters) : undefined })
    ),
  getDataSource: (id: string) => apiFetch<DataSource>(`/api/data-sources/${id}`),
  uploadDataSource: async (file: File, name: string, _options?: { configContent?: string; configSource?: string; configFilename?: string }) => {
    const formData = new FormData();
    formData.append("name_form", name);
    // Only file-based sonar.properties uploads are supported from the UI.
    formData.append("file", file);
    const response = await fetch(`${API_BASE_URL}/api/data-sources`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return (await response.json()) as DataSource;
  },
  updateDataSourceConfig: (id: string, payload: { content: string; source?: string; filename?: string | null }) =>
    apiFetch<DataSource>(`/api/data-sources/${id}/config`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  triggerCollection: (id: string) => apiFetch(`/api/data-sources/${id}/collect`, { method: "POST" }),
  listJobs: (limit?: number) => apiFetch<Job[]>(buildPath("/api/jobs", { limit })),
  listJobsPaginated: (
    page?: number,
    pageSize?: number,
    sortBy?: string,
    sortDir?: string,
    filters?: Record<string, any>
  ) =>
    apiFetch<{ items: Job[]; total: number }>(
      buildPath("/api/jobs", { page: page ?? 1, page_size: pageSize, sort_by: sortBy, sort_dir: sortDir, filters: filters ? JSON.stringify(filters) : undefined })
    ),
  getWorkersStats: () => apiFetch<WorkersStats>("/api/jobs/workers-stats"),
  listRuns: (limit?: number) => apiFetch<SonarRun[]>(buildPath("/api/sonar/runs", { limit })),
  listRunsPaginated: (
    page?: number,
    pageSize?: number,
    sortBy?: string,
    sortDir?: string,
    filters?: Record<string, any>
  ) =>
    apiFetch<{ items: SonarRun[]; total: number }>(
      buildPath("/api/sonar/runs", { page: page ?? 1, page_size: pageSize, sort_by: sortBy, sort_dir: sortDir, filters: filters ? JSON.stringify(filters) : undefined })
    ),
  listOutputs: (limit?: number) => apiFetch<OutputDataset[]>(buildPath("/api/outputs", { limit })),
  listOutputsPaginated: (
    page?: number,
    pageSize?: number,
    sortBy?: string,
    sortDir?: string,
    filters?: Record<string, any>
  ) =>
    apiFetch<{ items: OutputDataset[]; total: number }>(
      buildPath("/api/outputs", { page: page ?? 1, page_size: pageSize, sort_by: sortBy, sort_dir: sortDir, filters: filters ? JSON.stringify(filters) : undefined })
    ),
  listDeadLetters: (limit?: number) => apiFetch<DeadLetter[]>(buildPath("/api/dead-letters", { limit })),
  listDeadLettersPaginated: (
    page?: number,
    pageSize?: number,
    sortBy?: string,
    sortDir?: string,
    filters?: Record<string, any>
  ) =>
    apiFetch<{ items: DeadLetter[]; total: number }>(
      buildPath("/api/dead-letters", { page: page ?? 1, page_size: pageSize, sort_by: sortBy, sort_dir: sortDir, filters: filters ? JSON.stringify(filters) : undefined })
    ),
  updateDeadLetter: (id: string, payload: { config_override: string; config_source?: string }) =>
    apiFetch<DeadLetter>(`/api/dead-letters/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  retryDeadLetter: (id: string, payload: { config_override?: string; config_source?: string }) =>
    apiFetch<DeadLetter>(`/api/dead-letters/${id}/retry`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
