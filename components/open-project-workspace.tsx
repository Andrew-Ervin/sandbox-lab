'use client';
import { useState } from 'react';
import { LoaderCircle, Monitor } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { Project, Workspace } from '@/lib/lab-types';
type Fetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export function OpenProjectWorkspaceButton({ project, sessionFetch, onRefresh, onOpen }: {
  project: Project;
  sessionFetch: Fetch;
  onRefresh: () => unknown;
  onOpen: (ws: Workspace) => void | Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function open() {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const response = await sessionFetch(`/api/projects/${project.id}/developer-workspace`, { method: 'POST' });
      const ws = (await response.json()) as Workspace & { detail?: string };
      if (!response.ok) throw Error(ws.detail || 'Could not open workstation');
      await onOpen(ws);
      await onRefresh();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="workspace-open-action">
    <Button variant="ghost" size="sm" disabled={busy || project.archived || project.deleting} onClick={() => void open()}
      title="Copy project source and open it in your separate developer workstation">
      {busy ? <LoaderCircle size={15} className="spin" /> : <Monitor size={15} />}
      {busy ? 'Opening project…' : 'Open in VS Code'}
    </Button>
    {error && <p role="alert" className="workspace-open-error">{error}</p>}
  </div>;
}
