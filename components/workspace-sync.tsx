'use client';
import { useRef, useState } from 'react';
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  ArrowRight,
  FolderOpen,
  LoaderCircle,
  Monitor,
  Terminal,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { StatePill } from '@/components/state-pill';
import type { Project, Workspace } from '@/lib/lab-types';

type Fetch = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;
type Plan = {
  id: string;
  direction: 'to_chat' | 'to_developer';
  path: string;
  bytes: number;
  excluded: number;
  files: {
    path: string;
    bytes: number;
    change: 'new' | 'different' | 'unchanged';
  }[];
};
const bytes = (n: number) =>
  n >= 1e6 ? (n / 1e6).toFixed(1) + ' MB' : (n / 1000).toFixed(1) + ' KB';

export function WorkspaceSync({
  project,
  sessionFetch,
  onRefresh,
  onOpenDeveloper,
}: {
  project: Project;
  sessionFetch: Fetch;
  onRefresh: () => unknown;
  onOpenDeveloper: (ws: Workspace) => void;
}) {
  const [opened, setOpened] = useState(false),
    [busy, setBusy] = useState(false),
    [plan, setPlan] = useState<Plan | null>(null),
    [error, setError] = useState(''),
    [success, setSuccess] = useState('');
  const generation = useRef(0);
  async function request<T>(path: string, body: unknown): Promise<T> {
    const r = await sessionFetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = (await r.json()) as T & { detail?: string };
    if (!r.ok) throw Error(data.detail || 'Workspace request failed');
    return data;
  }
  function close() {
    generation.current++;
    setOpened(false);
    setPlan(null);
    setError('');
    if (plan)
      void sessionFetch(
        `/api/projects/${project.id}/workspace-sync/${plan.id}`,
        { method: 'DELETE' },
      );
  }
  async function review(direction: Plan['direction']) {
    const requestId = ++generation.current;
    setOpened(true);
    setBusy(true);
    setError('');
    setPlan(null);
    setSuccess('');
    try {
      const next = await request<Plan>(
        `/api/projects/${project.id}/workspace-sync/plan`,
        { direction },
      );
      if (requestId === generation.current) setPlan(next);
      else
        void sessionFetch(
          `/api/projects/${project.id}/workspace-sync/${next.id}`,
          { method: 'DELETE' },
        );
    } catch (e) {
      if (requestId === generation.current) setError((e as Error).message);
    } finally {
      if (requestId === generation.current) setBusy(false);
    }
  }
  async function apply() {
    if (!plan) return;
    setBusy(true);
    setError('');
    try {
      const result = await request<{ path: string; file_count: number }>(
        `/api/projects/${project.id}/workspace-sync/apply`,
        { plan_id: plan.id },
      );
      setSuccess(
        `${result.file_count} files copied to ${plan.direction === 'to_chat' ? 'the chat sandbox' : 'VS Code'}: ${result.path}`,
      );
      setPlan(null);
      setOpened(false);
      await onRefresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const last = project.workspace_sync;
  return (
    <section className="workspace-connection">
      <div className="workspace-connection-header">
        <div>
          <span className="eyebrow">TWO ENVIRONMENTS, ONE PROJECT</span>
          <h2>Work together, keep execution separate</h2>
        </div>
      </div>
      <div className="workspace-pair">
        <div>
          <Terminal size={19} />
          <span>
            <strong>Chat sandbox</strong>
            <small>
              {project.workspace_id
                ? 'Project chats share this source tree'
                : 'Created when a chat needs project compute'}
            </small>
          </span>
          <StatePill state={project.status} />
        </div>
        <div>
          <Monitor size={19} />
          <span>
            <strong>{project.developer_name || 'Developer workstation'}</strong>
            <small>VS Code · your own packages and processes</small>
          </span>
          <StatePill state={project.developer_status || 'unknown'} />
        </div>
      </div>
      <div className="workspace-sync-actions">
        <Button
          variant="outline"
          size="sm"
          disabled={!project.workspace_id || busy}
          onClick={() => void review('to_chat')}
        >
          <ArrowDownToLine size={15} /> Copy to chat
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={!project.workspace_id || busy}
          onClick={() => void review('to_developer')}
        >
          <ArrowUpFromLine size={15} /> Copy to VS Code
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            onOpenDeveloper({
              id: project.developer_workspace_id!,
              name: project.developer_name || project.name,
              status: project.developer_status || 'unknown',
              harness_status: '',
              url: '',
              ide_url: '',
              project_id: project.id,
            })
          }
        >
          Open VS Code <ArrowRight size={15} />
        </Button>
      </div>
      <p className="workspace-sync-help">
        Review a source snapshot, then copy it to an import folder. Live files
        stay in place until you or your coding agent merge the import. Packages,
        credentials and running processes are separate.
      </p>
      {!project.workspace_id && (
        <p className="workspace-sync-help">
          Start a project chat and ask it to use a coding workspace to enable
          file transfers.
        </p>
      )}
      {(success || last) && (
        <p className="workspace-sync-result" role="status">
          <FolderOpen size={14} />
          {success ||
            `${last!.file_count} files copied ${last!.direction === 'to_chat' ? 'to chat' : 'to VS Code'} · ${new Date(last!.at * 1000).toLocaleString()}`}
        </p>
      )}
      <Dialog
        open={opened}
        onOpenChange={(open) => {
          if (!open && !busy) close();
        }}
      >
        <DialogContent className="sync-review-dialog" showCloseButton={!busy}>
          <DialogTitle>Review workspace sync</DialogTitle>
          <DialogDescription>
            Copy source into a new import folder. Nothing in the destination’s
            live source tree will be overwritten.
          </DialogDescription>
          {busy && !plan ? (
            <div className="sync-preparing">
              <LoaderCircle className="spin" />
              <strong>Preparing a file comparison</strong>
              <p>Sleeping environments may take a moment to wake.</p>
            </div>
          ) : null}
          {error && (
            <p className="project-error" role="alert">
              {error}
            </p>
          )}
          {plan && (
            <>
              <div className="sync-summary">
                <strong>
                  {plan.direction === 'to_chat'
                    ? 'VS Code → Chat sandbox'
                    : 'Chat sandbox → VS Code'}
                </strong>
                <span>
                  {plan.files.length} files · {bytes(plan.bytes)} ·{' '}
                  {plan.excluded} excluded
                </span>
              </div>
              <div className="sync-file-list">
                {plan.files.map((file) => (
                  <div key={file.path}>
                    <code>{file.path}</code>
                    <span data-change={file.change}>
                      {file.change === 'different'
                        ? 'Differs from live file'
                        : file.change === 'unchanged'
                          ? 'Matches live file'
                          : 'New file'}
                    </span>
                  </div>
                ))}
              </div>
              <p className="workspace-sync-help">
                Destination: <code>{plan.path}</code>. Review expires after five
                minutes. Up to three imports can be retained in each
                environment; move or remove older imports before adding more.
              </p>
            </>
          )}
          <div className="sync-review-actions">
            <Button variant="ghost" disabled={busy} onClick={close}>
              Cancel
            </Button>
            {plan && (
              <Button disabled={busy} onClick={() => void apply()}>
                {busy ? (
                  <LoaderCircle size={15} className="spin" />
                ) : (
                  <ArrowDownToLine size={15} />
                )}{' '}
                Copy reviewed files
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}

export function LinkWorkspace({
  workspace,
  projects,
  sessionFetch,
  onRefresh,
}: {
  workspace: Workspace;
  projects: Project[];
  sessionFetch: Fetch;
  onRefresh: () => unknown;
}) {
  const [opened, setOpened] = useState(false),
    [choice, setChoice] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => {
          setChoice(workspace.project_id || '');
          setError('');
          setOpened(true);
        }}
      >
        {workspace.project_id ? 'Change project' : 'Link project'}
      </Button>
      <Dialog open={opened} onOpenChange={setOpened}>
        <DialogContent>
          <DialogTitle>Project for {workspace.name}</DialogTitle>
          <DialogDescription>
            Link this workstation to a project. Its files and permissions stay
            separate from chat compute; transfers are explicit.
          </DialogDescription>
          <select
            className="project-select"
            value={choice}
            onChange={(e) => setChoice(e.target.value)}
          >
            {!workspace.project_id && (
              <option value="">New project named {workspace.name}</option>
            )}
            {projects
              .filter(
                (p) =>
                  !p.archived &&
                  !p.deleting &&
                  (!p.developer_workspace_id ||
                    p.developer_workspace_id === workspace.id),
              )
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
          </select>
          {error && (
            <p className="project-error" role="alert">
              {error}
            </p>
          )}
          <div className="sync-review-actions">
            <Button variant="ghost" onClick={() => setOpened(false)}>
              Cancel
            </Button>
            <Button
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  const r = await sessionFetch(
                    `/api/developer/workspaces/${workspace.id}/project`,
                    {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ project_id: choice || null }),
                    },
                  );
                  const data = (await r.json()) as { detail?: string };
                  if (!r.ok)
                    throw Error(data.detail || 'Could not link project');
                  await onRefresh();
                  setOpened(false);
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {busy ? <LoaderCircle size={15} className="spin" /> : null}Link
              project
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function OpenProjectWorkspace({
  project,
  sessionFetch,
  onRefresh,
  onOpen,
}: {
  project: Project;
  sessionFetch: Fetch;
  onRefresh: () => unknown;
  onOpen: (ws: Workspace) => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function open() {
    setBusy(true);
    setError('');
    try {
      const response = await sessionFetch(
        `/api/projects/${project.id}/developer-workspace`,
        { method: 'POST' },
      );
      const ws = (await response.json()) as Workspace & { detail?: string };
      if (!response.ok) throw Error(ws.detail || 'Could not open workstation');
      await onRefresh();
      onOpen(ws);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="project-workstation-entry">
      <div>
        <strong>Work on this project in VS Code</strong>
        <p>
          Create a linked developer workstation, then review and copy the
          project files you want to use.
        </p>
      </div>
      <Button variant="secondary" disabled={busy} onClick={() => void open()}>
        {busy ? (
          <LoaderCircle size={16} className="spin" />
        ) : (
          <Monitor size={16} />
        )}{' '}
        {busy ? 'Preparing workstation…' : 'Open in VS Code'}
      </Button>
      {error && (
        <p role="alert" className="project-error">
          {error}
        </p>
      )}
    </section>
  );
}
