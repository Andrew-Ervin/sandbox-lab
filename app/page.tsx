'use client';
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  lazy,
  Suspense,
  type CSSProperties,
} from 'react';
import { ChatKit, useChatKit } from '@openai/chatkit-react';
import {
  Box,
  Monitor,
  X,
  Plus,
  ShieldCheck,
  Terminal,
  AppWindow,
  FolderOpen,
  LoaderCircle,
  Square,
  PanelRightOpen,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { OpenProjectWorkspaceButton } from '@/components/open-project-workspace';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarProvider,
  SidebarTrigger,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
} from '@/components/ui/sidebar';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import { LibraryActions, ArchiveNotice } from '@/components/library-actions';
import { ProjectSidebar, ChatRow } from '@/components/project-sidebar';
const ProjectsView = lazy(() =>
  import('@/components/projects-view').then((m) => ({
    default: m.ProjectsView,
  })),
);
const PackagePolicy = lazy(() =>
  import('@/components/package-policy').then((m) => ({
    default: m.PackagePolicy,
  })),
);
const AppsView = lazy(() =>
  import('@/components/resource-views').then((m) => ({ default: m.AppsView })),
);
const WorkspacesView = lazy(() =>
  import('@/components/resource-views').then((m) => ({
    default: m.WorkspacesView,
  })),
);
const FilesView = lazy(() =>
  import('@/components/resource-views').then((m) => ({ default: m.FilesView })),
);
function PanelLoading() {
  return (
    <div className="panel-loading" role="status">
      <LoaderCircle size={19} className="spin" />
      Loading…
    </div>
  );
}
import { HistoryResize } from '@/components/panel-resize';
import type {
  Run,
  Workspace,
  Preview,
  SavedFile,
  Project,
  ChatSummary,
} from '@/lib/lab-types';
import { usePolling } from '@/hooks/use-polling';
import { usePaneLayout } from '@/hooks/use-pane-layout';
import { PreviewPanel } from '@/components/preview-panel';

type Job = { id: string; thread_id: string; status: string; progress: string };

type Container = {
  namespace: string;
  name: string;
  state: string;
  ready: boolean;
  restarts: number;
  reason: string;
  pool_state?: string;
};
type Status = {
  project_reserve?: {
    state: string;
    target: number;
    idle_seconds: number;
    claims: number;
    error?: string;
  };
  containers?: {
    observed_at: number;
    pods: Container[];
    unavailable_namespaces: string[];
  };
  idle_policy?: {
    project_seconds: number;
    developer_seconds: number;
    error?: string;
  };
  kubernetes: boolean;
  openrouter: boolean;
  coder: boolean;
  warm_pods: number;
  model: string;
  reasoning: string;
  coding_engine: string;
  pool: {
    queued: number;
    executing: number;
    ready: number;
    target_reserve: number;
    max_concurrency: number;
    max_pods: number;
    idle_seconds: number;
    warm_hits: number;
    cold_misses: number;
    refill_seconds: number;
  };
  runs: Run[];
  apps?: Run[];
  jobs: Job[];
};
const modes = {
  auto: 'Auto',
  quick: 'Quick compute',
  analysis: 'Analysis',
  app: 'Build an app',
};
type Boot = { csrf: string; domain_key: string };

export default function Home() {
  const [boot, setBoot] = useState<Boot | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const script = document.createElement('script');
    script.src =
      'https://cdn.platform.openai.com/deployments/chatkit/chatkit.js';
    script.async = true;
    script.onerror = () =>
      setError(
        'ChatKit could not load. Check your internet connection and reload.',
      );
    document.head.appendChild(script);
    fetch('/api/bootstrap', { method: 'POST' })
      .then((r) => {
        if (!r.ok) throw Error('The local server is not ready.');
        return r.json() as Promise<Boot>;
      })
      .then(setBoot)
      .catch((e) => setError(e.message));
    return () => {
      script.remove();
    };
  }, []);
  return boot ? (
    <Lab boot={boot} loadError={error} />
  ) : (
    <div className="connecting">
      <Box size={30} />
      <h1>Sandbox Lab</h1>
      <p>{error || 'Connecting to your local lab…'}</p>
      {error && <Button onClick={() => location.reload()}>Reconnect</Button>}
    </div>
  );
}

