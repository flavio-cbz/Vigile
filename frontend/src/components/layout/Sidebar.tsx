import React, { useState, useEffect } from 'react';
import { useLocation, Link } from 'react-router';
import { api } from '../../hooks/useApi';
import { useAuthStore } from '../../store/authStore';
import { usePermission } from '../../hooks/usePermission';
import { useLayoutStore } from '../../store/layoutStore';
import { useNodeStore } from '../../store/nodeStore';
import {
  LayoutDashboard, CheckSquare, Grid, X, ChevronsLeft, ChevronsRight,
  MessageSquareCode, Server, Settings as SettingsIcon, ChevronDown,
  ChevronRight, Activity, Play, Container,
} from 'lucide-react';
import { VigileLogo } from '../ui/VigileLogo';
import { useLocale } from '../../i18n';
import { SidebarNavItem } from './SidebarNavItem';
import type { NavItem } from '../../types';
import type { AdminPluginInfo } from '../../types/plugins';

export const Sidebar: React.FC = () => {
  const { isAdmin, isOperator } = usePermission();
  const { t } = useLocale();
  const user = useAuthStore((state) => state.user);
  const { isSidebarOpen, isSidebarCollapsed, setSidebarOpen, toggleSidebarCollapse } = useLayoutStore();
  const { nodes } = useNodeStore();
  const location = useLocation();

  const [isMobile, setIsMobile] = useState(false);
  const pendingCount = useLayoutStore((s) => s.pendingCount);
  const [activePlugins, setActivePlugins] = useState<string[]>(['systemd', 'docker', 'metrics', 'disk_analysis', 'clean_logs', 'plex']);
  const [isAdminExpanded, setIsAdminExpanded] = useState(() => localStorage.getItem('vigile_admin_expanded') !== 'false');
  const [nonRunningContainerCount, setNonRunningContainerCount] = useState(0);

  useEffect(() => {
    const checkActivePlugins = async () => {
      try {
        const response = await api<AdminPluginInfo[] | { plugins: AdminPluginInfo[] }>('/api/admin/plugins');
        const list = Array.isArray(response) ? response : (response?.plugins || []);
        const activeIds = list
          .filter((p) => Boolean(p.enabled && p.loaded))
          .map((p) => p.id);
        setActivePlugins(activeIds);
      } catch (err) {
        console.error('Failed to check active plugins:', err);
      }
    };
    void checkActivePlugins();
  }, [location.pathname]);

  useEffect(() => {
    const fetchContainerCounts = async () => {
      const onlineNodes = nodes.filter((n) => n.online);
      if (onlineNodes.length === 0) return;
      try {
        const results = await Promise.allSettled(
          onlineNodes.map(async (node) => {
            const res = await api<{ containers: { state: string; status: string }[] }>(
              `/api/nodes/${node.id}/containers`,
              { skipToast: true },
            );
            return res?.containers ?? [];
          }),
        );
        let count = 0;
        for (const r of results) {
          if (r.status === 'fulfilled') {
            for (const c of r.value) {
              const s = (c.state ?? '').toLowerCase();
              const st = (c.status ?? '').toLowerCase();
              if (s !== 'running' && !st.includes('up')) count++;
            }
          }
        }
        setNonRunningContainerCount(count);
      } catch {
        // sidebar badge is best-effort, ignore failures
      }
    };
    void fetchContainerCounts();
  }, [nodes]);

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  const isSingleServer = nodes.length === 1;
  const collapsed = !isMobile && isSidebarCollapsed;

  const handleNavClick = () => { if (isMobile) setSidebarOpen(false); };

  const toggleAdmin = () => {
    setIsAdminExpanded((prev) => {
      const next = !prev;
      localStorage.setItem('vigile_admin_expanded', String(next));
      return next;
    });
  };

  const computeActive = (item: NavItem, currentTab: string | null): boolean => {
    if (item.to === '/chat/new' || item.to === '#') return false; // handled separately
    if (item.to.includes('tab=services')) return location.pathname.includes('/nodes/') && currentTab === 'services';
    if (item.to.includes('tab=containers')) return location.pathname.includes('/nodes/') && currentTab === 'containers';
    return item.exact ? location.pathname === item.to : location.pathname.startsWith(item.to);
  };

  const renderServerSelector = () => {
    if (!isSingleServer) return null;
    const srv = nodes[0];
    return (
      <div className={`flex items-center gap-2.5 px-4 py-3 select-none border-b border-border-strong/30 ${
        collapsed ? 'justify-center px-2' : 'justify-center'
      }`}>
        <span className={`w-2 h-2 rounded-full shrink-0 ${
          srv?.online ? 'bg-green-custom shadow-[0_0_6px_var(--color-green-glow)]' : 'bg-ink-muted'
        }`} />
        {!collapsed && (
          <div className="min-w-0 flex-1">
            <div className="text-[11px] font-bold text-text-1 truncate leading-tight uppercase font-mono">
              {srv?.name || t('sidebar.server')}
            </div>
            <div className="text-[9px] font-mono text-text-3 truncate">
              {srv?.hostname || t('sidebar.connected')}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderNav = () => {
    const nodeMatch = location.pathname.match(/\/nodes\/([^/]+)/);
    const activeNodeId = nodeMatch ? nodeMatch[1] : (nodes[0]?.id || '');
    const currentTab = new URLSearchParams(location.search).get('tab');

    const isSystemdActive = activePlugins.includes('systemd');
    const isDockerActive = activePlugins.includes('docker');
    const isPlexActive = activePlugins.includes('plex');

    const primaryItems: NavItem[] = [
      { to: '/', label: t('nav.dashboard'), icon: LayoutDashboard, exact: true },
      { to: '/servers', label: t('nav.servers'), icon: Server },
    ];

    if (isSystemdActive) {
      primaryItems.push({ to: activeNodeId ? `/nodes/${activeNodeId}?tab=services` : '/servers', label: t('nav.services'), icon: Activity });
    }

    primaryItems.push(
      { to: '/proposals', label: t('nav.proposals'), icon: CheckSquare, badge: pendingCount > 0 ? pendingCount : undefined },
      { to: '/chat/new', label: t('nav.chat'), icon: MessageSquareCode, dot: true }
    );

    if (isPlexActive) {
      primaryItems.push({ to: '/plugins?open=plex', label: 'Plex', icon: Play });
    }

    if (isDockerActive) {
      primaryItems.push({
        to: activeNodeId ? `/nodes/${activeNodeId}?tab=containers` : '/servers',
        label: t('nav.docker'),
        icon: Container,
        badge: nonRunningContainerCount > 0 ? nonRunningContainerCount : undefined,
      });
    }

    const adminItems: NavItem[] = [
      { to: '/plugins', label: t('nav.plugins'), icon: Grid },
      { to: '/settings', label: t('nav.settings'), icon: SettingsIcon },
    ];

    const renderLink = (item: NavItem, index: number) => {
      const isActive = item.to === '/chat/new' ? false : computeActive(item, currentTab);
      return <SidebarNavItem key={`${item.to}-${item.label}-${index}`} item={item} collapsed={collapsed} isActive={isActive} currentTab={currentTab} pathname={location.pathname} onNavClick={handleNavClick} t={t} />;
    };

    return (
      <nav className="flex-1 overflow-y-auto py-3 scrollbar-none flex flex-col gap-4 scrollable-list">
        <div>
          {!collapsed && (
            <div className="text-[9px] font-bold text-text-3 uppercase tracking-widest px-4 pb-1.5 font-mono">
              {t('sidebar.navigation')}
            </div>
          )}
          <div className={`flex flex-col gap-1 ${collapsed ? 'items-center' : ''}`}>
            {primaryItems.map((item, i) => renderLink(item, i))}
          </div>
        </div>

        {(isAdmin || isOperator) && (
          <div>
            {collapsed ? (
              <>
                <div className="border-t border-border-strong/30 my-2 w-5/6 mx-auto" />
                <div className="flex flex-col gap-1 items-center">
                  {adminItems.map((item, i) => renderLink(item, i))}
                </div>
              </>
            ) : (
              <>
                <button
                  onClick={toggleAdmin}
                  className="flex items-center justify-between w-full px-4 py-1.5 text-[9px] font-bold text-text-3 uppercase tracking-widest hover:text-text-1 hover:bg-surface-2/30 rounded-lg transition-colors cursor-pointer text-left font-mono"
                >
                  <span>{t('nav.admin')}</span>
                  {isAdminExpanded ? <ChevronDown className="w-3.5 h-3.5 text-text-3 shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-text-3 shrink-0" />}
                </button>
                {isAdminExpanded && (
                  <div className="flex flex-col gap-1 pl-1.5 mt-1 animate-fade-in">
                    {adminItems.map((item, i) => renderLink(item, i))}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </nav>
    );
  };

  if (isMobile) {
    return (
      <>
        {isSidebarOpen && <div className="fixed inset-0 bg-black/70 backdrop-blur-xs z-40" onClick={() => setSidebarOpen(false)} />}
        <nav className={`fixed top-0 left-0 h-full w-[260px] bg-surface/95 backdrop-blur-xs z-50 flex flex-col transition-transform duration-300 ease-in-out overflow-hidden border-r border-border-strong/30 shadow-[var(--shadow-sidebar)] ${
          isSidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}>
          <div className="flex items-center gap-2.5 h-14 px-4 border-b border-border-strong/30 shrink-0">
            <Link to="/" onClick={handleNavClick} className="flex items-center gap-2.5 hover:opacity-80 transition-opacity cursor-pointer text-text-1 hover:text-text-1">
              <VigileLogo className="w-7 h-7" />
              <span className="font-bold text-xs uppercase tracking-widest font-mono">{t('sidebar.brand')}</span>
            </Link>
            <button onClick={() => setSidebarOpen(false)} className="ml-auto p-1.5 rounded hover:bg-surface-2/60 text-text-2 hover:text-text-1 cursor-pointer transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>
          {renderServerSelector()}
          {renderNav()}
          <Link to="/settings" onClick={handleNavClick} className="p-3 border-t border-border-strong/30 shrink-0 block hover:bg-surface-hover/30 transition-colors duration-150" title={t('sidebar.profile_settings')}>
            <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg bg-surface-2/20 border border-border-strong/10">
              <div className={`w-8 h-8 rounded-full border flex items-center justify-center shrink-0 ${isAdmin ? 'border-accent shadow-[0_0_8px_var(--color-accent-glow)] bg-accent-muted/15' : 'border-accent/40 bg-accent-muted/5'}`}>
                <span className={`text-[11px] font-bold uppercase font-mono ${isAdmin ? 'text-accent' : 'text-text-2'}`}>{user?.username?.charAt(0) || 'U'}</span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-bold text-text-1 truncate leading-tight uppercase font-mono">{user?.username || t('sidebar.default_username')}</div>
                <div className={`text-[8px] font-extrabold uppercase tracking-wider font-mono mt-0.5 inline-block px-1 rounded-sm leading-none py-0.5 border ${isAdmin ? 'text-accent border-accent/20 bg-accent-muted/5' : 'text-text-2 border-border bg-surface-2'}`}>{user?.role || t('sidebar.default_role')}</div>
              </div>
            </div>
          </Link>
        </nav>
      </>
    );
  }

  return (
    <div className={`relative h-full bg-surface/95 backdrop-blur-xs border-r border-border-strong/30 flex flex-col shrink-0 select-none z-40 transition-[width] duration-250 ease-out shadow-[4px_0_32px_rgba(0,0,0,0.5)] ${collapsed ? 'sidebar-collapsed' : ''}`} style={{ width: 'var(--sidebar-width)' }}>
      <div className="w-full h-full flex flex-col overflow-hidden">
        <div className={`flex items-center h-[var(--topbar-height)] border-b border-border-strong/30 shrink-0 overflow-hidden ${collapsed ? 'justify-center' : 'gap-2.5 px-4'}`}>
          <Link to="/" className={`flex items-center gap-2.5 hover:opacity-80 transition-opacity cursor-pointer text-text-1 hover:text-text-1 shrink-0 ${collapsed ? '' : 'animate-fade-in'}`}>
            <VigileLogo className="w-7 h-7 xl:w-8.5 xl:h-8.5" />
            {!collapsed && <span className="font-bold text-xs xl:text-sm uppercase tracking-widest font-mono">{t('sidebar.brand')}</span>}
          </Link>
        </div>
        {renderServerSelector()}
        {collapsed && isSingleServer && <div className="border-t border-border-strong/30" />}
        {renderNav()}
        <Link to="/settings" onClick={handleNavClick} className={`border-t border-border-strong/30 shrink-0 block hover:bg-surface-hover/30 transition-colors duration-150 group relative ${collapsed ? 'p-2.5' : 'p-3 xl:p-4'}`} title={collapsed ? undefined : t("sidebar.profile_settings")}>
          <div className={`flex items-center gap-2.5 xl:gap-3 rounded-lg ${collapsed ? 'justify-center' : 'px-2 py-1.5 bg-surface-2/20 border border-border-strong/10'}`}>
            <div className={`rounded-full border flex items-center justify-center shrink-0 transition-transform duration-200 group-hover:scale-105 ${collapsed ? 'w-8 h-8' : 'w-8 h-8 xl:w-9.5 xl:h-9.5'} ${isAdmin ? 'border-accent shadow-[0_0_8px_var(--color-accent-glow)] bg-accent-muted/15' : 'border-accent/40 bg-accent-muted/5'}`}>
              <span className={`text-[11px] xl:text-[13px] font-bold uppercase font-mono ${isAdmin ? 'text-accent' : 'text-text-2'}`}>{user?.username?.charAt(0) || 'U'}</span>
            </div>
            {!collapsed && (
              <div className="flex-1 min-w-0">
                <div className="text-[11px] xl:text-[12.5px] font-bold text-text-1 truncate leading-tight uppercase font-mono">{user?.username || t('sidebar.default_username')}</div>
                <div className={`text-[8px] xl:text-[9.5px] font-extrabold uppercase tracking-wider font-mono mt-0.5 inline-block px-1 rounded-sm leading-none py-0.5 border ${isAdmin ? 'text-accent border-accent/20 bg-accent-muted/5' : 'text-text-2 border-border bg-surface-2'}`}>{user?.role || t('sidebar.default_role')}</div>
              </div>
            )}
          </div>
          {collapsed && (
            <div className="absolute left-full ml-3 top-1/2 -translate-y-1/2 px-2 py-1 rounded bg-surface-2 border border-border-strong/70 text-text-1 text-[10px] font-medium tracking-wide whitespace-nowrap shadow-lg pointer-events-none opacity-0 translate-x-[-4px] group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-150 z-50 uppercase font-mono">
              {user?.username || t("sidebar.default_username")} ({user?.role || t("sidebar.default_role")})
            </div>
          )}
        </Link>
      </div>
      <button onClick={toggleSidebarCollapse} className="absolute top-7 right-0 translate-x-1/2 z-50 w-6 h-6 rounded-full border border-border-strong/80 bg-surface-2/95 backdrop-blur-xs flex items-center justify-center text-text-3 hover:text-text-1 hover:border-accent/40 shadow-[var(--shadow-toggle)] hover:scale-105 cursor-pointer transition-colors duration-200" title={collapsed ? t('sidebar.toggle_expand') : t('sidebar.toggle_collapse')}>
        {collapsed ? <ChevronsRight className="w-3 h-3 text-accent" /> : <ChevronsLeft className="w-3 h-3" />}
      </button>
    </div>
  );
};
