'use client';
import { useEffect, useState } from 'react';
import {
  ChevronRight,
  FolderOpen,
  LoaderCircle,
  MessageSquare,
  SquarePen,
} from 'lucide-react';
import { ProjectMenu, ChatActions } from '@/components/library-actions';
import type { Project, ChatSummary } from '@/lib/lab-types';

export function ChatRow({
  chat,
  selected,
  running,
  onSelect,
}: {
  chat: ChatSummary;
  selected: boolean;
  running: boolean;
  onSelect: () => void;
}) {
  return (
    <div className={`library-chat-row ${selected ? 'selected' : ''}`}>
      <button
        className="library-chat-link"
        title={chat.title}
        onClick={onSelect}
      >
        <MessageSquare size={15} />
        <span>{chat.title || 'New conversation'}</span>
        {running && (
          <LoaderCircle size={13} className="spin" aria-label="Running" />
        )}
      </button>
      <ChatActions chat={chat} quickArchive />
    </div>
  );
}
export function ProjectSidebar({
  projects,
  currentThread,
  isChat,
  selectedProject,
  onOpen,
  onSelect,
  onNewChat,
  running,
}: {
  projects: Project[];
  currentThread: string | null;
  isChat: boolean;
  selectedProject: string | null;
  onOpen: (id: string | null) => void;
  onSelect: (id: string) => void;
  onNewChat: (id: string) => void;
  running: (id: string) => boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const active = projects.filter((p) => !p.archived);
  const recent = active.slice(0, 5);
  const currentProject = projects.find((p) =>
    p.threads.some((t) => t.id === currentThread),
  )?.id;
  useEffect(() => {
    if (currentProject)
      setCollapsed((previous) => {
        const next = new Set(previous);
        next.delete(currentProject);
        return next;
      });
  }, [currentProject]);
  return (
    <section className="project-sidebar" aria-label="Projects">
      <div
        className={`project-section-heading ${selectedProject ? 'selected' : ''}`}
      >
        <button className="project-section-link" onClick={() => onOpen(null)}>
          Projects <span>{active.length}</span>
        </button>
        <button
          className="row-action section-chevron"
          aria-label={expanded ? 'Collapse projects' : 'Expand projects'}
          aria-expanded={expanded}
          aria-controls="recent-projects"
          onClick={() => setExpanded(!expanded)}
        >
          <ChevronRight size={15} className={expanded ? 'rotated' : ''} />
        </button>
      </div>
      {expanded && (
        <div id="recent-projects">
          {recent.map((p) => {
            const open = !collapsed.has(p.id);
            const chats = p.threads
              .filter((t) => !t.archived)
              .slice()
              .sort(
                (a, b) =>
                  Number(b.id === currentThread) -
                  Number(a.id === currentThread),
              );
            return (
              <div className="project-sidebar-item" key={p.id}>
                <div
                  className={`project-sidebar-row ${selectedProject === p.id ? 'selected' : ''}`}
                >
                  <button
                    className="project-toggle"
                    aria-label={`Toggle ${p.name} conversations`}
                    aria-expanded={open}
                    onClick={() =>
                      setCollapsed((previous) => {
                        const next = new Set(previous);
                        if (next.has(p.id)) next.delete(p.id);
                        else next.add(p.id);
                        return next;
                      })
                    }
                  >
                    <ChevronRight size={12} className={open ? 'rotated' : ''} />
                  </button>
                  <button
                    className="project-sidebar-link"
                    title={p.name}
                    onClick={() => onOpen(p.id)}
                  >
                    <FolderOpen size={18} />
                    <span>{p.name}</span>
                  </button>
                  <div className="project-row-actions">
                    <ProjectMenu
                      project={p}
                      onOpen={() => onOpen(p.id)}
                      onNewChat={() => onNewChat(p.id)}
                    />
                    <button
                      className="row-action"
                      title="New chat in project"
                      aria-label={`New chat in ${p.name}`}
                      disabled={p.deleting}
                      onClick={() => onNewChat(p.id)}
                    >
                      <SquarePen size={16} />
                    </button>
                  </div>
                </div>
                {open && (
                  <div className="project-sidebar-chats">
                    {chats.slice(0, 3).map((t) => (
                      <ChatRow
                        key={t.id}
                        chat={t}
                        selected={isChat && t.id === currentThread}
                        running={running(t.id)}
                        onSelect={() => onSelect(t.id)}
                      />
                    ))}
                    {!chats.length && (
                      <p className="project-no-chats">No chats</p>
                    )}
                    {chats.length > 3 && (
                      <button
                        className="project-more-chats"
                        onClick={() => onOpen(p.id)}
                      >
                        View all {chats.length} chats
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
          {!recent.length && (
            <p className="project-no-chats">
              Projects appear when a chat needs a workspace.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
