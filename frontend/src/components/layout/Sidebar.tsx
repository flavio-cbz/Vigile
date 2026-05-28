import React, { useState, useEffect, useRef } from 'react';
import { NavLink, useNavigate, useLocation, Link } from 'react-router';
import { useAuthStore } from '../../store/authStore';
import { useLayoutStore } from '../../store/layoutStore';
import { useNodeStore } from '../../store/nodeStore';
import {
  ShieldAlert,
  LayoutDashboard,
  CheckSquare,
  Activity,
  Grid,
  Plus,
  Search,
  X,
  ChevronsLeft,
  ChevronsRight,
  MessageSquareCode,
  Server,
  Settings as SettingsIcon,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { useLocale } from '../../i18n';
const SIDEBAR_EXPANDED = 240;
const SIDEBAR_COLLAPSED = 60;

export const Sidebar: React.FC = () => {
  const user = useAuthStore((state) => state.user);
  const isAdmin = user?.role === 'admin';
  const {
    isSidebarOpen,
    isSidebarCollapsed,
    setSidebarOpen,
    toggleSidebarCollapse,
    setAddNodeModalOpen,
  } = useLayoutStore();
  const { nodes, selectedNodeId, selectNode } = useNodeStore();
  const navigate = useNavigate();
  const location = useLocation();

  const [isMobile, setIsMobile] = useState(false);
  const pendingCount = useLayoutStore((s) => s.pendingCount);
  const [showServerDropdown, setShowServerDropdown] = useState(false);
  const [serverSearch, setServerSearch] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);

  const isSingleServer = nodes.length === 1;
  const isGlobal = selectedNodeId === 'all' || !selectedNodeId;
  const activeNode = nodes.find((n) => n.id === selectedNodeId) || null;

  const [isAdminExpanded, setIsAdminExpanded] = useState(() => localStorage.getItem('vigile_admin_expanded') !== 'false');

  const toggleAdmin = () => {
    setIsAdminExpanded((prev) => {
      const next = !prev;
      localStorage.setItem('vigile_admin_expanded', String(next));
      return next;
    });
  };

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowServerDropdown(false);
        setServerSearch('');
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleNavClick = () => {
    if (isMobile) setSidebarOpen(false);
  };

  const collapsed = !isMobile && isSidebarCollapsed;

  const sidebarWidth = isMobile ? 260 : collapsed ? SIDEBAR_COLLAPSED : SIDEBAR_EXPANDED;

  // ─── Server Selector ───
  const renderServerSelector = () => {
    if (isSingleServer) {
      const srv = nodes[0];
      return (
        <div className="flex items-center justify-between gap-2.5 px-4 py-3 select-none border-b border-border-custom/30">
          <div className="flex items-center gap-2.5 min-w-0 flex-1">
            <span
              className={`w-2 h-2 rounded-full shrink-0 ${
                srv?.online
                  ? 'bg-green-custom shadow-[0_0_6px_var(--color-green-glow)]'
                  : 'bg-ink-muted'
              }`}
            />
            <div className="min-w-0 flex-1">
              <div className="text-[0.6875rem] font-semibold text-ink truncate leading-tight">
                {srv?.name || 'Serveur'}
              </div>
              <div className="text-[0.5rem] font-mono text-ink-muted truncate">
                {srv?.hostname || 'Connecté'}
              </div>
            </div>
          </div>
          {isAdmin && (
            <button
              onClick={() => setAddNodeModalOpen(true)}
              className="p-1.5 rounded hover:bg-surface-hover text-accent-custom hover:text-accent-custom/80 cursor-pointer transition-colors duration-150 shrink-0"
              title="Ajouter un serveur"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      );
    }

    const current = isGlobal ? null : activeNode;

    return (
      <div ref={dropdownRef} className="relative px-3 py-2">
        <div className="text-[0.5rem] font-bold text-ink/75 uppercase tracking-wider mb-1.5 px-1">
          Serveur actif
        </div>
        <button
          onClick={() => setShowServerDropdown(!showServerDropdown)}
          className="flex items-center gap-2 w-full px-2.5 py-2 rounded-lg border border-border-strong bg-surface-alt hover:border-accent-border hover:bg-accent-soft transition-all duration-150 cursor-pointer text-left"
        >
          <span
            className={`w-2 h-2 rounded-full shrink-0 ${
              current
                ? current.online
                  ? 'bg-green-custom shadow-[0_0_5px_var(--color-green-glow)]'
                  : 'bg-ink-muted'
                : 'bg-accent-custom shadow-[0_0_5px_var(--color-accent-glow)]'
            }`}
          />
          <div className="flex-1 min-w-0">
            <div className="text-[0.6875rem] font-semibold text-ink truncate leading-tight">
              {current ? current.name : 'Tous les serveurs'}
            </div>
            <div className="text-[0.5rem] font-mono text-ink truncate">
              {current
                ? current.online
                  ? 'En ligne'
                  : 'Hors ligne'
                : `${nodes.filter((n) => n.online).length} en ligne`}
            </div>
          </div>
          <svg
            className={`w-3 h-3 text-ink-dim shrink-0 transition-transform duration-200 ${
              showServerDropdown ? 'rotate-180' : ''
            }`}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        {showServerDropdown && (
          <div className="absolute left-3 right-3 top-full mt-1 z-50 rounded-lg border border-border-strong bg-surface-alt shadow-xl overflow-hidden">
            {/* Sticky search input */}
            <div className="sticky top-0 z-10 bg-surface-alt border-b border-border-strong px-2 py-2">
              <div className="relative">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-ink-muted pointer-events-none" />
                <input
                  type="text"
                  value={serverSearch}
                  onChange={(e) => setServerSearch(e.target.value)}
                  placeholder="Rechercher un serveur..."
                  className="w-full pl-7 pr-7 py-1.5 text-[0.6875rem] bg-bg border border-border-strong rounded text-ink placeholder-ink-muted focus:border-accent-border focus:outline-hidden transition-colors"
                  autoFocus
                />
                {serverSearch && (
                  <button
                    onClick={() => setServerSearch('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink transition-colors cursor-pointer"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>
            <button
              onClick={() => {
                selectNode('all');
                navigate('/');
                setShowServerDropdown(false);
                setServerSearch('');
                handleNavClick();
              }}
              className={`flex items-center gap-2.5 w-full px-3 py-2.5 text-left text-[0.6875rem] font-medium transition-colors duration-100 border-b border-border last:border-b-0 ${
                isGlobal ? 'bg-accent-soft text-accent-custom' : 'text-ink-dim hover:bg-surface-hover'
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-accent-custom shadow-[0_0_5px_var(--color-accent-glow)] shrink-0" />
              Tous les serveurs
              <span className="ml-auto text-[0.5rem] font-mono text-ink-muted">{nodes.length}</span>
            </button>
            {nodes
              .filter(node => !serverSearch || node.name.toLowerCase().includes(serverSearch.toLowerCase()))
              .map((node) => (
              <button
                key={node.id}
                onClick={() => {
                  selectNode(node.id);
                  navigate(`/nodes/${node.id}`);
                  setShowServerDropdown(false);
                  setServerSearch('');
                  handleNavClick();
                }}
                className={`flex items-center gap-2.5 w-full px-3 py-2.5 text-left text-[0.6875rem] font-medium transition-colors duration-100 ${
                  selectedNodeId === node.id
                    ? 'bg-accent-soft text-accent-custom'
                    : 'text-ink-dim hover:bg-surface-hover'
                }`}
              >
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${
                    node.online
                      ? 'bg-green-custom shadow-[0_0_5px_var(--color-green-glow)]'
                      : 'bg-ink-muted'
                  }`}
                />
                <span className="truncate">{node.name}</span>
                <span className="ml-auto text-[0.5rem] font-mono text-ink">
                  {node.online ? 'en ligne' : 'hors ligne'}
                </span>
              </button>
            ))}
            {isAdmin && (
              <button
                onClick={() => {
                  setAddNodeModalOpen(true);
                  setShowServerDropdown(false);
                  setServerSearch('');
                }}
                className="flex items-center gap-2.5 w-full px-3 py-2.5 text-left text-[0.6875rem] font-medium text-accent-custom border-t border-border hover:bg-accent-soft transition-colors duration-100"
              >
                <Plus className="w-3.5 h-3.5" />
                Ajouter un serveur
              </button>
            )}
          </div>
        )}
      </div>
    );
  };

  // ─── Navigation ───
  const renderNav = () => {
    const { t } = useLocale();

    // Primary navigation items
    const primaryItems = [
      { to: '/', label: t('nav.dashboard'), icon: LayoutDashboard, exact: true, key: '⌘1' },
      { to: '/servers', label: t('nav.servers'), icon: Server, key: '⌘2' },
      {
        to: '/proposals',
        label: t('nav.proposals'),
        icon: CheckSquare,
        badge: pendingCount > 0 ? pendingCount : undefined,
        key: '⌘3',
      },
      {
        to: '/chat/new',
        label: t('nav.chat'),
        icon: MessageSquareCode,
        dot: true,
        key: '⌘4',
      },
    ];

    // Admin/Secondary navigation items
    const adminItems = [
      { to: '/plugins', label: t('nav.plugins'), icon: Grid },
      { to: '/audit', label: t('nav.audit'), icon: Activity },
      { to: '/settings', label: t('nav.settings'), icon: SettingsIcon },
    ];

    const renderLink = (item: any) => {
      const Icon = item.icon;
      const isActive = item.exact
        ? location.pathname === item.to
        : location.pathname.startsWith(item.to) ||
          (item.to === '/chat/new' && location.pathname.startsWith('/chat/'));

      return (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.exact}
          onClick={handleNavClick}
          className={`relative flex items-center gap-2.5 rounded-lg transition-all duration-150 ${
            collapsed
              ? 'w-9 h-9 justify-center mx-auto'
              : 'px-2.5 py-2'
          } ${
            isActive
              ? 'text-accent-custom bg-accent-soft'
              : 'text-ink-dim hover:text-ink hover:bg-surface-alt'
          }`}
        >
          {isActive && !collapsed && (
            <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 bg-accent-custom rounded-r-full shadow-[0_0_6px_var(--color-accent-glow)]" />
          )}
          <Icon className="w-4 h-4 shrink-0" />
          {!collapsed && (
            <span className="text-[0.75rem] font-medium flex-1 truncate">{item.label}</span>
          )}
          {!collapsed && item.badge !== undefined && (
            <span className="text-[0.5rem] font-bold px-1.5 py-0.5 rounded-full bg-amber-soft border border-amber-border text-amber-custom">
              {item.badge}
            </span>
          )}
          {!collapsed && item.dot && (
            <span className="w-1.5 h-1.5 rounded-full bg-accent-custom shadow-[0_0_4px_var(--color-accent-glow)]" />
          )}
          {collapsed && item.badge !== undefined && (
            <span className="absolute -top-0.5 -right-0.5 text-[0.4375rem] font-bold px-1 py-0.5 rounded-full bg-amber-soft border border-amber-border text-amber-custom leading-none min-w-[14px] text-center">
              {item.badge}
            </span>
          )}
          {collapsed && item.dot && (
            <span className="absolute -bottom-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-accent-custom shadow-[0_0_4px_var(--color-accent-glow)]" />
          )}
        </NavLink>
      );
    };

    return (
      <nav className="flex-1 overflow-y-auto px-2 py-2 scrollbar-none flex flex-col gap-4">
        {/* Navigation Section */}
        <div>
          {!collapsed && (
            <div className="text-[0.5rem] font-bold text-ink/75 uppercase tracking-wider px-2 pb-1.5">
              Navigation
            </div>
          )}
          <div className={`flex flex-col gap-0.5 ${collapsed ? 'items-center' : ''}`}>
            {primaryItems.map(renderLink)}
          </div>
        </div>

        {/* Administration Section */}
        <div>
          {collapsed ? (
            <>
              <div className="border-t border-border-custom/50 my-2 w-full" />
              <div className="flex flex-col gap-0.5 items-center">
                {adminItems.map(renderLink)}
              </div>
            </>
          ) : (
            <>
              <button
                onClick={toggleAdmin}
                className="flex items-center justify-between w-full px-2 py-1.5 text-[0.5rem] font-bold text-ink/75 uppercase tracking-wider hover:text-ink hover:bg-surface-alt rounded-lg transition-colors cursor-pointer text-left"
              >
                <span>{t('nav.admin')}</span>
                {isAdminExpanded ? (
                  <ChevronDown className="w-3.5 h-3.5 text-ink-muted shrink-0" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-ink-muted shrink-0" />
                )}
              </button>
              {isAdminExpanded && (
                <div className="flex flex-col gap-0.5 pl-1.5 mt-0.5 animate-fade-in">
                  {adminItems.map(renderLink)}
                </div>
              )}
            </>
          )}
        </div>
      </nav>
    );
  };

  // ─── Mobile Drawer ───
  if (isMobile) {
    return (
      <>
        {isSidebarOpen && (
          <div
            className="fixed inset-0 bg-black/70 backdrop-blur-xs z-40"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <nav
          className={`fixed top-0 left-0 h-full w-[260px] bg-surface z-50 flex flex-col transition-transform duration-300 ease-in-out overflow-hidden ${
            isSidebarOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          <div className="flex items-center gap-2.5 h-14 px-4 border-b border-border-custom shrink-0">
            <Link
              to="/"
              onClick={handleNavClick}
              className="flex items-center gap-2.5 hover:opacity-80 transition-opacity cursor-pointer text-ink hover:text-ink"
            >
              <div className="w-7 h-7 rounded-md border border-accent-border bg-accent-soft flex items-center justify-center">
                <ShieldAlert className="w-3.5 h-3.5 text-accent-custom" />
              </div>
              <span className="font-bold text-[0.8125rem]">Vigile</span>
            </Link>
            <button
              onClick={() => setSidebarOpen(false)}
              className="ml-auto p-1 rounded hover:bg-surface-hover text-ink-muted cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {renderServerSelector()}
          {renderNav()}

          {/* User */}
          <Link
            to="/settings"
            onClick={handleNavClick}
            className="p-2 border-t border-border-custom shrink-0 block hover:bg-surface-hover/50 transition-colors duration-150"
            title="Mon Profil & Paramètres"
          >
            <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg">
              <div className="w-7 h-7 rounded-md border border-border-strong bg-surface-alt flex items-center justify-center shrink-0">
                <span className="text-[0.5625rem] font-bold text-ink-muted uppercase">
                  {user?.username?.charAt(0) || 'U'}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[0.6875rem] font-semibold text-ink truncate leading-tight">
                  {user?.username || 'Utilisateur'}
                </div>
                <div className="text-[0.4375rem] font-bold text-ink-muted uppercase tracking-wider">
                  {user?.role || 'visiteur'}
                </div>
              </div>
            </div>
          </Link>
        </nav>
      </>
    );
  }

  // ─── Desktop ───
  return (
    <nav
      className="h-full bg-surface border-r border-border-custom flex flex-col shrink-0 overflow-hidden select-none z-40 transition-[width] duration-250 ease-out"
      style={{ width: sidebarWidth }}
    >
      {/* Brand + Collapse */}
      <div className={`flex items-center h-14 border-b border-border-custom shrink-0 overflow-hidden ${
        collapsed ? 'justify-center' : 'gap-2.5 px-4'
      }`}>
        {!collapsed ? (
          <Link
            to="/"
            className="flex items-center gap-2.5 hover:opacity-80 transition-opacity cursor-pointer text-ink hover:text-ink shrink-0 animate-fade-in"
          >
            <div className="w-7 h-7 rounded-md border border-accent-border bg-accent-soft flex items-center justify-center">
              <ShieldAlert className="w-3.5 h-3.5 text-accent-custom" />
            </div>
            <span className="font-bold text-[0.8125rem] whitespace-nowrap overflow-hidden transition-opacity duration-150">
              Vigile
            </span>
          </Link>
        ) : null}
        <button
          onClick={toggleSidebarCollapse}
          className={`w-6 h-6 rounded flex items-center justify-center transition-all duration-150 cursor-pointer shrink-0 ${
            collapsed
              ? 'text-ink/70 hover:text-ink hover:bg-surface-alt'
              : 'ml-auto text-ink/70 hover:text-ink hover:bg-surface-alt'
          }`}
          title={collapsed ? 'Étendre la sidebar' : 'Réduire la sidebar'}
        >
          {collapsed ? (
            <ChevronsRight className="w-3.5 h-3.5" />
          ) : (
            <ChevronsLeft className="w-3.5 h-3.5" />
          )}
        </button>
      </div>

      {/* Server selector — only visible when expanded */}
      {!collapsed && renderServerSelector()}

      {/* Divider when collapsed */}
      {collapsed && <div className="border-t border-border-custom" />}

      {/* Navigation */}
      {renderNav()}

      {/* User — compact info */}
      <Link
        to="/settings"
        onClick={handleNavClick}
        className="p-2 border-t border-border-custom shrink-0 block hover:bg-surface-hover/50 transition-colors duration-150"
        title="Mon Profil & Paramètres"
      >
        <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg">
          <div className={`rounded-md border border-border-strong bg-surface-alt flex items-center justify-center shrink-0 ${
            collapsed ? 'w-7 h-7 mx-auto' : 'w-7 h-7'
          }`}>
            <span className="text-[0.5625rem] font-bold text-ink-muted uppercase">
              {user?.username?.charAt(0) || 'U'}
            </span>
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <div className="text-[0.6875rem] font-semibold text-ink truncate leading-tight">
                {user?.username || 'Utilisateur'}
              </div>
              <div className="text-[0.4375rem] font-bold text-ink-muted uppercase tracking-wider">
                {user?.role || 'visiteur'}
              </div>
            </div>
          )}
        </div>
      </Link>
    </nav>
  );
};
