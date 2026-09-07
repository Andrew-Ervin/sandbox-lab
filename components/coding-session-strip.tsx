import { useEffect, useState } from 'react';
import { LoaderCircle, Square, Terminal, WifiOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { startPolling } from '@/lib/polling';

type Session = { session_id: string; status: string; active: boolean };
type Fetch = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;
const labels: Record<string, string> = {
  running: 'Coding',
  waiting: 'Code session idle',
  error: 'Code session failed',
  requires_action: 'Coding needs attention',
  interrupting: 'Stopping coding…',
  unknown: 'Code session reconnecting',
  deleted: 'Code session unavailable',
  stopping_workspace: 'Stopping workspace…',
  stopped: 'Code workspace stopped',
  stop_failed: 'Workspace stop needs retry',
};

/** Coder outlives a lost chat response. Observe it without extending idle time. */
export function CodingSessionStrip({
  thread,
  sessionFetch,
  progress,
  onInspect,
  onStopChat,
  onError,
}: {
  thread: string | null;
  sessionFetch: Fetch;
  progress?: string;
  onInspect: () => void;
  onStopChat: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [observed, setObserved] = useState<{
    thread: string;
    session: Session | null;
  } | null>(null);
  const [stopping, setStopping] = useState(false);
  useEffect(() => {
    if (!thread) return;
    let disposed = false;
    const stop = startPolling({
      run: async () => {
        const response = await sessionFetch(
          `/api/threads/${thread}/coding-session`,
        );
        if (!response.ok) throw Error('Coding status unavailable');
        const session = (await response.json()) as Session | null;
        if (!disposed) setObserved({ thread, session });
      },
      interval: () => 5000,
      onError: () => {
        if (!disposed)
          setObserved((old) =>
            old?.thread === thread && old.session
              ? { thread, session: { ...old.session, status: 'unknown' } }
              : old,
          );
      },
    });
    return () => {
      disposed = true;
      stop();
    };
  }, [thread, sessionFetch]);
  const session = observed?.thread === thread ? observed.session : null;
  if (!progress && !session) return null;
  const busy = session?.active;
  return (
    <section className="run-strip" aria-label="Code session">
      <button onClick={onInspect} title={progress || 'View execution details'}>
        {session?.status === 'unknown' ? (
          <WifiOff size={15} />
        ) : busy || progress ? (
          <LoaderCircle size={15} className="spin" />
        ) : (
          <Terminal size={15} />
        )}
        <span>
          {session
            ? labels[session.status] || `Coder · ${session.status}`
            : progress}
          {session && progress && !busy ? ' · Responding' : ''}
        </span>
      </button>
      {session && (busy || session.status === 'unknown') && (
        <Button
          size="sm"
          variant="ghost"
          title="Stops the coding agent and headless workspace processes. Files are retained; app previews can be reopened."
          disabled={
            stopping ||
            ['interrupting', 'stopping_workspace'].includes(session.status)
          }
          onClick={async () => {
            setStopping(true);
            try {
              const response = await sessionFetch(
                `/api/threads/${thread}/coding-session/stop`,
                {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ session_id: session.session_id }),
                },
              );
              const body = (await response.json()) as Session & {
                detail?: string;
              };
              if (!response.ok)
                throw Error(body.detail || 'Could not stop coding');
              setObserved({ thread: thread!, session: body });
            } catch (error) {
              onError(
                error instanceof Error
                  ? error.message
                  : 'Could not stop coding',
              );
            } finally {
              setStopping(false);
            }
          }}
        >
          <Square size={12} />
          {stopping ? 'Stopping…' : 'Stop coding'}
        </Button>
      )}
      {progress && !busy && (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => void onStopChat().catch((e) => onError(e.message))}
        >
          <Square size={12} />
          Stop response
        </Button>
      )}
    </section>
  );
}
