import React, { useState, useEffect } from 'react';
import { useLocation, Link } from 'react-router';
import { useLayoutStore } from '../../store/layoutStore';
import { useNodeStore } from '../../store/nodeStore';
import { useAuthStore } from '../../store/authStore';
import { MessageSquareCode, Menu, Plus, RefreshCw } from 'lucide-react';
import { useLocale } from '../../i18n';

export const TopBar: React.FC = () => {
  const { isCopilotOpen, toggleCopilot, setSidebarOpen, isSidebarOpen, setAddNodeModalOpen } = useLayoutStore();
  const { nodes, selectedNodeId, fetchNodes } = useNodeStore();
  const { user } = useAuthStore();
  const location = useLocation();
  const { t } = useLocale();

  const pendingCount = useLayoutStore((s) => s.pendingCount);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await fetchNodes();
    } catch (err) {
      console.error(err);
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchNodes();
  }, [fetchNodes]);

  // Current server context for badge
  const isGlobal = selectedNodeId === 'all' || !selectedNodeId;
  const activeNode = isGlobal ? null : nodes.find((n) => n.id === selectedNodeId) || null;

  const getBreadcrumbs = () => {
    const path = location.pathname;
    if (path === '/') return [t('nav.dashboard')];
    if (path.startsWith('/nodes/') || path === '/servers') return [t('nav.servers')];
    if (path === '/proposals') return [t('nav.proposals')];
    if (path === '/audit') return [t('nav.audit')];
    if (path === '/plugins') return [t('nav.plugins')];
    if (path === '/settings') return [t('nav.settings')];
    if (path.startsWith('/chat/')) return [t('nav.chat')];
    return [];
  };

  const breadcrumbs = getBreadcrumbs();
  const isAdmin = user?.role === 'admin';

  return (
    <header className="h-[60px] px-6 border-b border-border-custom bg-surface/50 backdrop-blur-md flex items-center justify-between shrink-0 z-40 relative">
      {/* Left: Breadcrumbs + Server Context Badge */}
      <div className="flex items-center gap-2.5 text-[0.6875rem] font-semibold text-ink-muted">
        {breadcrumbs.map((bc, idx) => (
          <React.Fragment key={idx}>
            {idx > 0 && <span className="opacity-30">/</span>}
            <span className={idx === breadcrumbs.length - 1 ? 'text-ink' : ''}>{bc}</span>
          </React.Fragment>
        ))}

        {/* Server context badge */}
        {activeNode ? (
          <span className="flex items-center gap-1.5 px-2 py-1 rounded border border-border-strong text-[0.625rem] font-bold text-ink cursor-default select-none">
            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
              activeNode.online
                ? 'bg-green-custom shadow-[0_0_6px_var(--color-green-glow)]'
                : 'bg-ink-muted'
            }`} />
            <span className="truncate max-w-[130px]">{activeNode.name}</span>
          </span>
        ) : nodes.length > 0 ? (
          <span className="flex items-center gap-1.5 px-2 py-1 rounded border border-accent-border bg-accent-soft text-[0.5625rem] font-bold text-accent-custom cursor-default select-none">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-custom shadow-[0_0_5px_var(--color-accent-glow)]" />
            {nodes.filter((n) => n.online).length} {t('dash.servers_online').split(' ')[1] || 'en ligne'}
          </span>
        ) : null}
      </div>

      {/* Right */}
      <div className="flex items-center gap-3">
        {/* Mobile Sidebar Toggle */}
        <button
          onClick={() => setSidebarOpen(!isSidebarOpen)}
          className="md:hidden p-2 rounded border border-border-strong hover:border-accent-border text-ink-muted hover:text-ink hover:bg-surface-hover transition-all duration-200 cursor-pointer"
          title="Menu"
        >
          <Menu className="w-4 h-4" />
        </button>

        {/* Refresh (Actualiser) - Ghost button */}
        <button
          onClick={handleRefresh}
          disabled={isRefreshing}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-border-strong text-ink-muted hover:text-ink hover:bg-surface-hover text-[0.6875rem] font-medium transition-all duration-150 cursor-pointer disabled:opacity-50"
          title={t('btn.refresh')}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline">{t('btn.refresh')}</span>
        </button>

        {/* Add Server CTA - prominent for Admin only */}
        {isAdmin && (
          <button
            onClick={() => setAddNodeModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent-custom hover:bg-accent-hover text-white text-[0.6875rem] font-semibold cursor-pointer transition-colors duration-150"
            title={t('add_node.title')}
          >
            <Plus className="w-3.5 h-3.5" />
            <span>{t('add_node.title')}</span>
          </button>
        )}

        {/* Proposals indicator */}
        {pendingCount > 0 && (
          <Link
            to="/proposals"
            className="flex items-center gap-1.5 text-[0.625rem] font-bold px-2 py-1 rounded bg-amber-soft border border-amber-border text-amber-custom animate-pulse shadow-[0_0_8px_rgba(212,168,80,0.1)]"
          >
            <span>{pendingCount} Prop{pendingCount > 1 ? 's' : ''}</span>
          </Link>
        )}

        {/* Copilot toggle */}
        <button
          onClick={toggleCopilot}
          className={`relative p-2 rounded border transition-all duration-200 cursor-pointer ${
            isCopilotOpen
              ? 'border-accent-custom bg-accent-soft text-accent-custom shadow-[0_0_12px_rgba(20,184,166,0.15)]'
              : 'border-border-strong hover:border-accent-border text-ink-muted hover:text-ink hover:bg-surface-hover'
          }`}
          title="Copilot IA (Ctrl+` ou Cmd+`)"
        >
          <MessageSquareCode className="w-4 h-4" />
          {pendingCount > 0 && !isCopilotOpen && (
            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-accent-custom rounded-full animate-badge-pulse" />
          )}
        </button>
      </div>
    </header>
  );
};


