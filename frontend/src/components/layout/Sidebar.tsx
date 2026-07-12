import React, { useState, useEffect } from 'react';
import { NavLink, useLocation, Link } from 'react-router';
import { useAuthStore } from '../../store/authStore';
import { usePermission } from '../../hooks/usePermission';
import { useLayoutStore } from '../../store/layoutStore';
import { useNodeStore } from '../../store/nodeStore';
import { useUiStore } from '../../store/uiStore';
import {
  LayoutDashboard,
  CheckSquare,
  Grid,
  X,
  ChevronsLeft,
  ChevronsRight,
  MessageSquareCode,
  Server,
  Settings as SettingsIcon,
  ChevronDown,
  ChevronRight,
  Zap,
  Container,
  Activity,
} from 'lucide-react';
import { VigileLogo } from '../ui/VigileLogo';
import { useLocale } from '../../i18n';
import type { NavItem } from '../../types';

export const Sidebar: React.FC = () => {
  const { isAdmin, isOperator } = usePermission();
  const { t } = useLocale();
  const copilotOpen = useUiStore((state) => state.copilotOpen);
  const user = useAuthStore((state) => state.user);
  const {
    isSidebarOpen,
    isSidebarCollapsed,
    setSidebarOpen,
    toggleSidebarCollapse,
  } = useLayoutStore();
  const { nodes } = useNodeStore();
  const location = useLocation();

  const [isMobile, setIsMobile] = useState(false);
  const pendingCount = useLayoutStore((s) => s.pendingCount);

  const isSingleServer = nodes.length === 1;

  const [isAdminExpanded, setIsAdminExpanded] = useState(() => localStorage.getItem('vigile_admin_expanded') !== 'false');

  const toggleAdmin = () => {
    setIsAdminExpanded((prev) => {
      const next = !prev;
      localStorage.setItem('vigile_admin_expanded', String(next));
      return next;
    });
  };

  useEffect(() => {
    const check = () => {
      setIsMobile(window.innerWidth < 768);
    };
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  const handleNavClick = () => {
    if (isMobile) setSidebarOpen(false);
  };

  const collapsed = !isMobile && isSidebarCollapsed;

  const renderServerSelector = () => {
    if (!isSingleServer) return null;

    const srv = nodes[0];
    return (
      <div className={`flex items-center gap-2.5 px-4 py-3 select-none border-b border-border-strong/30 ${
        collapsed ? 'justify-center px-2' : 'justify-center'
      }`}>
        <span
          className={`w-2 h-2 rounded-full shrink-0 ${
            srv?.online
              ? 'bg-green-custom shadow-[0_0_6px_var(--color-green-glow)]'
              : 'bg-ink-muted'
          }`}
        />
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
    const primaryItems = [
      { to: '/', label: t('nav.dashboard'), icon: LayoutDashboard, exact: true },
      { to: '/servers', label: t('nav.servers'), icon: Server },
      {
        to: '/services',
        label: t('nav.services'),
        icon: Activity,
      },
      {
        to: '/docker',
        label: t('nav.docker'),
        icon: Container,
      },
      {
        to: '/proposals',
        label: t('nav.proposals'),
        icon: CheckSquare,
        badge: pendingCount > 0 ? pendingCount : undefined,
      },
      {
        to: '/chat/new',
        label: t('nav.chat'),
        icon: MessageSquareCode,
        dot: true,
      },
    ];

    const adminItems = [
      { to: '/automations', label: t('nav.automations'), icon: Zap },
      { to: '/plugins', label: t('nav.plugins'), icon: Grid },
      { to: '/settings', label: t('nav.settings'), icon: SettingsIcon },
    ];

    const renderLink = (item: NavItem) => {
      const Icon = item.icon;
      const isActive = item.to === '/chat/new'
        ? copilotOpen
        : (item.exact
            ? location.pathname === item.to
            : location.pathname.startsWith(item.to));

      return (
        <NavLink
          key={item.to}
          to={item.to === '/chat/new' ? '#' : item.to}
          end={item.exact}
          onClick={(e) => {
            if (item.to === '/chat/new') {
              e.preventDefault();
              const store = useUiStore.getState();
              if (store.copilotOpen) {
                store.closeCopilot();
              } else {
                store.openCopilot({ trigger: 'manual' });
              }
            } else {
              handleNavClick();
            }
          }}
          className={`group relative flex items-center gap-2.5 rounded-lg transition-all duration-200 ${
            collapsed
              ? 'w-9 h-9 justify-center mx-auto'
              : 'px-2.5 py-2 mx-2 xl:px-3.5 xl:py-2.5 xl:mx-3'
          } ${
            isActive
              ? 'text-accent bg-accent-soft/80 shadow-[0_0_12px_var(--color-accent-glow)] border border-accent/15'
              : 'text-text-2 hover:text-text-1 hover:bg-surface-2/40 border border-transparent'
          }`}
        >
          {isActive && (
            <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[2.5px] h-4 bg-accent rounded-r-full shadow-[0_0_8px_var(--color-accent-glow)]" />
          )}
          <Icon className="w-4 h-4 xl:w-4.5 xl:h-4.5 shrink-0 transition-transform duration-200 group-hover:scale-110" />
          {!collapsed && (
            <span className="text-[11px] xl:text-[12.5px] font-medium flex-1 truncate uppercase font-mono tracking-wide">{item.label}</span>
          )}

          {!collapsed && item.badge !== undefined && (
            <span className="text-[9px] xl:text-[10px] font-bold px-1.5 py-0.5 rounded bg-severity-warning/15 border border-severity-warning/25 text-severity-warning">
              {item.badge}
            </span>
          )}
          {!collapsed && item.dot && !isActive && (
            <span className="w-1.5 h-1.5 rounded-full bg-accent shadow-[0_0_4px_var(--color-accent-glow)]" title={t("sidebar.new_activity")} />
          )}
          {collapsed && item.badge !== undefined && (
            <span className="absolute -top-1 -right-1 text-[8px] font-bold px-1.5 py-0.5 rounded-full bg-severity-warning text-white leading-none min-w-[14px] text-center shadow-md">
              {item.badge}
            </span>
          )}
          {collapsed && item.dot && !isActive && (
            <span className="absolute top-0.5 right-0.5 w-2.5 h-2.5 rounded-full bg-accent border-2 border-surface shadow-[0_0_4px_var(--color-accent-glow)]" title={t("sidebar.new_activity")} />
          )}

          {/* Floating CSS Tooltip when collapsed */}
          {collapsed && (
            <div className="absolute left-full ml-3 px-2 py-1 rounded bg-surface-2 border border-border-strong/70 text-text-1 text-[10px] font-medium tracking-wide whitespace-nowrap shadow-lg pointer-events-none opacity-0 translate-x-[-4px] group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-150 z-50 uppercase font-mono max-w-[200px] break-words">
              {item.label}
            </div>
          )}
        </NavLink>
      );
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
            {primaryItems.map(renderLink)}
          </div>
        </div>

        {(isAdmin || isOperator) && (
        <div>
          {collapsed ? (
            <>
              <div className="border-t border-border-strong/30 my-2 w-5/6 mx-auto" />
              <div className="flex flex-col gap-1 items-center">
                {adminItems.map(renderLink)}
              </div>
            </>
          ) : (
            <>
              <button
                onClick={toggleAdmin}
                className="flex items-center justify-between w-full px-4 py-1.5 text-[9px] font-bold text-text-3 uppercase tracking-widest hover:text-text-1 hover:bg-surface-2/30 rounded-lg transition-colors cursor-pointer text-left font-mono"
              >
                <span>{t('nav.admin')}</span>
                {isAdminExpanded ? (
                  <ChevronDown className="w-3.5 h-3.5 text-text-3 shrink-0" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-text-3 shrink-0" />
                )}
              </button>
              {isAdminExpanded && (
                <div className="flex flex-col gap-1 pl-1.5 mt-1 animate-fade-in">
                  {adminItems.map(renderLink)}
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
        {isSidebarOpen && (
          <div
            className="fixed inset-0 bg-black/70 backdrop-blur-xs z-40"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <nav
          className={`fixed top-0 left-0 h-full w-[260px] bg-surface/85 backdrop-blur-md z-50 flex flex-col transition-transform duration-300 ease-in-out overflow-hidden border-r border-border-strong/30 shadow-[0_0_24px_var(--shadow-sidebar)] ${
            isSidebarOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          <div className="flex items-center gap-2.5 h-14 px-4 border-b border-border-strong/30 shrink-0">
            <Link
              to="/"
              onClick={handleNavClick}
              className="flex items-center gap-2.5 hover:opacity-80 transition-opacity cursor-pointer text-text-1 hover:text-text-1"
            >
              <VigileLogo className="w-7 h-7" />
              <span className="font-bold text-xs uppercase tracking-widest font-mono">{t('sidebar.brand')}</span>
            </Link>
            <button
              onClick={() => setSidebarOpen(false)}
              className="ml-auto p-1.5 rounded hover:bg-surface-2/60 text-text-2 hover:text-text-1 cursor-pointer transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {renderServerSelector()}
          {renderNav()}

          <Link
            to="/settings"
            onClick={handleNavClick}
            className="p-3 border-t border-border-strong/30 shrink-0 block hover:bg-surface-hover/30 transition-colors duration-150"
            title={t('sidebar.profile_settings')}
          >
            <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg bg-surface-2/20 border border-border-strong/10">
              <div className={`w-8 h-8 rounded-full border flex items-center justify-center shrink-0 ${
                isAdmin
                  ? 'border-accent shadow-[0_0_8px_var(--color-accent-glow)] bg-accent-muted/15'
                  : 'border-accent/40 bg-accent-muted/5'
              }`}>
                <span className={`text-[11px] font-bold uppercase font-mono ${
                  isAdmin ? 'text-accent' : 'text-text-2'
                }`}>
                  {user?.username?.charAt(0) || 'U'}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-bold text-text-1 truncate leading-tight uppercase font-mono">
                  {user?.username || t('sidebar.default_username')}
                </div>
                <div className={`text-[8px] font-extrabold uppercase tracking-wider font-mono mt-0.5 inline-block px-1 rounded-sm leading-none py-0.5 border ${
                  isAdmin
                    ? 'text-accent border-accent/20 bg-accent-muted/5'
                    : 'text-text-2 border-border bg-surface-2'
                }`}>
                  {user?.role || t('sidebar.default_role')}
                </div>
              </div>
            </div>
          </Link>
        </nav>
      </>
    );
  }

  return (
    <div
      className={`relative h-full bg-surface/75 backdrop-blur-md border-r border-border-strong/30 flex flex-col shrink-0 select-none z-40 transition-[width] duration-250 ease-out shadow-[4px_0_24px_var(--shadow-sidebar)] ${
        collapsed ? 'sidebar-collapsed' : ''
      }`}
      style={{ width: 'var(--sidebar-width)' }}
    >
      <div className="w-full h-full flex flex-col overflow-hidden">
        <div className={`flex items-center h-[var(--topbar-height)] border-b border-border-strong/30 shrink-0 overflow-hidden ${
          collapsed ? 'justify-center' : 'gap-2.5 px-4'
        }`}>
          <Link
            to="/"
            className={`flex items-center gap-2.5 hover:opacity-80 transition-opacity cursor-pointer text-text-1 hover:text-text-1 shrink-0 ${
              collapsed ? '' : 'animate-fade-in'
            }`}
          >
            <VigileLogo className="w-7 h-7 xl:w-8.5 xl:h-8.5" />
            {!collapsed && (
              <span className="font-bold text-xs xl:text-sm uppercase tracking-widest font-mono">
                {t('sidebar.brand')}
              </span>
            )}
          </Link>
        </div>

        {renderServerSelector()}

        {collapsed && isSingleServer && <div className="border-t border-border-strong/30" />}

        {renderNav()}

        <Link
          to="/settings"
          onClick={handleNavClick}
          className={`border-t border-border-strong/30 shrink-0 block hover:bg-surface-hover/30 transition-colors duration-150 group relative ${
            collapsed ? 'p-2.5' : 'p-3 xl:p-4'
          }`}
          title={collapsed ? undefined : t("sidebar.profile_settings")}
        >
          <div className={`flex items-center gap-2.5 xl:gap-3 rounded-lg ${
            collapsed ? 'justify-center' : 'px-2 py-1.5 bg-surface-2/20 border border-border-strong/10'
          }`}>
            <div className={`rounded-full border flex items-center justify-center shrink-0 transition-transform duration-200 group-hover:scale-105 ${
              collapsed ? 'w-8 h-8' : 'w-8 h-8 xl:w-9.5 xl:h-9.5'
            } ${
              isAdmin
                ? 'border-accent shadow-[0_0_8px_var(--color-accent-glow)] bg-accent-muted/15'
                : 'border-accent/40 bg-accent-muted/5'
            }`}>
              <span className={`text-[11px] xl:text-[13px] font-bold uppercase font-mono ${
                isAdmin ? 'text-accent' : 'text-text-2'
              }`}>
                {user?.username?.charAt(0) || 'U'}
              </span>
            </div>

            {!collapsed && (
              <div className="flex-1 min-w-0">
                <div className="text-[11px] xl:text-[12.5px] font-bold text-text-1 truncate leading-tight uppercase font-mono">
                  {user?.username || t('sidebar.default_username')}
                </div>
                <div className={`text-[8px] xl:text-[9.5px] font-extrabold uppercase tracking-wider font-mono mt-0.5 inline-block px-1 rounded-sm leading-none py-0.5 border ${
                  isAdmin
                    ? 'text-accent border-accent/20 bg-accent-muted/5'
                    : 'text-text-2 border-border bg-surface-2'
                }`}>
                  {user?.role || t('sidebar.default_role')}
                </div>
              </div>
            )}
          </div>

          {/* Floating CSS Tooltip when collapsed */}
          {collapsed && (
            <div className="absolute left-full ml-3 top-1/2 -translate-y-1/2 px-2 py-1 rounded bg-surface-2 border border-border-strong/70 text-text-1 text-[10px] font-medium tracking-wide whitespace-nowrap shadow-lg pointer-events-none opacity-0 translate-x-[-4px] group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-150 z-50 uppercase font-mono">
              {user?.username || t("sidebar.default_username")} ({user?.role || t("sidebar.default_role")})
            </div>
          )}
        </Link>
      </div>

      {/* Floating toggle button - outside the overflow-hidden wrapper so it doesn't get clipped! */}
      <button
        onClick={toggleSidebarCollapse}
        className="absolute top-7 right-0 translate-x-1/2 z-50 w-6 h-6 rounded-full border border-border-strong/80 bg-surface-2/95 backdrop-blur-md flex items-center justify-center text-text-3 hover:text-text-1 hover:border-accent/40 shadow-[0_2px_8px_var(--shadow-toggle)] hover:scale-105 cursor-pointer transition-all duration-200"
        title={collapsed ? t('sidebar.toggle_expand') : t('sidebar.toggle_collapse')}
      >
        {collapsed ? (
          <ChevronsRight className="w-3 h-3 text-accent" />
        ) : (
          <ChevronsLeft className="w-3 h-3" />
        )}
      </button>
    </div>
  );
};
