import React, { useMemo, useState, useRef, useEffect } from 'react';
import { useLocale } from '../../i18n';
import { useChatStore, type ChatSession } from '../../store/chatStore';
import { useNodeStore } from '../../store/nodeStore';
import { TimeAgo } from '../primitives/TimeAgo';
import {
  Plus,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Server,
  Pin,
  Pencil,
  Trash2,
  Check,
  X,
} from 'lucide-react';

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
  return parts.map((p) => p.charAt(0).toUpperCase()).join('') || trimmed.charAt(0).toUpperCase();
};

const sessionHasPending = (session: ChatSession): boolean =>
  (session.history || []).some(
    (m) => m.role === 'assistant' && m.proposal?.status === 'PENDING'
  );

export const CopilotSidebar: React.FC<CopilotSidebarProps> = ({ nodeId, onOpenSearch }) => {
  const { t } = useLocale();
  const sessions = useChatStore((s) => s.sessions);
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const selectSession = useChatStore((s) => s.selectSession);
  const createSession = useChatStore((s) => s.createSession);
  const deleteSession = useChatStore((s) => s.deleteSession);
  const renameSession = useChatStore((s) => s.renameSession);
  const togglePinSession = useChatStore((s) => s.togglePinSession);
  const abortStreaming = useChatStore((s) => s.abortStreaming);
  const { nodes } = useNodeStore();
  const [expanded, setExpanded] = useState(true);

  // Renaming state
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');
  const editInputRef = useRef<HTMLInputElement>(null);

  // Deletion confirm state
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  useEffect(() => {
    if (editingSessionId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingSessionId]);

  const nodeSessions = useMemo(() => {
    const list = sessions.filter((s) => (nodeId ? s.node_id === nodeId : true));
    return [...list].sort(
      (a, b) => (b.is_pinned ? 1 : 0) - (a.is_pinned ? 1 : 0) || b.updated_at - a.updated_at
    );
  }, [sessions, nodeId]);

  const pinnedSessions = useMemo(() => nodeSessions.filter((s) => s.is_pinned), [nodeSessions]);
  const recentSessions = useMemo(() => nodeSessions.filter((s) => !s.is_pinned), [nodeSessions]);

  const handleSelect = (sessionId: string) => {
    if (sessionId === activeSessionId || editingSessionId === sessionId) return;
    if (isStreaming) abortStreaming();
    selectSession(sessionId);
  };

  const handleNewSession = async () => {
    if (isStreaming) abortStreaming();
    const nodeName = nodes.find((n) => n.id === nodeId)?.name;
    await createSession(nodeId, `Focus : ${nodeName || t('copilot.scope_global')}`);
  };

  const handleStartRename = (session: ChatSession, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingSessionId(session.id);
    setEditingTitle(session.title);
  };

  const handleSaveRename = async (sessionId: string, e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (editingTitle.trim()) {
      await renameSession(sessionId, editingTitle.trim());
    }
    setEditingSessionId(null);
  };

  const handleCancelRename = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingSessionId(null);
  };

  const handleTogglePin = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await togglePinSession(sessionId);
  };

  const handleDelete = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirmDeleteId === sessionId) {
      await deleteSession(sessionId);
      setConfirmDeleteId(null);
    } else {
      setConfirmDeleteId(sessionId);
      setTimeout(() => {
        setConfirmDeleteId((prev) => (prev === sessionId ? null : prev));
      }, 4000);
    }
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
          className="p-2 rounded-md hover:bg-surface-3/60 text-text-3 hover:text-text-1 transition-colors cursor-pointer"
          title={t('copilot.expand_sidebar')}
          aria-label={t('copilot.expand_sidebar')}
        >
          <PanelLeftOpen className="w-4 h-4" />
        </button>
        <button
          onClick={handleNewSession}
          className="p-2 rounded-md bg-accent-info/10 hover:bg-accent-info/20 text-accent-info-strong transition-colors cursor-pointer"
          title={t('copilot.new_session')}
          aria-label={t('copilot.new_session')}
        >
          <Plus className="w-4 h-4" />
        </button>
        <div className="w-full px-2 my-1 border-t border-border/40" />
        <div className="flex-1 overflow-y-auto space-y-1.5 px-1 w-full flex flex-col items-center">
          {nodeSessions.slice(0, 15).map((s) => (
            <button
              key={s.id}
              onClick={() => handleSelect(s.id)}
              title={s.title}
              className={`w-8 h-8 rounded-full relative flex items-center justify-center text-[11px] font-bold transition-all cursor-pointer ${
                s.id === activeSessionId
                  ? 'bg-accent-info text-bg border-2 border-accent-info/40 shadow-sm'
                  : 'bg-surface-3 text-text-2 hover:text-text-1 border border-border'
              } ${sessionHasPending(s) ? 'ring-2 ring-severity-critical/50' : ''}`}
            >
              {initials(s.title)}
              {s.is_pinned && (
                <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-accent-warning border border-bg flex items-center justify-center" />
              )}
            </button>
          ))}
        </div>
      </aside>
    );
  }

  const renderSessionItem = (s: ChatSession) => {
    const node = s.node_id ? nodes.find((n) => n.id === s.node_id) : null;
    const nodeLabel = node?.name || (s.node_id ? s.node_id.substring(0, 8) : t('copilot.scope_global'));
    const isActive = s.id === activeSessionId;
    const isEditing = s.id === editingSessionId;
    const isConfirming = s.id === confirmDeleteId;
    const pending = sessionHasPending(s);

    return (
      <div
        key={s.id}
        onClick={() => handleSelect(s.id)}
        className={`group relative flex items-center gap-2 px-2.5 py-2 rounded-lg transition-all cursor-pointer ${
          isActive
            ? 'bg-accent-info/15 text-text-1 border border-accent-info/30 shadow-xs'
            : 'hover:bg-surface-3/50 text-text-2 border border-transparent'
        } ${pending ? 'border-l-2 border-l-severity-critical' : ''}`}
      >
        <span
          className={`w-6 h-6 rounded-full flex items-center justify-center text-[9.5px] font-bold shrink-0 ${
            isActive ? 'bg-accent-info text-bg' : 'bg-surface-3 text-text-2 group-hover:text-text-1'
          }`}
        >
          {initials(s.title)}
        </span>

        {isEditing ? (
          <form
            onSubmit={(e) => handleSaveRename(s.id, e)}
            className="flex-1 min-w-0 flex items-center gap-1"
            onClick={(e) => e.stopPropagation()}
          >
            <input
              ref={editInputRef}
              type="text"
              value={editingTitle}
              onChange={(e) => setEditingTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') setEditingSessionId(null);
              }}
              className="flex-1 bg-surface-2 border border-accent-info/50 text-text-1 text-xs px-1.5 py-0.5 rounded focus:outline-none"
            />
            <button
              type="submit"
              className="p-1 text-status-online hover:bg-surface-3 rounded cursor-pointer"
              title={t('copilot.sidebar_save')}
            >
              <Check className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={handleCancelRename}
              className="p-1 text-text-3 hover:text-text-1 hover:bg-surface-3 rounded cursor-pointer"
              title={t('copilot.sidebar_cancel')}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </form>
        ) : (
          <div className="flex-1 min-w-0 pr-1">
            <div className="flex items-center gap-1">
              {s.is_pinned && <Pin className="w-2.5 h-2.5 text-accent-warning shrink-0 fill-current" />}
              <p className={`text-[11.5px] font-medium truncate ${isActive ? 'text-text-1 font-semibold' : 'text-text-2'}`}>
                {s.title}
              </p>
            </div>
            <div className="flex items-center gap-1.5 text-[9.5px] text-text-3 mt-0.5">
              <Server className="w-2.5 h-2.5 shrink-0 opacity-70" />
              <span className="truncate max-w-[85px]">{nodeLabel}</span>
              <span>·</span>
              <TimeAgo timestamp={s.updated_at} />
            </div>
          </div>
        )}

        {/* Action buttons (Pin, Edit, Delete) */}
        {!isEditing && (
          <div
            className={`flex items-center gap-0.5 transition-opacity ${
              isActive || isConfirming || s.is_pinned ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
            }`}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={(e) => handleTogglePin(s.id, e)}
              className={`p-1 rounded hover:bg-surface-3 transition-colors cursor-pointer ${
                s.is_pinned ? 'text-accent-warning' : 'text-text-3 hover:text-text-1'
              }`}
              title={s.is_pinned ? t('copilot.sidebar_unpin') : t('copilot.sidebar_pin')}
            >
              <Pin className={`w-3 h-3 ${s.is_pinned ? 'fill-current' : ''}`} />
            </button>

            <button
              type="button"
              onClick={(e) => handleStartRename(s, e)}
              className="p-1 rounded hover:bg-surface-3 text-text-3 hover:text-text-1 transition-colors cursor-pointer"
              title={t('copilot.sidebar_rename')}
            >
              <Pencil className="w-3 h-3" />
            </button>

            <button
              type="button"
              onClick={(e) => handleDelete(s.id, e)}
              className={`p-1 rounded transition-colors cursor-pointer ${
                isConfirming
                  ? 'bg-severity-critical text-bg font-bold animate-pulse text-[9px] px-1.5'
                  : 'hover:bg-severity-critical/15 text-text-3 hover:text-severity-critical'
              }`}
              title={isConfirming ? t('copilot.sidebar_confirm_delete') : t('copilot.sidebar_delete')}
            >
              {isConfirming ? t('copilot.sidebar_delete_confirm') : <Trash2 className="w-3 h-3" />}
            </button>
          </div>
        )}
      </div>
    );
  };

  return (
    <aside
      className="cp-sidebar shrink-0 flex flex-col border-r border-glass-border font-sans"
      style={{ width: 'var(--copilot-sidebar-width)' }}
      aria-label={t('copilot.sidebar_label')}
    >
      <header className="flex items-center justify-between px-3 py-2.5 border-b border-glass-border">
        <span className="text-[10px] font-bold uppercase tracking-widest text-text-3 font-interface pl-1">
          {t('copilot.sessions')} ({nodeSessions.length})
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={handleNewSession}
            className="p-1.5 rounded-md hover:bg-accent-info/15 text-text-3 hover:text-accent-info-strong transition-colors cursor-pointer"
            title={t('copilot.new_session')}
            aria-label={t('copilot.new_session')}
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
          {onOpenSearch && (
            <button
              onClick={onOpenSearch}
              className="p-1.5 rounded-md hover:bg-surface-3/60 text-text-3 hover:text-text-1 transition-colors cursor-pointer"
              title={t('copilot.search_sessions')}
              aria-label={t('copilot.search_sessions')}
            >
              <Search className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            onClick={() => setExpanded(false)}
            className="p-1.5 rounded-md hover:bg-surface-3/60 text-text-3 hover:text-text-1 transition-colors cursor-pointer"
            title={t('copilot.collapse_sidebar')}
            aria-label={t('copilot.collapse_sidebar')}
          >
            <PanelLeftClose className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-3">
        {nodeSessions.length === 0 ? (
          <p className="text-[11px] text-text-3 italic px-3 py-4 text-center">
            {t('copilot.no_sessions')}
          </p>
        ) : (
          <>
            {pinnedSessions.length > 0 && (
              <div className="space-y-1">
                <div className="px-2 py-0.5 flex items-center gap-1.5 text-[9.5px] font-bold text-accent-warning uppercase tracking-wider">
                  <Pin className="w-2.5 h-2.5 fill-current" />
                  <span>{t('copilot.sidebar_pinned_section')} ({pinnedSessions.length})</span>
                </div>
                {pinnedSessions.map(renderSessionItem)}
              </div>
            )}

            {recentSessions.length > 0 && (
              <div className="space-y-1">
                {pinnedSessions.length > 0 && (
                  <div className="px-2 pt-2 pb-0.5 text-[9.5px] font-bold text-text-3 uppercase tracking-wider border-t border-border/30">
                    <span>{t('copilot.sidebar_recent_section')}</span>
                  </div>
                )}
                {recentSessions.map(renderSessionItem)}
              </div>
            )}
          </>
        )}
      </div>
    </aside>
  );
};
