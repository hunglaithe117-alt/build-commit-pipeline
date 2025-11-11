export type CSVSummary = {
  project_name?: string | null;
  project_key?: string | null;
  total_builds: number;
  total_commits: number;
  unique_branches: number;
  unique_repos: number;
  first_commit?: string | null;
  last_commit?: string | null;
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
};

export type Job = {
  id: string;
  data_source_id: string;
  status: string;
  processed: number;
  total: number;
  last_error?: string | null;
  current_commit?: string | null;
  created_at: string;
  updated_at: string;
};

export type SonarRun = {
  id: string;
  data_source_id: string;
  project_key: string;
  commit_sha?: string | null;
  job_id?: string | null;
  component_key?: string | null;
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
  path: string;
  record_count: number;
  metrics: string[];
  created_at: string;
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

export const api = {
  listDataSources: () => apiFetch<DataSource[]>("/api/data-sources"),
  uploadDataSource: async (file: File, name: string) => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(`${API_BASE_URL}/api/data-sources?name=${encodeURIComponent(name)}`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return (await response.json()) as DataSource;
  },
  triggerCollection: (id: string) => apiFetch(`/api/data-sources/${id}/collect`, { method: "POST" }),
  listJobs: () => apiFetch<Job[]>("/api/jobs"),
  listRuns: () => apiFetch<SonarRun[]>("/api/sonar/runs"),
  listOutputs: () => apiFetch<OutputDataset[]>("/api/outputs"),
};
