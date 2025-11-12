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
  last_error?: string | null;
  current_commit?: string | null;
  sonar_instance?: string | null;
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

export const api = {
  listDataSources: () => apiFetch<DataSource[]>("/api/data-sources"),
  getDataSource: (id: string) => apiFetch<DataSource>(`/api/data-sources/${id}`),
  uploadDataSource: async (
    file: File,
    name: string,
    options?: { configContent?: string; configSource?: string; configFilename?: string }
  ) => {
    const formData = new FormData();
    formData.append("name_form", name);
    formData.append("file", file);
    if (options?.configContent) {
      formData.append("sonar_config_content", options.configContent);
      if (options.configSource) {
        formData.append("sonar_config_source", options.configSource);
      }
      if (options.configFilename) {
        formData.append("sonar_config_filename", options.configFilename);
      }
    }
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
  listJobs: () => apiFetch<Job[]>("/api/jobs"),
  listRuns: () => apiFetch<SonarRun[]>("/api/sonar/runs"),
  listOutputs: () => apiFetch<OutputDataset[]>("/api/outputs"),
  listDeadLetters: () => apiFetch<DeadLetter[]>("/api/dead-letters"),
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
