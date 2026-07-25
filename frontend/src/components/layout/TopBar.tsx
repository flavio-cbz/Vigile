import React, { useState, useRef, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router';
import { useAuthStore } from '../../store/authStore';
import { useUiStore } from '../../store/uiStore';
import { useLayoutStore } from '../../store/layoutStore';
import { useNodeStore } from '../../store/nodeStore';
import { NodeSelector } from './NodeSelector';
import { NotifBell } from './NotifBell';
import { useLocale } from '../../i18n';
import { LogOut, Settings, User, Compass, Palette, Search } from 'lucide-react';
import { VigileLogo } from '../ui/VigileLogo';
import { themes, type ThemeKey } from '../../design/themes';

export const TopBar: React.FC = () => {
  const { t } = useLocale();
  const { user, logout } = useAuthStore();
  const { theme, setTheme } = useUiStore();
  const { nodes } = useNodeStore();
  const navigate = useNavigate();
  const location = useLocation();

  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const getPageTitle = () => {
    const path = location.pathname;
    if (path === '/') return t('page_title.dashboard').toUpperCase();
    if (path.startsWith('/nodes/')) return t('page_title.node_detail').toUpperCase();
    if (path === '/proposals') return t('prop_page.title').toUpperCase();
    if (path === '/audit') return t('page_title.audit').toUpperCase();
    if (path === '/settings') return t('settings.system_title').toUpperCase();
    return t('topbar.console');
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const triggerSearch = () => {
    useLayoutStore.getState().setPaletteOpen(true);
  };

  return (
    <header className="h-[var(--topbar-height)] bg-surface/75 backdrop-blur-md border-b border-border-strong/30 flex items-center justify-between px-6 shrink-0 relative z-30 font-interface select-none shadow-[0_4px_20px_var(--shadow-topbar)]">
      <div className="flex items-center gap-6">
        <Link to="/" className="flex items-center gap-2 group md:hidden">
          <VigileLogo className="w-7 h-7 xl:w-8.5 xl:h-8.5" />
        </Link>

        <div className="h-4 w-px bg-border-strong/50 hidden sm:block md:hidden" />

        <div className="hidden sm:flex items-center gap-2">
          <span className="text-[10px] xl:text-[11.5px] font-extrabold tracking-widest text-text-3 uppercase font-mono">
            {t('topbar.console')}
          </span>
          <span className="text-[10px] xl:text-[11.5px] text-text-3 font-mono">/</span>
          <span className="text-[10px] xl:text-[11.5px] font-bold tracking-wider text-accent/90 uppercase font-mono">
            {getPageTitle()}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <button
          onClick={triggerSearch}
          className="hidden md:flex items-center gap-2 px-3 py-1.5 xl:px-4 xl:py-2 rounded-md bg-surface-2/45 border border-border-strong/45 hover:border-accent/50 text-text-2 hover:text-text-1 text-[10px] xl:text-[11.5px] font-medium transition-all duration-200 cursor-pointer shadow-inner"
        >
          <Search className="w-3.5 h-3.5 xl:w-4.5 xl:h-4.5 text-text-3" />
          <span>{t('topbar.search_placeholder')}</span>
        </button>

        <div className="w-px h-4 bg-border-strong/50 hidden md:block" />

        {nodes.length >= 2 && (
          <>
            <NodeSelector />
            <div className="w-px h-4 bg-border-strong/50" />
          </>
        )}

        <nav className="flex items-center gap-1">
          <Link
            to="/"
            className={`p-2 xl:p-2.5 rounded-md hover:bg-surface-2/60 text-text-2 hover:text-text-1 transition-colors ${
              location.pathname === '/' ? 'text-accent bg-accent-muted/15' : ''
            }`}
            title={t("ui.cmd_dashboard")}
          >
            <Compass className="w-4 h-4 xl:w-5 h-5 transition-transform duration-200 hover:rotate-12" />
          </Link>
          <Link
            to="/settings"
            className={`p-2 xl:p-2.5 rounded-md hover:bg-surface-2/60 text-text-2 hover:text-text-1 transition-colors ${
              location.pathname === '/settings' ? 'text-accent bg-accent-muted/15' : ''
            }`}
            title={t("ui.cmd_plugins")}
          >
            <Settings className="w-4 h-4 xl:w-5 h-5 transition-transform duration-300 hover:rotate-45" />
          </Link>
        </nav>

        <div className="w-px h-4 bg-border-strong/50" />

        <NotifBell />

        <div ref={menuRef} className="relative">
          <button
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            className="flex items-center gap-2 cursor-pointer p-1 rounded-md hover:bg-surface-2/60 transition-colors focus:outline-none"
          >
            <div className="w-6.5 h-6.5 xl:w-8 xl:h-8 rounded-full bg-accent-muted/20 border border-accent/25 flex items-center justify-center text-[10px] xl:text-[12px] font-bold text-accent shadow-[0_0_6px_var(--color-accent-glow)]">
              {user?.username?.substring(0, 2).toUpperCase() || <User className="w-3.5 h-3.5 xl:w-4 xl:h-4" />}
            </div>
          </button>

          {isMenuOpen && (
            <div className="absolute right-0 mt-2 w-56 rounded-lg bg-surface-2/95 backdrop-blur-md border border-border-strong/60 shadow-[0_8px_32px_var(--shadow-dropdown)] py-1.5 z-50 animate-fade-in text-xs">
              <div className="px-4 py-2.5 border-b border-border-strong/30">
                <p className="font-bold text-text-1 truncate">{user?.username || t('sidebar.default_username')}</p>
                <p className="text-[9px] font-mono text-accent uppercase tracking-wider mt-0.5 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                  {t('sidebar.role_label', { role: user?.role || 'operator' })}
                </p>
              </div>

              <div className="px-4 py-2.5 border-b border-border-strong/30">
                <p className="text-[10px] font-bold text-text-3 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <Palette className="w-3.5 h-3.5 text-accent" /> {t('topbar.theme_menu')}
                </p>
                <div className="grid grid-cols-2 gap-1.5">
                  {Object.keys(themes).map((t) => {
                    const dotColor =
                      t === 'warm-dark' ? 'bg-[#F59E0B]' :
                      t === 'cool-dark' ? 'bg-[#2dd4bf]' :
                      t === 'gray-dark' ? 'bg-[#8b8698]' :
                      'bg-[#e8650a]';
                    return (
                      <button
                        key={t}
                        onClick={() => setTheme(t as ThemeKey)}
                        className={`flex items-center gap-1.5 px-2 py-1.5 rounded text-[9px] text-left uppercase truncate font-semibold border transition-all duration-150 cursor-pointer ${
                          theme === t
                            ? 'border-accent text-accent bg-accent-muted/20 shadow-[0_0_8px_var(--color-accent-glow)]'
                            : 'border-border-strong/30 text-text-2 hover:bg-surface-3/50'
                        }`}
                      >
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />
                        {t.replace('-', ' ')}
                      </button>
                    );
                  })}
                </div>
              </div>

              <button
                onClick={() => {
                  setIsMenuOpen(false);
                  navigate('/settings');
                }}
                className="w-full flex items-center gap-2 px-4 py-2.5 text-left text-text-2 hover:text-text-1 hover:bg-surface-3/40 transition-colors"
              >
                <Settings className="w-3.5 h-3.5 text-text-3" />
                <span>{t('topbar.settings_menu')}</span>
              </button>

              <div className="h-px bg-border-strong/30 my-1" />

              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-2 px-4 py-2.5 text-left text-severity-critical hover:bg-severity-critical/10 transition-colors font-semibold"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>{t('topbar.logout')}</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
