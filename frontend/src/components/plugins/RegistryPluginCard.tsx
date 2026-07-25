import React from 'react';
import { FileCode, Download } from 'lucide-react';
import { Spinner } from '../primitives/Spinner';
import { clsx } from 'clsx';

interface RegistryPluginCardProps {
  plugin: {
    id: string;
    name: string;
    description: string;
    author: string;
    version: string;
  };
  isInstalled: boolean;
  isAdmin: boolean;
  isInstalling: boolean;
  onSelect: () => void;
  onInstall: (e: React.MouseEvent) => void;
  t: (key: string, params?: Record<string, string>) => string;
}

export const RegistryPluginCard: React.FC<RegistryPluginCardProps> = ({
  plugin, isInstalled, isAdmin, isInstalling,
  onSelect, onInstall, t,
}) => {
  return (
    <div
      onClick={onSelect}
      className={clsx(
        'bg-surface-2 border rounded-xl p-4 flex flex-col justify-between transition-all duration-200 cursor-pointer hover:-translate-y-0.5 hover:shadow-md',
        isInstalled
          ? 'border-border-strong/10 opacity-70'
          : 'border-border-strong/20 hover:border-border-strong/40'
      )}
    >
      <div>
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-surface-3 shrink-0">
              <FileCode className="w-4 h-4 text-text-3" />
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-bold text-text-1 truncate">{plugin.name}</h3>
              <span className="text-[9px] font-mono font-bold text-text-3 uppercase">
                {t('plugins.registry.version')}: {plugin.version}
              </span>
            </div>
          </div>
        </div>

        <p className="text-xs text-text-2 mb-4 line-clamp-3">
          {plugin.description}
        </p>

        <div className="space-y-1 text-[10px] text-text-3 font-medium mb-4">
          <div>
            <span className="font-bold uppercase tracking-wider text-[9px] block text-text-3 mb-0.5">
              {t('plugins.registry.author')}
            </span>
            <span className="text-text-2">{plugin.author}</span>
          </div>
        </div>
      </div>

      <div>
        {isInstalled ? (
          <button
            disabled
            className="w-full py-1.5 px-3 rounded-lg text-[10px] font-bold uppercase tracking-wider bg-surface border border-border-strong/20 text-text-3 cursor-not-allowed text-center"
          >
            {t('plugins.registry.installed')}
          </button>
        ) : (
          <button
            onClick={onInstall}
            disabled={!isAdmin || isInstalling}
            className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg text-[10px] font-bold uppercase tracking-wider bg-accent hover:bg-accent-hover text-text-1 transition-colors disabled:opacity-50 cursor-pointer"
          >
            {isInstalling ? (
              <>
                <Spinner size="sm" />
                {t('plugins.registry.installing')}
              </>
            ) : (
              <>
                <Download className="w-3 h-3" />
                {t('plugins.registry.install')}
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
};
