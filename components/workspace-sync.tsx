'use client';
import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { FolderOpen, Monitor, Terminal, LoaderCircle } from 'lucide-react';
import { StatePill } from '@/components/state-pill';
import type { Project, Workspace } from '@/lib/lab-types';
import { OpenProjectWorkspaceButton } from '@/components/open-project-workspace';
type Fetch = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

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
  const last = project.workspace_sync;
  const [resolving, setResolving] = useState('');
  const [syncError, setSyncError] = useState('');
  async function resolve(path: string, keep: 'chat' | 'developer') {
    if (resolving) return;
    setResolving(path);
    setSyncError('');
    try {
      const response = await sessionFetch(
        `/api/projects/${project.id}/source-sync/resolve`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path, keep }),
        },
      );
      const data = (await response.json()) as { detail?: string };
      if (!response.ok)
        throw Error(data.detail || 'Could not resolve this file');
      await onRefresh();
    } catch (e) {
      setSyncError((e as Error).message);
    } finally {
      setResolving('');
    }
  }
  return (
    <section className="workspace-connection">
      <div className="workspace-connection-header">
        <h2>Developer workstation</h2>
      </div>
      <div className="workspace-pair">
        <div>
          <Terminal size={19} />
          <span>
            <strong>Chat sandbox</strong>
            <small>
              {project.workspace_id
                ? 'Shared by project chats'
                : 'Starts when source or coding needs it'}
            </small>
          </span>
          <StatePill state={project.status} />
        </div>
        <div>
          <Monitor size={19} />
          <span>
            <strong>{project.developer_name || 'Developer workstation'}</strong>
            <small>VS Code · separate packages and processes</small>
          </span>
          <StatePill state={project.developer_status || 'unknown'} />
        </div>
      </div>
      <div className="workspace-sync-actions">
        <OpenProjectWorkspaceButton
          project={project}
          sessionFetch={sessionFetch}
          onRefresh={onRefresh}
          onOpen={onOpenDeveloper}
        />
      </div>
      <p className="workspace-sync-help">
        Source files sync automatically while both workspaces are running, and
        catch up when you open either environment. Packages, credentials and
        processes remain separate.
      </p>
      {last && (
        <p className="workspace-sync-result" role="status">
          <FolderOpen size={14} />
          {last.state === 'conflict'
            ? `${last.conflict_count} file conflicts`
            : last.state === 'retrying'
              ? 'Sync will retry'
              : `${last.file_count} source files synced`}{' '}
          · {new Date(last.at * 1000).toLocaleTimeString()}
        </p>
      )}
      {last?.conflicts?.map((path) => (
        <div className="source-sync-conflict" key={path}>
          <code>{path}</code>
          <span>Changed on both sides</span>
          <div>
            <Button
              size="sm"
              variant="outline"
              disabled={!!resolving}
              onClick={() => void resolve(path, 'chat')}
            >
              Keep chat
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!!resolving}
              onClick={() => void resolve(path, 'developer')}
            >
              Keep VS Code
            </Button>
          </div>
        </div>
      ))}
      {(syncError || last?.error) && (
        <p className="project-error" role="alert">
          {syncError || last?.error}
        </p>
      )}
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
            Link this workstation to a project. Its source files sync
            automatically with chat compute; credentials, packages and processes
            stay separate.
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
  return (
    <section className="project-workstation-entry">
      <div>
        <strong>Work on this project in VS Code</strong>
        <p>
          Your source opens automatically in a separate developer workstation.
        </p>
      </div>
      <OpenProjectWorkspaceButton
        project={project}
        sessionFetch={sessionFetch}
        onRefresh={onRefresh}
        onOpen={onOpen}
      />
    </section>
  );
}
