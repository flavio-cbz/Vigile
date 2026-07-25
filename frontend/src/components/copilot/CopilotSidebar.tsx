import React, { useMemo, useState } from 'react';
import { useLocale } from '../../i18n';
import { useChatStore, type ChatSession } from '../../store/chatStore';
import { useNodeStore } from '../../store/nodeStore';
import { TimeAgo } from '../primitives/TimeAgo';
import { Plus, PanelLeftClose, PanelLeftOpen, Search, Server } from 'lucide-react';

interface CopilotSidebarProps {
  /** Filter sessions by this node id (null = global/fleet sessions). */
  nodeId: string | null;
  /** Called when the user requests opening the find-session palette. */
  onOpenSearch?: () => void;
}

const initials = (title: string): string => {
  const trimmed = title.trim();
  if (!trimmed) return '·';
  const parts = trimmed.split(/[\s:_-]+/).filter(Boolean).slice(0, 2);
  return parts.map(p => p.charAt(0).toUpperCase()).join('') || trimmed.charAt(0).toUpperCase();
};

const sessionHasPending = (session: ChatSession): boolean =>
  (session.history || []).some(
    m => m.role === 'assistant' && m.proposal?.status === 'PENDING'
  );

export const CopilotSidebar: React.FC<CopilotSidebarProps> = ({ nodeId, onOpenSearch }) => {
  const { t } = useLocale();
  const { sessions, activeSessionId, selectSession, createSession, abortStreaming, isStreaming } = useChatStore();
  const { nodes } = useNodeStore();
  const [expanded, setExpanded] = useState(true);

  const nodeSessions = useMemo(
    () => sessions.filter(s => (nodeId ? s.node_id === nodeId : true)),
    [sessions, nodeId]
  );

  const handleSelect = (sessionId: string) => {
    if (sessionId === activeSessionId) return;
    // Abort any in-flight stream before switching to avoid race conditions.
    if (isStreaming) abortStreaming();
    selectSession(sessionId);
  };

  const handleNewSession = async () => {
    if (isStreaming) abortStreaming();
    const nodeName = nodes.find(n => n.id === nodeId)?.name;
    await createSession(nodeId, `Focus : ${nodeName || t('copilot.scope_global')}`);
  };

  if (!expanded) {
    return (
      <aside
        className="cp-sidebar shrink-0 flex flex-col items-center gap-2 py-3"
        style={{ width: 'var(--copilot-sidebar-collapsed-width)' }}
        aria-label={t('copilot.sidebar_label')}
      >
        <button
          onClick={() => setExpanded(true)}
          className="p-2 rounded-md hover:bg-surface-3/60 text-text-3 hover:text-text-1 transition-colors"
          title={t('copilot.expand_sidebar')}
          aria-label={t('copilot.expand_sidebar')}
        >
          <PanelLeftOpen className="w-4 h-4" />
        </button>
        <button
          onClick={handleNewSession}
          className="p-2 rounded-md bg-accent/10 hover:bg-accent/20 text-accent transition-colors"
          title={t('copilot.new_session')}
          aria-label={t('copilot.new_session')}
        >
          <Plus className="w-4 h-4" />
        </button>
        {nodeSessions.slice(0, 10).map((s) => (
          <button
            key={s.id}
            onClick={() => handleSelect(s.id)}
            title={s.title}
            className={`w-8 h-8 rounded-full flex items-center justify-center text-[11px] font-bold transition-all ${
              s.id === activeSessionId
                ? 'bg-accent text-bg border-2 border-accent/40'
                : 'bg-surface-3 text-text-2 hover:text-text-1 border border-border'
            } ${sessionHasPending(s) ? 'ring-2 ring-severity-critical/50' : ''}`}
          >
            {initials(s.title)}
          </button>
        ))}
      </aside>
    );
  }

  return (
    <aside
      className="cp-sidebar shrink-0 flex flex-col"
      style={{ width: 'var(--copilot-sidebar-width)' }}
      aria-label={t('copilot.sidebar_label')}
    >
      <header className="flex items-center justify-between px-3 py-2.5 border-b border-glass-border">
        <span className="text-[10px] font-bold uppercase tracking-widest text-text-3 font-interface pl-1">
          {t('copilot.sessions')}
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={handleNewSession}
            className="p-1.5 rounded-md hover:bg-accent/15 text-text-3 hover:text-accent transition-colors"
            title={t('copilot.new_session')}
            aria-label={t('copilot.new_session')}
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
          {onOpenSearch && (
            <button
              onClick={onOpenSearch}
              className="p-1.5 rounded-md hover:bg-surface-3/60 text-text-3 hover:text-text-1 transition-colors"
              title={t('copilot.search_sessions')}
              aria-label={t('copilot.search_sessions')}
            >
              <Search className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            onClick={() => setExpanded(false)}
            className="p-1.5 rounded-md hover:bg-surface-3/60 text-text-3 hover:text-text-1 transition-colors"
            title={t('copilot.collapse_sidebar')}
            aria-label={t('copilot.collapse_sidebar')}
          >
            <PanelLeftClose className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
        {nodeSessions.length === 0 ? (
          <p className="text-[11px] text-text-3 italic px-3 py-4 text-center">
            {t('copilot.no_sessions')}
          </p>
        ) : (
          nodeSessions.map((s) => {
            const node = s.node_id ? nodes.find(n => n.id === s.node_id) : null;
            const nodeLabel = node?.name || (s.node_id ? s.node_id.substring(0, 8) : t('copilot.scope_global'));
            const isActive = s.id === activeSessionId;
            const pending = sessionHasPending(s);
            return (
              <button
                key={s.id}
                onClick={() => handleSelect(s.id)}
                className={`cp-session-item w-full text-left ${isActive ? 'is-active' : ''} ${pending ? 'is-pending' : ''}`}
              >
                <span
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 ${
                    isActive
                      ? 'bg-accent text-bg'
                      : 'bg-surface-3 text-text-2'
                  }`}
                >
                  {initials(s.title)}
                </span>
                <div className="flex-1 min-w-0">
                  <p className={`text-[12px] font-medium truncate ${isActive ? 'text-text-1' : 'text-text-2'}`}>
                    {s.title}
                  </p>
                  <div className="flex items-center gap-1.5 text-[9.5px] text-text-3 mt-0.5">
                    <Server className="w-2.5 h-2.5 shrink-0" />
                    <span className="truncate">{nodeLabel}</span>
                    <span>·</span>
                    <TimeAgo timestamp={s.updated_at} />
                  </div>
                </div>
              </button>
            );
          })
        )}
      </div>
    </aside>
  );
};
