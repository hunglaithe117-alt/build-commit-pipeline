export type SonarConfig = {
  filename: string;
  file_path: string;
  updated_at?: string;
};

export enum ProjectStatus {
  PENDING = "PENDING",
  PROCESSING = "PROCESSING",
  FINISHED = "FINISHED",
}

export enum ScanJobStatus {
  PENDING = "PENDING",
  RUNNING = "RUNNING",
  SUCCESS = "SUCCESS",
  FAILED_TEMP = "FAILED_TEMP",
  FAILED_PERMANENT = "FAILED_PERMANENT",
}

export type Project = {
  id: string;
  project_name: string;
  project_key: string;
  total_builds: number;
  total_commits: number;
  processed_commits: number;
  failed_commits: number;
  status: ProjectStatus;
  source_filename?: string | null;
  source_path?: string | null;
  created_at: string;
  updated_at: string;
  sonar_config?: SonarConfig | null;
};

export type ScanJob = {
  id: string;
  project_id: string;
  project_key?: string | null;
  commit_sha: string;
  status: ScanJobStatus;
  retry_count: number;
  max_retries: number;
  last_error?: string | null;
  sonar_instance?: string | null;
  component_key?: string | null;
  config_override?: string | null;
  config_source?: string | null;
  repository_url?: string | null;
  repo_slug?: string | null;
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

export type ScanResult = {
  id: string;
  job_id: string;
  project_id: string;
  sonar_project_key: string;
  metrics: Record<string, string>;
  created_at: string;
};

export type TriggerCollectionResult =
  | { status: "queued" }
  | { status: "retrying_failed"; count: number };

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
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
  listProjects: (limit?: number) =>
    apiFetch<Project[]>(buildPath("/api/projects", { limit })),
  listProjectsPaginated: (
    page?: number,
    pageSize?: number,
    sortBy?: string,
    sortDir?: string,
    filters?: Record<string, any>
  ) =>
    apiFetch<{ items: Project[]; total: number }>(
      buildPath("/api/projects", {
        page: page ?? 1,
        page_size: pageSize,
        sort_by: sortBy,
        sort_dir: sortDir,
        filters: filters ? JSON.stringify(filters) : undefined,
      })
    ),
  getProject: (id: string) => apiFetch<Project>(`/api/projects/${id}`),
  uploadProject: async (
    file: File,
    name: string,
    options?: { sonarConfig?: File }
  ) => {
    const formData = new FormData();
    formData.append("name_form", name);
    formData.append("file", file);
    if (options?.sonarConfig) {
      formData.append("sonar_config_file", options.sonarConfig);
    }
    const response = await fetch(`${API_BASE_URL}/api/projects`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return (await response.json()) as Project;
  },
  updateProjectConfig: async (id: string, file: File) => {
    const formData = new FormData();
    formData.append("config_file", file);
    const response = await fetch(`${API_BASE_URL}/api/projects/${id}/config`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return (await response.json()) as Project;
  },
  triggerCollection: (id: string) =>
    apiFetch<TriggerCollectionResult>(`/api/projects/${id}/collect`, {
      method: "POST",
    }),
  listScanJobsPaginated: (
    page?: number,
    pageSize?: number,
    sortBy?: string,
    sortDir?: string,
    filters?: Record<string, any>
  ) =>
    apiFetch<{ items: ScanJob[]; total: number }>(
      buildPath("/api/scan-jobs", {
        page: page ?? 1,
        page_size: pageSize,
        sort_by: sortBy,
        sort_dir: sortDir,
        filters: filters ? JSON.stringify(filters) : undefined,
      })
    ),
  getWorkersStats: () => apiFetch<WorkersStats>("/api/scan-jobs/workers-stats"),
  retryScanJob: (
    id: string,
    payload: { config_override?: string; config_source?: string }
  ) =>
    apiFetch<ScanJob>(`/api/scan-jobs/${id}/retry`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listScanResultsPaginated: (
    page?: number,
    pageSize?: number,
    sortBy?: string,
    sortDir?: string,
    filters?: Record<string, any>
  ) =>
    apiFetch<{ items: ScanResult[]; total: number }>(
      buildPath("/api/scan-results", {
        page: page ?? 1,
        page_size: pageSize,
        sort_by: sortBy,
        sort_dir: sortDir,
        filters: filters ? JSON.stringify(filters) : undefined,
      })
    ),
};
