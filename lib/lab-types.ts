export type Mode = 'auto' | 'quick' | 'analysis' | 'app';
export type Run = {
  runtime_status?: string;
  workspace_id?: string;
  preview_artifact?: string;
  title?: string;
  gallery_hidden?: boolean;
  id: string;
  thread_id: string;
  mode: Mode;
  status: string;
  pod?: string;
  elapsed?: number;
  timings?: Record<string, number>;
  summary?: string;
  workspace_url?: string;
  preview_url?: string;
  artifacts?: { name: string; url: string }[];
};
export type Workspace = {
  source_path?: string;
  project_id?: string | null;
  project_name?: string | null;
  observed_at?: number;
  coder_status?: string;
  id: string;
  name: string;
  status: string;
  harness_status: string;
  url: string;
  ide_url: string;
};
export type SavedFile = {
  name: string;
  size: number;
  run_id: string;
  url: string;
  download_url: string;
};
export type ProjectSync = {
  mock: true;
  synced_at: number;
  file_count: number;
  bytes: number;
  excluded: number;
  destination: string;
};
export type ChatSummary = {
  id: string;
  title: string;
  project_id?: string | null;
  archived: boolean;
  updated?: number;
};
export type Project = {
  id: string;
  name: string;
  workspace_id: string | null;
  developer_workspace_id?: string | null;
  developer_name?: string | null;
  developer_status?: string | null;
  workspace_sync?: {
    direction: 'to_chat' | 'to_developer';
    at: number;
    path: string;
    file_count: number;
  } | null;
  status: string;
  created: number;
  updated: number;
  archived: boolean;
  deleting: boolean;
  deletion?: {
    status: 'deleting' | 'failed' | 'deleted';
    phase: string;
    error: string | null;
  };
  sync: ProjectSync | null;
  threads: ChatSummary[];
};

export type Preview = {
  title: string;
  endpoint: string;
  url?: string;
  error?: string;
  workspace?: Workspace;
  ide?: boolean;
};
