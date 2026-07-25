import React from 'react';
import { NavLink } from 'react-router';
import { useUiStore } from '../../store/uiStore';
import { clsx } from 'clsx';
import type { NavItem } from '../../types';

interface SidebarNavItemProps {
  item: NavItem;
  collapsed: boolean;
  isActive: boolean;
  currentTab: string | null;
  pathname: string;
  onNavClick: () => void;
  t: (key: string) => string;
}

export const SidebarNavItem: React.FC<SidebarNavItemProps> = ({
  item, collapsed, isActive, onNavClick, t,
}) => {
  const Icon = item.icon;

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
          onNavClick();
        }
      }}
      className={clsx(
        'group relative flex items-center gap-2.5 rounded-lg transition-all duration-200 border',
        collapsed
          ? 'w-9 h-9 justify-center mx-auto'
          : 'px-2.5 py-2 mx-2 xl:px-3.5 xl:py-2.5 xl:mx-3',
        isActive
          ? 'text-accent bg-accent-soft/80 shadow-[0_0_12px_var(--color-accent-glow)] border-accent/15'
          : 'text-text-2 hover:text-text-1 hover:bg-surface-2/40 border-transparent',
      )}
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
