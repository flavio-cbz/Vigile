import React from 'react';
import { Layers } from 'lucide-react';
import type { LogSourceItemRecord } from './types';
import { useLocale } from '../../i18n';

interface LogSourceBarProps {
  sources: LogSourceItemRecord[];
  activeService: string;
  activePath: string;
  onSelectService: (service: string) => void;
  onSelectPath: (path: string) => void;
  onOpenModal: () => void;
}

export const LogSourceBar: React.FC<LogSourceBarProps> = ({
  sources,
  activeService,
  activePath,
  onSelectService,
  onSelectPath,
  onOpenModal,
}) => {
  const { t } = useLocale();

  const isGlobal = !activeService && !activePath;

  // Preset pinned sources
  const pinnedSources = [
    { id: 'global', name: 'journald (global)', isGlobal: true },
    { id: 'auth', name: 'auth.log', path: '/var/log/auth.log' },
    { id: 'syslog', name: 'syslog', path: '/var/log/syslog' },
    { id: 'dockerd', name: 'docker.service', service: 'docker.service' },
    { id: 'kernel', name: 'kernel (dmesg)', service: '__kernel__' },
  ];

  return (
    <div className="flex flex-wrap items-center justify-between gap-2.5 p-3 bg-surface border border-border rounded-lg font-interface text-xs select-none">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10.5px] font-bold uppercase tracking-wider text-text-3 mr-1">
          {t('node_detail.logs_source_label') || 'Source :'}
        </span>

        {pinnedSources.map((pin) => {
          const isActive = pin.isGlobal
            ? isGlobal
            : (pin.service && activeService === pin.service) || (pin.path && activePath === pin.path);

          return (
            <button
              key={pin.id}
              onClick={() => {
                if (pin.isGlobal) {
                  onSelectService('');
                  onSelectPath('');
                } else if (pin.service) {
                  onSelectPath('');
                  onSelectService(pin.service);
                } else if (pin.path) {
                  onSelectService('');
                  onSelectPath(pin.path);
                }
              }}
              className={`px-2.5 py-1 rounded font-mono text-[11.5px] transition-all cursor-pointer inline-flex items-center gap-1.5 ${
                isActive
                  ? 'bg-accent/15 border border-accent/40 text-accent font-semibold'
                  : 'bg-surface-2 border border-border text-text-2 hover:text-text-1 hover:border-text-3'
              }`}
            >
              <span>{pin.name}</span>
            </button>
          );
        })}

        {/* Active custom source chip if not in presets */}
        {activeService && !pinnedSources.some((p) => p.service === activeService) && (
          <div className="px-2.5 py-1 rounded font-mono text-[11.5px] bg-accent/15 border border-accent/40 text-accent font-semibold inline-flex items-center gap-1.5">
            <span>⚙️ {activeService}</span>
            <button
              onClick={() => onSelectService('')}
              className="text-text-3 hover:text-text-1 ml-1"
            >
              ×
            </button>
          </div>
        )}
        {activePath && !pinnedSources.some((p) => p.path === activePath) && (
          <div className="px-2.5 py-1 rounded font-mono text-[11.5px] bg-accent/15 border border-accent/40 text-accent font-semibold inline-flex items-center gap-1.5">
            <span>📄 {activePath.split('/').pop()}</span>
            <button
              onClick={() => onSelectPath('')}
              className="text-text-3 hover:text-text-1 ml-1"
            >
              ×
            </button>
          </div>
        )}
      </div>

      {/* Button to open Fuzzy Finder Modal */}
      <button
        onClick={onOpenModal}
        className="px-3 py-1.5 rounded bg-surface-2 hover:bg-surface-3 border border-border hover:border-accent/40 text-text-2 hover:text-text-1 font-semibold text-[11.5px] cursor-pointer inline-flex items-center gap-2 transition-all ml-auto"
      >
        <Layers className="w-3.5 h-3.5 text-accent" />
        <span>{t('node_detail.logs_all_sources') || 'Toutes les sources'} ({sources.length || 48})</span>
        <span className="font-mono text-[10px] text-text-3 bg-surface border border-border px-1 py-0.5 rounded">
          S
        </span>
      </button>
    </div>
  );
};
