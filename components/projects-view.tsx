'use client';
import { memo, useEffect, useRef, useState } from 'react';
import {
  Folder,
  FolderOpen,
  FileCode2,
  ArrowLeft,
  ChevronRight,
  CloudUpload,
  MessageSquare,
  Plus,
  RefreshCw,
  LoaderCircle,
  Download,
  Files,
} from 'lucide-react';
import {
  ProjectMenu,
  ChatActions,
  useLibraryActions,
} from '@/components/library-actions';
import { Button } from '@/components/ui/button';
import { StatePill } from '@/components/state-pill';
import {
  WorkspaceSync,
  OpenProjectWorkspace,
} from '@/components/workspace-sync';
import type {
  Project,
  ProjectSync,
  ChatSummary,
  Workspace,
} from '@/lib/lab-types';

type Entry = { name: string; path: string; directory: boolean; size: number };
type Listing = {
  path: string;
  entries: Entry[];
  excluded: number;
  limit: number;
  truncated?: boolean;
};
type OpenFile = { path: string; data: string; size: number };
const size = (n: number) =>
  n >= 1e6
    ? (n / 1e6).toFixed(1) + ' MB'
    : n >= 1000
      ? (n / 1000).toFixed(1) + ' KB'
      : n + ' B';
export function ProjectsView({
  chats,
  projects,
  selected,
  onSelect,
  onChat,
  sessionFetch,
  onRefresh,
  onOpenDeveloper,
}: {
  onOpenDeveloper: (ws: Workspace) => void;
  chats: ChatSummary[];
  projects: Project[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  onChat: (id: string) => void;
  sessionFetch: (
    input: RequestInfo | URL,
    init?: RequestInit,
  ) => Promise<Response>;
  onRefresh: () => unknown;
}) {
  const actions = useLibraryActions();
  const [filter, setFilter] = useState<'active' | 'archived' | 'chats'>(
    'active',
  );
  const visibleProjects = projects.filter((p) =>
    filter === 'archived' ? p.archived : !p.archived,
  );
  const archivedChats = chats.filter((t) => t.archived);
  const project = projects.find((p) => p.id === selected);
  const [listing, setListing] = useState<Listing | null>(null);
  const [file, setFile] = useState<OpenFile | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [synced, setSynced] = useState<ProjectSync | null>(null);
  const generation = useRef(0);
  const selection = useRef(selected);
  selection.current = selected;
  async function request<T>(endpoint: string, method = 'GET'): Promise<T> {
    const r = await sessionFetch(endpoint, { method });
    const value = (await r.json()) as T & { detail?: string };
    if (!r.ok) throw Error(value.detail || 'Project request failed');
    return value;
  }
  async function browse(path = '', wake = false) {
    if (!selected) return;
    const id = ++generation.current;
    setLoading(true);
    setError('');
    setFile(null);
    try {
      const data = await request<Listing>(
        `/api/projects/${selected}/${wake ? 'open' : 'files?path=' + encodeURIComponent(path)}`,
        wake ? 'POST' : 'GET',
      );
      if (id === generation.current) setListing(data);
    } catch (e) {
      if (id === generation.current) setError((e as Error).message);
    } finally {
      if (id === generation.current) setLoading(false);
    }
  }
  useEffect(() => {
    generation.current++;
    setListing(null);
    setFile(null);
    setSynced(null);
    setSyncing(false);
    setError('');
    if (
      selected &&
      project?.workspace_id &&
      !project.archived &&
      !project.deleting
    )
      void browse('', true);
    return () => {
      generation.current++;
    };
  }, [selected, project?.archived, project?.deleting, project?.workspace_id]);
  async function openFile(entry: Entry) {
    const id = ++generation.current;
    setLoading(true);
    setError('');
    try {
      const result = await request<OpenFile>(
        `/api/projects/${selected}/file?path=${encodeURIComponent(entry.path)}`,
      );
      if (id === generation.current) setFile(result);
    } catch (e) {
      if (id === generation.current) setError((e as Error).message);
    } finally {
      if (id === generation.current) setLoading(false);
    }
  }
  async function newChat(pid = selected) {
    if (!pid) return;
    setCreating(true);
    try {
      const result = await request<{ id: string }>(
        `/api/projects/${pid}/threads`,
        'POST',
      );
      await onRefresh();
      onChat(result.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCreating(false);
    }
  }
  async function sync() {
    if (!selected) return;
    const pid = selected;
    setSyncing(true);
    setError('');
    try {
      const result = await request<ProjectSync>(
        `/api/projects/${pid}/sync-onedrive`,
        'POST',
      );
      if (selection.current === pid) setSynced(result);
      onRefresh();
    } catch (e) {
      if (selection.current === pid) setError((e as Error).message);
    } finally {
      if (selection.current === pid) setSyncing(false);
    }
  }
  const lastSync = synced || project?.sync;
  return (
    <section className="workspace-page collection-page projects-page">
      {!project ? (
        <>
          <header className="collection-heading">
            <div>
              <p className="eyebrow">SHARED WORK, SEPARATE CONVERSATIONS</p>
              <h1>Projects</h1>
              <p className="collection-description">
                A home for chats that build something. Files and packages belong
                to the project.
              </p>
            </div>
            <span className="collection-count">
              {projects.filter((p) => !p.archived).length} projects
            </span>
          </header>
          <div className="library-filters" aria-label="Project library filters">
            <button
              aria-pressed={filter === 'active'}
              onClick={() => setFilter('active')}
            >
              Recent projects
            </button>
            <button
              aria-pressed={filter === 'archived'}
              onClick={() => setFilter('archived')}
            >
              Archived projects{' '}
              <span>{projects.filter((p) => p.archived).length}</span>
            </button>
            <button
              aria-pressed={filter === 'chats'}
              onClick={() => setFilter('chats')}
            >
              Archived chats <span>{archivedChats.length}</span>
            </button>
          </div>
          {error && (
            <div role="alert" className="project-error">
              {error}
            </div>
          )}
          {filter === 'chats' ? (
            <div className="project-conversations">
              {archivedChats.map((t) => (
                <div key={t.id} className="project-conversation-row">
                  <button onClick={() => onChat(t.id)}>
                    <MessageSquare size={17} />
                    <span>
                      {t.title}
                      <small>
                        {projects.find((p) => p.id === t.project_id)?.name ||
                          'No project'}
                      </small>
                    </span>
                  </button>
                  <ChatActions chat={t} />
                </div>
              ))}
              {!archivedChats.length && (
                <div className="collection-empty">
                  <MessageSquare />
                  <h2>No archived chats</h2>
                  <p>Chats you archive will appear here, ready to restore.</p>
                </div>
              )}
            </div>
          ) : (
            <>
              <div className="project-grid">
                {visibleProjects.map((p) => (
                  <article key={p.id} className="project-card">
                    <div className="project-card-top">
                      <FolderOpen size={25} />
                      <StatePill state={p.archived ? 'archived' : p.status} />
                      <ProjectMenu
                        project={p}
                        onOpen={() => onSelect(p.id)}
                        onNewChat={() => void newChat(p.id)}
                      />
                    </div>
                    <button
                      className="project-card-open"
                      onClick={() => onSelect(p.id)}
                    >
                      <h2>{p.name}</h2>
                      <p>
                        {p.threads.length} conversation
                        {p.threads.length === 1 ? '' : 's'} ·{' '}
                        {p.workspace_id
                          ? 'Chat sandbox'
                          : p.developer_workspace_id
                            ? 'Developer workspace linked'
                            : 'No compute allocated'}
                      </p>
                      <footer>
                        <span>
                          {p.deleting
                            ? p.deletion?.phase || 'Deletion in progress'
                            : p.archived
                              ? 'Files and conversations retained'
                              : p.sync
                                ? 'Mock copy saved'
                                : p.workspace_id
                                  ? 'Workspace files retained'
                                  : 'Chat compute starts only when needed'}
                        </span>
                        <ChevronRight size={17} />
                      </footer>
                    </button>
                  </article>
                ))}
              </div>
              {!visibleProjects.length && (
                <div className="collection-empty">
                  <FolderOpen />
                  <h2>
                    {filter === 'archived'
                      ? 'No archived projects'
                      : 'Start with a conversation'}
                  </h2>
                  <p>
                    {filter === 'archived'
                      ? 'Archived projects stay here until you restore or delete them.'
                      : 'A project is created automatically when the AI delegates to a larger coding workspace.'}
                  </p>
                </div>
              )}
            </>
          )}
        </>
      ) : (
        <>
          <button className="project-back" onClick={() => onSelect(null)}>
            <ArrowLeft size={15} /> All projects
          </button>
          <header className="collection-heading">
            <div>
              <p className="eyebrow">PROJECT WORKSPACE</p>
              <h1>{project.name}</h1>
              <p className="collection-description">
                One set of files and packages, shared by every conversation
                here.
              </p>
            </div>
            <div className="project-detail-actions">
              <StatePill
                state={project.archived ? 'archived' : project.status}
              />
              <ProjectMenu
                project={project}
                onOpen={() => onSelect(project.id)}
                onNewChat={() => void newChat()}
              />
            </div>
          </header>
          {project.archived || project.deleting ? (
            <div className="project-archive-note">
              <FolderOpen size={22} />
              <div>
                <strong>
                  {project.deleting
                    ? project.deletion?.phase ||
                      'Workspace deletion is in progress'
                    : 'This project is archived'}
                </strong>
                <p>
                  {project.deleting
                    ? project.deletion?.error ||
                      'Deletion continues in the background. You can leave this page.'
                    : 'Your files and conversations are retained. Restore the project to continue working.'}
                </p>
              </div>
              {!project.deleting && (
                <Button
                  variant="secondary"
                  onClick={() =>
                    actions.archive({
                      kind: 'project',
                      id: project.id,
                      name: project.name,
                      archived: true,
                    })
                  }
                >
                  Restore project
                </Button>
              )}
            </div>
          ) : (
            <>
              {!project.developer_workspace_id && (
                <OpenProjectWorkspace
                  project={project}
                  sessionFetch={sessionFetch}
                  onRefresh={onRefresh}
                  onOpen={onOpenDeveloper}
                />
              )}
              {project.developer_workspace_id && (
                <WorkspaceSync
                  key={project.id}
                  project={project}
                  sessionFetch={sessionFetch}
                  onRefresh={onRefresh}
                  onOpenDeveloper={onOpenDeveloper}
                />
              )}
              <div className="project-toolbar">
                <Button onClick={() => void newChat()} disabled={creating}>
                  <Plus size={16} /> New chat in project
                </Button>
                <Button
                  variant="secondary"
                  onClick={sync}
                  disabled={syncing || loading || !project.workspace_id}
                >
                  {syncing ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <CloudUpload size={17} />
                  )}{' '}
                  {syncing ? 'Saving mock copy…' : 'Mock sync to OneDrive'}
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => browse('', true)}
                  disabled={loading || !project.workspace_id}
                >
                  <RefreshCw size={16} /> Open workspace files
                </Button>
              </div>
              <div className="project-sync-note">
                <CloudUpload size={17} />
                <div>
                  <strong>Local simulation · no Microsoft connection</strong>
                  <span>
                    {lastSync
                      ? `${lastSync.file_count} files · ${size(lastSync.bytes)} · ${new Date(lastSync.synced_at * 1000).toLocaleString()} · ${lastSync.excluded} entries excluded`
                      : 'Save a local copy to OneDrive (mock)/Projects/' +
                        project.id +
                        '.'}
                  </span>
                </div>
              </div>
              {error && (
                <div role="alert" className="project-error">
                  {error}
                </div>
              )}
              {project.workspace_id ? (
                <div className="project-browser">
                  <div className="project-tree">
                    <header>
                      <Files size={16} />
                      <strong>Workspace files</strong>
                      {loading && <LoaderCircle size={15} className="spin" />}
                    </header>
                    <div className="project-breadcrumbs">
                      <button onClick={() => browse('')}>Project</button>
                      {listing?.path
                        .split('/')
                        .filter(Boolean)
                        .map((part, i, all) => (
                          <span key={i}>
                            <ChevronRight size={12} />
                            <button
                              onClick={() =>
                                browse(all.slice(0, i + 1).join('/'))
                              }
                            >
                              {part}
                            </button>
                          </span>
                        ))}
                    </div>
                    <div className="project-entries">
                      {listing?.entries
                        .slice()
                        .sort(
                          (a, b) =>
                            Number(b.directory) - Number(a.directory) ||
                            a.name.localeCompare(b.name),
                        )
                        .map((e) => (
                          <button
                            key={e.path}
                            className={file?.path === e.path ? 'selected' : ''}
                            onClick={() =>
                              e.directory ? browse(e.path) : openFile(e)
                            }
                          >
                            {e.directory ? (
                              <Folder size={16} />
                            ) : (
                              <FileCode2 size={16} />
                            )}
                            <span>{e.name}</span>
                            {!e.directory && <small>{size(e.size)}</small>}
                          </button>
                        ))}
                      {!listing && loading ? (
                        <p className="project-placeholder">
                          Waking workspace and loading files…
                        </p>
                      ) : listing && !listing.entries.length ? (
                        <p className="project-placeholder">
                          This folder is empty.
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <div className="project-file-preview">
                    {file ? (
                      <FilePreview file={file} />
                    ) : (
                      <div className="project-placeholder">
                        <FileCode2 size={30} />
                        <h3>Your project, in view</h3>
                        <p>
                          Select a file to preview its contents. HTML is shown
                          as source; use Apps for interactive previews.
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="project-archive-note">
                  <FolderOpen size={23} />
                  <div>
                    <strong>Your chat sandbox starts when needed</strong>
                    <p>
                      Open a project conversation and ask for coding work.
                      Linking a developer workstation does not allocate another
                      environment.
                    </p>
                  </div>
                </div>
              )}
              {listing?.truncated && (
                <p role="status" className="project-error">
                  This folder exceeds the browser limit; only part of it is
                  shown. Narrow the folder contents to see the remaining
                  entries.
                </p>
              )}
              <p className="collection-footnote">
                File access wakes sleeping compute. Dependencies, hidden
                credential files and symlinks are excluded. Mock sync also
                excludes build output; limits are 2,000 files, 8 MB per file and
                32 MB total.
              </p>
            </>
          )}
          <h2 className="project-conversations-title">
            Conversations in this project
          </h2>
          <div className="project-conversations">
            {project.threads.map((t) => (
              <div key={t.id} className="project-conversation-row">
                <button onClick={() => onChat(t.id)}>
                  <MessageSquare size={17} />
                  <span>
                    {t.title}
                    {t.archived && <small>Archived</small>}
                  </span>
                  <ChevronRight size={16} />
                </button>
                <ChatActions chat={t} />
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
const FilePreview = memo(function FilePreview({ file }: { file: OpenFile }) {
  let text: string | null = null;
  let bytes: Uint8Array;
  try {
    bytes = Uint8Array.from(atob(file.data), (c) => c.charCodeAt(0));
  } catch {
    bytes = new Uint8Array();
  }
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    if (text.includes('\0')) text = null;
  } catch {
    text = null;
  }
  const imageType = /\.(png|jpg|jpeg|gif|webp)$/i
    .exec(file.path)?.[1]
    ?.toLowerCase();
  function download() {
    const url = URL.createObjectURL(
      new Blob([bytes as BlobPart], { type: 'application/octet-stream' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = file.path.split('/').pop() || 'file';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <>
      <header>
        <strong>{file.path}</strong>
        <Button variant="ghost" size="sm" onClick={download}>
          <Download size={15} /> Download
        </Button>
      </header>
      {imageType ? (
        <img
          className="project-image"
          src={`data:image/${imageType === 'jpg' ? 'jpeg' : imageType};base64,${file.data}`}
          alt={file.path}
        />
      ) : text !== null ? (
        <>
          <pre>{text.slice(0, 200000)}</pre>
          {text.length > 200000 && (
            <p className="project-placeholder">
              Preview shortened. Download to read the full file.
            </p>
          )}
        </>
      ) : (
        <p className="project-placeholder">
          Binary file · {size(file.size)}. Download to open it.
        </p>
      )}
    </>
  );
});