function Lab({ boot, loadError }: { boot: Boot; loadError: string }) {
  const panes = usePaneLayout();
  const { openPreview: showPreviewPane } = panes;
  const [chatReady, setChatReady] = useState(false);
  const [threadLoading, setThreadLoading] = useState(false);
  const csrf = useRef(boot.csrf);
  const renewing = useRef<Promise<void> | null>(null);
  const sessionFetch = useCallback(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const send = () => {
        const headers = new Headers(init?.headers);
        headers.set('X-Lab-CSRF', csrf.current);
        return fetch(input, { ...init, headers });
      };
      let response = await send();
      if (response.status === 401) {
        renewing.current ??= fetch('/api/bootstrap', { method: 'POST' })
          .then(async (r) => {
            if (!r.ok) throw Error('Could not reconnect to the lab.');
            csrf.current = ((await r.json()) as Boot).csrf;
          })
          .finally(() => {
            renewing.current = null;
          });
        await renewing.current;
        response = await send();
      }
      return response;
    },
    [],
  );
  const [thread, setThread] = useState<string | null>(null);
  const [threads, setThreads] = useState<ChatSummary[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [inspect, setInspect] = useState(false);
  const [view, setView] = useState<
    'chat' | 'apps' | 'dev' | 'files' | 'policy' | 'projects'
  >('chat');
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const previewHiddenAt = useRef<number | null>(null);
  useEffect(() => {
    if (!panes.previewOpen) previewHiddenAt.current = Date.now();
  }, [panes.previewOpen]);
  const [historyWidth, setHistoryWidth] = useState(280);
  const [previewWidth, setPreviewWidth] = useState(55);
  const [previewFull, setPreviewFull] = useState(false);
  const [fitPreview, setFitPreview] = useState(true);
  const [widthsLoaded, setWidthsLoaded] = useState(false);
  const workArea = useRef<HTMLDivElement>(null);
  useEffect(() => {
    try {
      const saved = JSON.parse(
        localStorage.getItem('lab-panel-widths') || '{}',
      );
      if (Number.isFinite(saved.history))
        setHistoryWidth(Math.max(220, Math.min(420, saved.history)));
      if (Number.isFinite(saved.preview))
        setPreviewWidth(Math.max(30, Math.min(75, saved.preview)));
    } catch {}
    setWidthsLoaded(true);
  }, []);
  useEffect(() => {
    if (widthsLoaded)
      try {
        localStorage.setItem(
          'lab-panel-widths',
          JSON.stringify({ history: historyWidth, preview: previewWidth }),
        );
      } catch {}
  }, [historyWidth, previewWidth, widthsLoaded]);
  const previewRequest = useRef(0);
  const lastActivity = useRef(Date.now());
  const previewElement = useRef<HTMLIFrameElement>(null);
  const [statusStale, setStatusStale] = useState(false);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceName, setWorkspaceName] = useState('dev');
  const [starting, setStarting] = useState(false);
  const [files, setFiles] = useState<SavedFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const filesRequest = useRef(0);
  const [projectId, setProjectId] = useState<string | null>(null);
  const streaming = useRef(false);
  const threadRef = useRef(thread);
  threadRef.current = thread;
  const [error, setError] = useState('');
  const api = useCallback(
    async <T = unknown,>(url: string): Promise<T> => {
      const response = await sessionFetch(url);
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as {
          detail?: string;
        };
        throw Error(
          body.detail || `Lab server unavailable (${response.status})`,
        );
      }
      return response.json() as Promise<T>;
    },
    [sessionFetch],
  );
  const refreshing = useRef<Promise<Status | undefined> | null>(null);
  const refresh = useCallback(
    async (force = false) => {
      if (refreshing.current) {
        if (!force) return refreshing.current;
        await refreshing.current;
      }
      if (refreshing.current) return refreshing.current;
      refreshing.current = (async () => {
        const results = await Promise.allSettled([
          api<Status>('/api/status')
            .then((next) => {
              setStatus(next);
              setStatusStale(false);
              return next;
            })
            .catch((e) => {
              setStatusStale(true);
              throw e;
            }),
          api<ChatSummary[]>('/api/threads').then(setThreads),
          api<Project[]>('/api/projects').then(setProjects),
        ]);
        // An unavailable control plane must not prevent healthy chat/library updates.
        const failed = results.find((r) => r.status === 'rejected');
        if (failed?.status === 'rejected')
          setError(
            failed.reason instanceof Error
              ? failed.reason.message
              : 'Some lab status is unavailable.',
          );
        return results[0].status === 'fulfilled' ? results[0].value : undefined;
      })().finally(() => {
        refreshing.current = null;
      });
      return refreshing.current;
    },
    [api],
  );
  usePolling(
    async () => {
      if (!(await refresh())) throw Error('Status unavailable');
    },
    () =>
      status?.jobs.some((j) => ['running', 'queued'].includes(j.status))
        ? 3000
        : 5000,
    { hiddenInterval: 30000 },
  );
  const openPreview = useCallback(
    async (
      title: string,
      endpoint: string,
      workspace?: Workspace,
      ide = false,
    ) => {
      const request = ++previewRequest.current;
      showPreviewPane();
      lastActivity.current = Date.now();
      setPreview({ title, endpoint, workspace, ide });
      if (preview?.endpoint !== endpoint) {
        setPreviewFull(view !== 'chat' || Boolean(workspace));
        setFitPreview(true);
      }
      try {
        let data: { url: string };
        if (endpoint.startsWith('/api/app-preview/') || workspace) {
          const url = workspace
            ? `/api/developer/workspaces/${workspace.id}/resume`
            : endpoint.replace('/api/app-preview/', '/api/apps/') +
              '/start?resolve=1';
          const response = await sessionFetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ide, source_path: workspace?.source_path }),
          });
          const result = (await response.json()) as {
            detail?: string;
            url?: string;
          };
          if (!response.ok || !result.url)
            throw Error(
              result.detail || 'Could not start the app. Retry opening it.',
            );
          data = { url: result.url };
        } else data = await api<{ url: string }>(endpoint + '?resolve=1');
        if (request === previewRequest.current)
          setPreview((current) =>
            current?.endpoint === endpoint
              ? { ...current, url: data.url }
              : current,
          );
      } catch (e) {
        if (request === previewRequest.current)
          setPreview((current) =>
            current?.endpoint === endpoint
              ? { ...current, error: (e as Error).message }
              : current,
          );
      }
    },
    [api, sessionFetch, view, preview?.endpoint, showPreviewPane],
  );
  const reopenPreview = () => {
    if (!preview) return;
    // A briefly collapsed IDE stays mounted; expired previews resolve and wake again.
    if (
      previewHiddenAt.current &&
      Date.now() - previewHiddenAt.current > 60000
    ) {
      void openPreview(
        preview.title,
        preview.endpoint,
        preview.workspace,
        preview.ide,
      );
    } else {
      lastActivity.current = Date.now();
      showPreviewPane();
    }
  };
  const syncPreviewFit = useCallback(() => {
    previewElement.current?.contentWindow?.postMessage(
      { type: 'lab-preview-fit', enabled: fitPreview },
      '*',
    );
  }, [fitPreview]);
  useEffect(() => {
    syncPreviewFit();
  }, [syncPreviewFit, preview?.url]);
  useEffect(() => {
    if (!preview?.url || !panes.previewOpen) return;
    // Parent gestures and sandboxed app gestures count; background polling does not.
    const activity = () => {
      if (!document.hidden) lastActivity.current = Date.now();
    };
    const message = (event: MessageEvent) => {
      if (
        event.source === previewElement.current?.contentWindow &&
        event.data?.type === 'lab-preview-activity'
      )
        activity();
    };
    window.addEventListener('pointerdown', activity);
    window.addEventListener('keydown', activity);
    window.addEventListener('wheel', activity, { passive: true });
    window.addEventListener('message', message);
    const timer = setInterval(() => {
      if (document.hidden || Date.now() - lastActivity.current > 60000) return;
      if (preview.ide && preview.workspace)
        sessionFetch(
          `/api/developer/workspaces/${preview.workspace.id}/heartbeat`,
          { method: 'POST' },
        ).catch(() => {});
      else api(preview.endpoint + '?resolve=1').catch(() => {});
    }, 30000);
    return () => {
      clearInterval(timer);
      window.removeEventListener('pointerdown', activity);
      window.removeEventListener('keydown', activity);
      window.removeEventListener('wheel', activity);
      window.removeEventListener('message', message);
    };
  }, [
    preview?.url,
    preview?.endpoint,
    preview?.ide,
    preview?.workspace,
    panes.previewOpen,
    api,
    sessionFetch,
  ]);
  const loadFiles = useCallback(async () => {
    const request = ++filesRequest.current;
    if (!thread) {
      setFiles([]);
      setProjectId(null);
      setFilesLoading(false);
      return;
    }
    setFilesLoading(true);
    try {
      const data = await api<{ files: SavedFile[]; workspace_id: string }>(
        `/api/threads/${thread}/files`,
      );
      if (request === filesRequest.current) {
        setFiles(data.files);
        setProjectId(data.workspace_id);
      }
    } catch (e) {
      if (request === filesRequest.current) setError((e as Error).message);
      throw e;
    } finally {
      if (request === filesRequest.current) setFilesLoading(false);
    }
  }, [thread, api]);
  usePolling(
    loadFiles,
    () =>
      status?.jobs.some(
        (j) =>
          j.thread_id === thread && ['running', 'queued'].includes(j.status),
      )
        ? 5000
        : 30000,
    { enabled: view === 'files' },
  );
  usePolling(
    async () =>
      setWorkspaces(await api<Workspace[]>('/api/developer/workspaces')),
    5000,
    {
      enabled: view === 'dev',
      onError: (e) => {
        setWorkspaces((previous) =>
          previous.map((w) => ({ ...w, status: 'unknown' })),
        );
        setError((e as Error).message);
      },
    },
  );
  const startWorkspace = async (name: string) => {
    setStarting(true);
    setError('');
    try {
      const response = await sessionFetch('/api/developer/workspaces', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const result = (await response.json()) as { detail?: string };
      if (!response.ok) throw Error(result.detail);
      setWorkspaces(await api<Workspace[]>('/api/developer/workspaces'));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  };
  const chat = useChatKit({
    api: {
      url: '/api/chatkit',
      domainKey: boot.domain_key,
      fetch: async (input, init) => {
        const headers = new Headers(init?.headers);
        headers.set('X-Lab-CSRF', boot.csrf);
        headers.set('X-Lab-Mode', 'auto');
        return sessionFetch(input, { ...init, headers });
      },
    },
    widgets: {
      onAction: async (action) => {
        if (
          action.type === 'download_artifact' &&
          typeof action.payload?.run_id === 'string' &&
          typeof action.payload?.name === 'string'
        ) {
          const a = document.createElement('a');
          a.href = `/api/artifacts/${encodeURIComponent(action.payload.run_id)}/${encodeURIComponent(action.payload.name)}`;
          a.download = action.payload.name;
          document.body.appendChild(a);
          a.click();
          a.remove();
          return;
        }
        if (
          action.type === 'open_approval_payload' &&
          typeof action.payload?.thread_id === 'string' &&
          typeof action.payload?.item_id === 'string'
        ) {
          await openPreview(
            'Request details',
            `/api/approval-payload/${encodeURIComponent(action.payload.thread_id)}/${encodeURIComponent(action.payload.item_id)}`,
          );
          return;
        }
        if (action.type === 'approval_decide') {
          try {
            const r = await sessionFetch('/api/approvals/decision', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(action.payload),
            });
            if (!r.ok) {
              setError('This request is expired, already handled, or unavailable. No new approval was recorded.');
            } else {
              setError('');
              void refresh();
            }
            // The active response already delivers the authoritative card update.
            // Starting a second fetch while it streams can race that update.
            if (!streaming.current) await chat.fetchUpdates();
          } catch {
            setError('The approval service could not be reached. Your decision was not confirmed; check the card before retrying.');
          }
          return;
        }
        if (
          action.type === 'open_app' &&
          typeof action.payload?.run_id === 'string'
        ) {
          await openPreview(
            'App preview',
            `/api/app-preview/${encodeURIComponent(action.payload.run_id)}`,
          );
        }
        if (
          action.type === 'open_artifact' &&
          typeof action.payload?.run_id === 'string' &&
          typeof action.payload?.name === 'string'
        ) {
          await openPreview(
            action.payload.name,
            `/api/artifact-view/${encodeURIComponent(action.payload.run_id)}/${encodeURIComponent(action.payload.name)}`,
          );
        }
      },
    },
    theme: {
      colorScheme: 'dark',
      radius: 'round',
      typography: { baseSize: 16, fontFamily: 'Arial, sans-serif' },
      color: {
        surface: { background: '#212121', foreground: '#2f2f2f' },
        accent: { primary: '#b4e4cc', level: 2 },
      },
    },
    header: { enabled: false },
    history: { enabled: false },
    startScreen: {
      greeting: 'What do you want to work on?',
      prompts: [
        {
          label: 'Calculate & chart',
          prompt:
            'Use Python to simulate 1,000 dice rolls and make a chart of the results.',
        },
        {
          label: 'Explore a model',
          prompt:
            'Build a small machine learning example predicting material strength from synthetic composition data. Use cross-validation and save the model and evaluation.',
        },
        {
          label: 'Build something',
          prompt:
            'Build a simple interactive unit converter web app and start a preview server on port 3000.',
        },
      ],
    },
    composer: {
      placeholder: 'Message Sandbox Lab',
      attachments: { enabled: false },
    },
    disclaimer: {
      text: 'Local security lab · Check generated code and results.',
    },
    onReady: () => setChatReady(true),
    onThreadLoadStart: () => setThreadLoading(true),
    onThreadLoadEnd: () => setThreadLoading(false),
    onThreadChange: ({ threadId }) => {
      setThread(threadId);
      void refresh();
    },
    onResponseStart: () => {
      streaming.current = true;
      setError('');
    },
    onResponseEnd: () => {
      streaming.current = false;
      void refresh();
    },
    onError: ({ error }) => {
      setThreadLoading(false);
      setError(error.message);
    },
  });
  usePolling(
    async () => {
      if (!streaming.current) await chat.fetchUpdates();
    },
    4000,
    { enabled: Boolean(thread) && view === 'chat' },
  );
  const selectThread = (id: string | null) => {
    filesRequest.current++;
    setFiles([]);
    setProjectId(null);
    streaming.current = false;
    setView('chat');
    setPreview(null);
    setThread(id);
    void chat.setThreadId(id).catch((e: Error) => setError(e.message));
  };
  const openProject = (id: string | null) => {
    setSelectedProject(id);
    setView('projects');
    setPreview(null);
  };
  const threadProject = threads.find((t) => t.id === thread)?.project_id;
  const currentProject = projects.find((p) => p.id === threadProject);
  const active = (id: string | null) =>
    status?.jobs?.find(
      (j) => j.thread_id === id && ['running', 'queued'].includes(j.status),
    );
  const activeJob = active(thread);
  const orderedThreads = [...threads].sort(
    (a, b) => Number(b.id === thread) - Number(a.id === thread),
  );
  const appRuns = (status?.apps || status?.runs || []).filter(
    (r, i, all) =>
      r.preview_url &&
      !r.gallery_hidden &&
      all.findIndex(
        (other) =>
          other.preview_url && !other.gallery_hidden && other.pod === r.pod,
      ) === i,
  );
  const currentRuns = status?.runs.filter((r) => r.thread_id === thread) || [];
  const latest = currentRuns[0];
  useEffect(() => {
    const mc = (
      document as Document & {
        modelContext?: {
          registerTool: (
            tool: unknown,
            options: { signal: AbortSignal },
          ) => unknown;
        };
      }
    ).modelContext;
    if (!mc) return;
    const life = new AbortController();
    try {
      Promise.resolve(
        mc.registerTool(
          {
            name: 'read_lab_status',
            description:
              'Read the current local sandbox health and execution runs.',
            inputSchema: {
              type: 'object',
              properties: {},
              additionalProperties: false,
            },
            annotations: { readOnlyHint: true, untrustedContentHint: true },
            execute: async (input: unknown) => {
              if (
                input == null ||
                typeof input !== 'object' ||
                Array.isArray(input) ||
                Object.keys(input).length
              )
                throw Error('Expected an empty object');
              return api('/api/status');
            },
          },
          { signal: life.signal },
        ),
      ).catch(() => {});
    } catch {}
    return () => life.abort();
  }, [api]);
  const newProjectChat = async (id: string) => {
    try {
      const r = await sessionFetch(`/api/projects/${id}/threads`, {
        method: 'POST',
      });
      const data = (await r.json()) as { id: string; detail?: string };
      if (!r.ok) throw Error(data.detail || 'Could not create conversation');
      await refresh(true);
      selectThread(data.id);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <LibraryActions
      sessionFetch={sessionFetch}
      onError={setError}
      onChanged={async (change) => {
        if (
          (change.action === 'archive' || change.action === 'delete') &&
          ((change.kind === 'chat' && change.id === thread) ||
            (change.kind === 'project' && change.id === threadProject))
        )
          selectThread(null);
        if (
          change.kind === 'project' &&
          change.action === 'delete' &&
          selectedProject === change.id
        )
          setSelectedProject(null);
        await refresh(true);
      }}
    >
      <SidebarProvider
        open={panes.historyOpen}
        onOpenChange={panes.changeHistory}
        openMobile={panes.mobileHistoryOpen}
        onOpenMobileChange={panes.changeMobileHistory}
        style={{ '--sidebar-width': historyWidth + 'px' } as CSSProperties}
      >
        <Sidebar>
          <SidebarHeader className="p-4">
            <div className="brand">
              <Box size={24} />
              <span>Sandbox Lab</span>
              <SidebarTrigger aria-label="Collapse sidebar" title="Collapse sidebar" />
            </div>
            <Button
              variant="ghost"
              className="new-chat"
              onClick={() => selectThread(null)}
            >
              <Plus size={18} /> New chat
            </Button>
          </SidebarHeader>
          <SidebarContent className="px-3">
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={view === 'apps'}
                  onClick={() => {
                    setView('apps');
                    setPreview(null);
                  }}
                >
                  <AppWindow size={17} />
                  <span>Apps</span>
                  <span className="nav-count">{appRuns.length}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={view === 'dev'}
                  onClick={() => {
                    setView('dev');
                    setPreview(null);
                  }}
                >
                  <Monitor size={17} />
                  <span>Developer workspaces</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={view === 'files'}
                  onClick={() => {
                    setView('files');
                    setPreview(null);
                  }}
                >
                  <FolderOpen size={17} />
                  <span>Conversation files</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={view === 'policy'}
                  onClick={() => {
                    setView('policy');
                    setPreview(null);
                  }}
                >
                  <ShieldCheck size={17} />
                  <span>Network & packages</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
            <ProjectSidebar
              projects={projects}
              currentThread={thread}
              isChat={view === 'chat'}
              selectedProject={view === 'projects' ? selectedProject : null}
              onOpen={openProject}
              onSelect={selectThread}
              onNewChat={(id) => void newProjectChat(id)}
              running={(id) => Boolean(active(id))}
            />
            <p className="section-label">Your chats</p>
            <div className="history-list">
              {orderedThreads
                .filter((t) => !t.project_id && !t.archived)
                .map((t) => (
                  <ChatRow
                    key={t.id}
                    chat={t}
                    selected={t.id === thread && view === 'chat'}
                    running={Boolean(active(t.id))}
                    onSelect={() => selectThread(t.id)}
                  />
                ))}
            </div>
            {!threads.length && (
              <p className="empty-history">
                Your conversations will appear here.
              </p>
            )}
          </SidebarContent>
          <SidebarFooter className="p-4">
            <Button
              variant="ghost"
              className="justify-start"
              onClick={() => setInspect(true)}
            >
              <ShieldCheck size={18} /> Lab status{' '}
              <span
                className={`status-dot ${status?.kubernetes ? 'online' : ''}`}
              />
            </Button>
            <div className="profile">
              <span className="avatar">L</span>
              <div>
                Local workspace<small>OpenRouter · Kubernetes</small>
              </div>
            </div>
          </SidebarFooter>
          <HistoryResize
            value={historyWidth}
            onChange={setHistoryWidth}
            onReset={() => setHistoryWidth(280)}
            min={220}
            max={420}
          />
        </Sidebar>
        <main className="lab-main">
          <header className="topbar">
            <div className="topbar-left">
              <SidebarTrigger className={panes.historyOpen ? 'md:hidden' : ''} aria-label="Open sidebar" title="Open sidebar" />
              {view === 'chat' && currentProject && (
                <Button variant="ghost" size="sm" className="project-header-link" title="Open project files" onClick={() => openProject(currentProject.id)}>
                  <FolderOpen size={15} /><span>{currentProject.name}</span>
                </Button>
              )}
            </div>
            <div className="topbar-actions">
              {view === 'chat' && currentProject && !(panes.previewOpen && preview?.ide) && (
                <OpenProjectWorkspaceButton project={currentProject} sessionFetch={sessionFetch} onRefresh={() => refresh(true)}
                  onOpen={(ws) => openPreview(currentProject.name, `/api/developer/workspaces/${ws.id}/open`, ws, true)} />
              )}
              {preview && !panes.previewOpen && (
                <Button variant="ghost" size="icon-sm" onClick={reopenPreview} aria-label="Reopen preview" title={`Reopen ${preview.title}`}>
                  <PanelRightOpen size={17} />
                </Button>
              )}
            </div>
          </header>
          {(error || loadError) && (
            <div role="alert" className="error-banner">
              {error || loadError}
              <button aria-label="Dismiss error" onClick={() => setError('')}>
                <X size={16} />
              </button>
            </div>
          )}
          <div
            className={`work-area ${preview ? 'has-preview' : ''}`}
            ref={workArea}
          >
            {view === 'projects' && (
              <Suspense fallback={<PanelLoading />}>
                <ProjectsView
                  chats={threads}
                  projects={projects}
                  selected={selectedProject}
                  onSelect={openProject}
                  onChat={selectThread}
                  sessionFetch={sessionFetch}
                  onRefresh={() => refresh(true)}
                  onOpenDeveloper={(ws) =>
                    openPreview(
                      ws.project_name || ws.name,
                      `/api/developer/workspaces/${ws.id}/open`,
                      ws,
                      true,
                    )
                  }
                />
              </Suspense>
            )}
            {view === 'policy' && (
              <Suspense fallback={<PanelLoading />}>
                <PackagePolicy sessionFetch={sessionFetch} />
              </Suspense>
            )}
            <div
              className="conversation"
              style={{ display: view === 'chat' ? 'flex' : 'none' }}
            >
              <ArchiveNotice
                chat={threads.find((t) => t.id === thread)}
                project={projects.find((p) => p.id === threadProject)}
              />
              <div
                className="chat-stage"
                aria-busy={!chatReady || threadLoading}
              >
                {(!chatReady || threadLoading) && (
                  <div className="chat-loading" role="status">
                    <span className="skeleton-line wide" />
                    <span className="skeleton-line" />
                    <span className="skeleton-card" />
                    <p>
                      <LoaderCircle size={14} className="spin" />
                      {threadLoading
                        ? 'Loading conversation…'
                        : 'Preparing chat…'}
                    </p>
                  </div>
                )}
                <ChatKit
                  control={chat.control}
                  className="chat-surface"
                  style={{
                    visibility:
                      !chatReady || threadLoading ? 'hidden' : 'visible',
                  }}
                />
              </div>
              {activeJob && (
                <div className="run-strip">
                  <button onClick={() => setInspect(true)}>
                    {activeJob ? (
                      <LoaderCircle size={16} className="spin" />
                    ) : (
                      <Terminal size={16} />
                    )}
                    <span>
                      {activeJob?.progress ||
                        `Last run: ${modes[latest.mode]} · ${latest.status}${latest.elapsed != null ? ` · ${latest.elapsed.toFixed(1)}s` : ''}`}
                    </span>
                  </button>
                  {activeJob && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={async () => {
                        await sessionFetch(`/api/threads/${thread}/stop`, {
                          method: 'POST',
                        });
                        streaming.current = false;
                        void refresh();
                        void chat
                          .fetchUpdates()
                          .catch((e: Error) => setError(e.message));
                      }}
                    >
                      <Square size={12} /> Stop run
                    </Button>
                  )}

                </div>
              )}
            </div>
            {view === 'apps' && (
              <Suspense fallback={<PanelLoading />}>
                <AppsView
                  runs={appRuns}
                  stale={statusStale}
                  onOpen={(run) =>
                    openPreview(run.title || 'App preview', run.preview_url!)
                  }
                  onConversation={selectThread}
                />
              </Suspense>
            )}
            {view === 'dev' && (
              <Suspense fallback={<PanelLoading />}>
                <WorkspacesView
                  projects={projects}
                  sessionFetch={sessionFetch}
                  onProject={openProject}
                  onLinked={async () => {
                    await refresh(true);
                    setWorkspaces(
                      await api<Workspace[]>('/api/developer/workspaces'),
                    );
                  }}
                  workspaces={workspaces}
                  stale={statusStale}
                  name={workspaceName}
                  setName={setWorkspaceName}
                  starting={starting}
                  onStart={() => startWorkspace(workspaceName)}
                  onOpen={(ws) =>
                    openPreview(
                      ws.project_name || ws.name,
                      `/api/developer/workspaces/${ws.id}/open`,
                      ws,
                      true,
                    )
                  }
                  onDelete={async (ws) => {
                    const r = await sessionFetch(
                      `/api/developer/workspaces/${ws.id}`,
                      { method: 'DELETE' },
                    );
                    if (!r.ok) {
                      const body = (await r.json().catch(() => ({}))) as {
                        detail?: string;
                      };
                      throw Error(body.detail || 'Could not delete workspace');
                    }
                    if (preview?.workspace?.id === ws.id) setPreview(null);
                    setWorkspaces((previous) =>
                      previous.map((w) =>
                        w.id === ws.id ? { ...w, status: 'deleting' } : w,
                      ),
                    );
                  }}
                  onRefresh={async (ws) => {
                    try {
                      const r = await sessionFetch(
                        `/api/developer/workspaces/${ws.id}/harness`,
                        { method: 'POST' },
                      );
                      if (!r.ok)
                        throw Error(
                          'Could not refresh Pi. Retry after the workspace is ready.',
                        );
                      setWorkspaces(
                        await api<Workspace[]>('/api/developer/workspaces'),
                      );
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                />
              </Suspense>
            )}
            {view === 'files' && (
              <Suspense fallback={<PanelLoading />}>
                <FilesView
                  title={threads.find((t) => t.id === thread)?.title}
                  files={files}
                  projectId={projectId}
                  loading={filesLoading}
                  onOpen={(file) => openPreview(file.name, file.url)}
                />
              </Suspense>
            )}
            {preview && (
              <PreviewPanel
                preview={preview}
                visible={panes.previewOpen}
                previewFull={previewFull}
                previewWidth={previewWidth}
                fitPreview={fitPreview}
                setPreviewFull={setPreviewFull}
                setPreviewWidth={setPreviewWidth}
                setFitPreview={setFitPreview}
                workArea={workArea}
                previewElement={previewElement}
                syncPreviewFit={syncPreviewFit}
                collapsePreview={panes.collapsePreview}
                openPreview={openPreview}
              />
            )}
          </div>
        </main>
        <Sheet open={inspect} onOpenChange={setInspect}>
          <SheetContent className="lab-sheet">
            <SheetHeader>
              <SheetTitle>Lab status</SheetTitle>
              <SheetDescription>
                Execution, isolation, and workspace handoffs.
              </SheetDescription>
            </SheetHeader>
            <div className="inspect-body">
              {(
                [
                  ['Kubernetes', status?.kubernetes],
                  ['OpenRouter configured', status?.openrouter],
                  ['Coder', status?.coder],
                ] as const
              ).map(([name, ready]) => (
                <div className="health-row" key={name}>
                  <span>{name}</span>
                  <span className={ready ? 'healthy' : 'pending'}>
                    {ready ? '● Ready' : '○ Unavailable'}
                  </span>
                </div>
              ))}
              <p className="detail-note">
                {status?.warm_pods || 0} quick pods ready · {status?.model} ·{' '}
                {status?.reasoning}
              </p>
              {status?.pool && (
                <div className="pool-state">
                  <strong>
                    {status.pool.ready
                      ? `${status.pool.ready} quick pods ready`
                      : status.pool.executing || status.pool.queued
                        ? 'Scaling for demand'
                        : 'Quick compute asleep'}
                  </strong>
                  <p>
                    {status.pool.executing} executing · {status.pool.queued}{' '}
                    queued · warm target {status.pool.target_reserve}
                  </p>
                  <p>
                    Up to {status.pool.max_concurrency} local executions · idle
                    to zero after {status.pool.idle_seconds}s
                  </p>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={async () => {
                      await sessionFetch('/api/compute/warm', {
                        method: 'POST',
                      });
                      void refresh();
                    }}
                  >
                    Warm quick compute
                  </Button>
                </div>
              )}
              <div className="mode-explanation">
                <h3>Conversations keep running</h3>
                <p>
                  Switch chats or open an app while the server works. Use Stop
                  run to cancel. Server restarts interrupt active jobs and
                  retain saved results.
                </p>
                <h3>Quick Python</h3>
                <p>
                  Clean single-use pods, conversation-owned files, no network. A
                  missing package requires an explicit delegate_project tool
                  call from the AI.
                </p>
                <h3>Project environments</h3>
                <p>
                  Only delegated conversations have a project with separate
                  packages, caches, and files. uv, npm, NuGet, Julia Pkg, Go
                  modules, Cargo, and CMake cover the language toolchains.
                </p>
                <h3>Developer workspaces</h3>
                <p>
                  Separate Coder workspaces with VS Code and Pi through Ori as
                  the default agent. Independent of chat.
                </p>
              </div>
              {status?.project_reserve && (
                <div className="pool-state">
                  <strong>
                    Unassigned project reserve · {status.project_reserve.state}
                  </strong>
                  <p>
                    Target {status.project_reserve.target} · claims{' '}
                    {status.project_reserve.claims} · idle to zero after{' '}
                    {status.project_reserve.idle_seconds}s
                  </p>
                  <p>
                    No conversation files or model allowance until the AI hands
                    off a project. Used homes never return to the reserve.
                  </p>
                  {status.project_reserve.error && (
                    <p>{status.project_reserve.error}</p>
                  )}
                </div>
              )}
              <h3 className="runs-heading">Live containers</h3>
              <p className="detail-note">
                {statusStale
                  ? 'Status unavailable — last successful snapshot below'
                  : 'Updated ' +
                    (status?.containers
                      ? new Date(
                          status.containers.observed_at * 1000,
                        ).toLocaleTimeString()
                      : '…')}{' '}
                · polls every 5 seconds
              </p>
              {status?.containers?.unavailable_namespaces.length ? (
                <p role="alert">
                  Unable to observe:{' '}
                  {status.containers.unavailable_namespaces.join(', ')}
                </p>
              ) : null}
              {status?.idle_policy?.error && (
                <p role="alert">{status.idle_policy.error}</p>
              )}
              {status?.containers?.pods.map((p) => (
                <article className="run-card" key={p.namespace + '/' + p.name}>
                  <div>
                    <strong>{p.namespace}</strong>
                    <span>{statusStale ? 'unknown' : p.state}</span>
                  </div>
                  <code>{p.name}</code>
                  <p>
                    {p.pool_state ? 'Quick pool: ' + p.pool_state + ' · ' : ''}
                    {p.ready ? 'Ready' : 'Not ready'} · {p.restarts} restarts
                    {p.reason ? ' · ' + p.reason : ''}
                  </p>
                </article>
              ))}
              <h3 className="runs-heading">This conversation</h3>
              {!currentRuns.length && (
                <p className="detail-note">
                  Execution details appear when code runs.
                </p>
              )}
              {currentRuns.map((run) => (
                <article className="run-card" key={run.id}>
                  <div>
                    <strong>{modes[run.mode]}</strong>
                    <span>{run.status}</span>
                  </div>
                  <code>{run.pod || 'Waiting for compute'}</code>
                  {run.summary && <p>{run.summary}</p>}
                  {run.timings && (
                    <dl className="timing-grid">
                      {(
                        [
                          ['queue_seconds', 'Queue'],
                          ['acquire_seconds', 'Acquire pod'],
                          ['workspace_seconds', 'Workspace ready'],
                          ['agent_seconds', 'Agent & collect'],
                          ['execute_seconds', 'Run & collect'],
                          ['cleanup_seconds', 'Cleanup'],
                        ] as const
                      ).map(
                        ([key, label]) =>
                          run.timings?.[key] != null && (
                            <div key={key}>
                              <dt>{label}</dt>
                              <dd>{run.timings[key].toFixed(2)}s</dd>
                            </div>
                          ),
                      )}
                    </dl>
                  )}
                  {run.preview_url && (
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setInspect(false);
                        void openPreview('App preview', run.preview_url!);
                      }}
                    >
                      Open preview
                    </Button>
                  )}
                  {run.artifacts?.map((a) => (
                    <button
                      className="artifact-button"
                      key={a.url}
                      onClick={() => {
                        setInspect(false);
                        void openPreview(a.name, a.url);
                      }}
                    >
                      {a.name} ↗
                    </button>
                  ))}
                </article>
              ))}
            </div>
          </SheetContent>
        </Sheet>
      </SidebarProvider>
    </LibraryActions>
  );
}
