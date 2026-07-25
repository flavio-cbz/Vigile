import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router';
import { useLayoutStore } from '../../store/layoutStore';
import { useLocale } from '../../i18n';
import { useUiStore } from '../../store/uiStore';
import {
  LayoutDashboard,
  CheckSquare,
  Activity,
  Puzzle,
  MessageSquareCode,
  Bot,
  Search,
  Command,
} from 'lucide-react';

interface CommandItem {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  action: () => void;
}

export const CommandPalette: React.FC = () => {
  const { t } = useLocale();
  const [search, setSearch] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const isOpen = useLayoutStore((s) => s.paletteOpen);
  const setPaletteOpen = useLayoutStore((s) => s.setPaletteOpen);
  const openCopilot = useUiStore((s) => s.openCopilot);
  const closeCopilot = useUiStore((s) => s.closeCopilot);

  const closePalette = () => {
    setPaletteOpen(false);
    setSearch('');
    setSelectedIndex(0);
    closeCopilot();
  };

  const commands: CommandItem[] = useMemo(
    () => [
      { id: 'dashboard', label: t('ui.cmd_dashboard'), icon: LayoutDashboard, action: () => navigate('/') },
      { id: 'proposals', label: t('ui.cmd_proposals'), icon: CheckSquare, action: () => navigate('/proposals') },
      { id: 'audit', label: t('ui.cmd_audit'), icon: Activity, action: () => navigate('/audit') },
      { id: 'plugins', label: t('ui.cmd_plugins'), icon: Puzzle, action: () => navigate('/plugins') },
      { id: 'chat', label: t('ui.cmd_chat'), icon: MessageSquareCode, action: () => navigate('/chat') },
      { id: 'copilot', label: t('ui.cmd_toggle_copilot'), icon: Bot, action: () => openCopilot({ trigger: 'manual' }) },
    ],
    [navigate, openCopilot, t],
  );

  const filteredCommands = useMemo(
    () => commands.filter((cmd) => cmd.label.toLowerCase().includes(search.toLowerCase())),
    [commands, search],
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setPaletteOpen(!isOpen);
      }
      if (e.key === 'Escape' && isOpen) {
        e.preventDefault();
        closePalette();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  useEffect(() => {
    if (isOpen) {
      const raf = requestAnimationFrame(() => inputRef.current?.focus());
      return () => cancelAnimationFrame(raf);
    }
  }, [isOpen]);

  useEffect(() => {
    return () => {
      useUiStore.getState().closeCopilot();
    };
  }, [navigate]);

  const handlePanelKeyDown = (e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex((prev) => (prev < filteredCommands.length - 1 ? prev + 1 : 0));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex((prev) => (prev > 0 ? prev - 1 : filteredCommands.length - 1));
        break;
      case 'Enter':
        e.preventDefault();
        if (filteredCommands[selectedIndex]) {
          filteredCommands[selectedIndex].action();
          closePalette();
        }
        break;
      case 'Escape':
        e.preventDefault();
        closePalette();
        break;
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/60 backdrop-blur-sm animate-fade-in"
      onClick={closePalette}
    >
      <div
        className="w-full max-w-lg bg-surface-alt border border-border-strong rounded-lg shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handlePanelKeyDown}
      >
        <div className="flex items-center gap-3 px-4 border-b border-border-custom">
          <Search className="w-4 h-4 text-ink-muted shrink-0" />
          <input
            ref={inputRef}
            type="text"
            placeholder={t('ui.command_placeholder')}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setSelectedIndex(0);
            }}
            className="flex-1 bg-transparent border-none outline-none py-4 text-sm text-ink placeholder-ink-dim font-mono"
          />
          <kbd className="hidden sm:inline-flex items-center gap-1 px-1.5 py-0.5 text-[0.625rem] font-bold text-ink-muted bg-surface border border-border-custom rounded">
            <Command className="w-2.5 h-2.5" />
            K
          </kbd>
        </div>

        <div className="max-h-80 overflow-y-auto py-2">
          {filteredCommands.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-ink-muted font-mono">
              {t('ui.command_no_results')}
            </div>
          ) : (
            filteredCommands.map((cmd, index) => {
              const Icon = cmd.icon;
              const isSelected = index === selectedIndex;

              return (
                <button
                  key={cmd.id}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors duration-100 ${
                    isSelected
                      ? 'bg-accent-soft text-accent-custom'
                      : 'text-ink hover:bg-surface-hover hover:text-ink'
                  }`}
                  onClick={() => {
                    cmd.action();
                    closePalette();
                  }}
                  onMouseEnter={() => setSelectedIndex(index)}
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  <span className="flex-1 text-sm font-medium">{cmd.label}</span>
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
