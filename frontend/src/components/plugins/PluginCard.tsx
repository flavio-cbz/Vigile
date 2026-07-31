import React from 'react';
import { FileCode, ToggleLeft, ToggleRight, Trash2 } from 'lucide-react';
import { Spinner } from '../primitives/Spinner';
import { clsx } from 'clsx';

interface PluginCardProps {
  plugin: {
    id: string;
    name: string;
    description?: string;
    module?: string;
    path?: string;
    hooks: string[];
    error?: string;
    enabled?: boolean;
  };
  isLoaded: boolean;
  isAdmin: boolean;
  toggling: boolean;
  deleting: boolean;
  onSelect: () => void;
  onToggle: (e: React.MouseEvent) => void;
  onDelete: (e: React.MouseEvent) => void;
  t: (key: string, params?: Record<string, string>) => string;
}

export const PluginCard: React.FC<PluginCardProps> = ({
  plugin, isLoaded, isAdmin, toggling, deleting,
  onSelect, onToggle, onDelete, t,
}) => {
  return (
    <div
      onClick={onSelect}
      className={clsx(
        'bg-surface-2 border rounded-xl p-4 transition-all duration-200 cursor-pointer hover:-translate-y-0.5 hover:shadow-md',
        isLoaded
          ? 'border-accent/20 hover:border-accent/30'
          : 'border-border-strong/20 hover:border-border-strong/40'
      )}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className={clsx(
            'w-8 h-8 rounded-lg flex items-center justify-center shrink-0',
            isLoaded ? 'bg-accent/10' : 'bg-surface-3'
          )}>
            <FileCode className={clsx(
              'w-4 h-4',
              isLoaded ? 'text-accent' : 'text-text-3'
            )} />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-text-1 truncate">{plugin.name}</h3>
            <span className={clsx(
              'text-[9px] font-mono font-bold uppercase',
              isLoaded ? 'text-severity-ok' : plugin.error ? 'text-severity-critical' : 'text-text-3'
            )}>
              {isLoaded ? t('plugins.loaded') : plugin.error ? t('plugins.error') || 'ERROR' : t('plugins.unloaded')}
            </span>
          </div>
        </div>
        {isAdmin && (
          <>
            <button
              onClick={onToggle}
              disabled={toggling}
              className="shrink-0 p-1 rounded hover:bg-surface-3 transition-colors cursor-pointer disabled:opacity-50"
              title={isLoaded ? t('plugins.deactivate') : t('plugins.activate')}
            >
              {toggling ? (
                <Spinner size="sm" />
              ) : isLoaded ? (
                <ToggleRight className="w-4 h-4 text-accent" />
              ) : (
                <ToggleLeft className="w-4 h-4 text-text-3" />
              )}
            </button>
            <button
              onClick={onDelete}
              disabled={deleting}
              className="shrink-0 p-1 rounded hover:bg-severity-critical/15 transition-colors cursor-pointer disabled:opacity-50 text-text-3 hover:text-severity-critical"
              title="Uninstall"
            >
              {deleting ? <Spinner size="sm" /> : <Trash2 className="w-4 h-4" />}
            </button>
          </>
        )}
      </div>

      {plugin.description && (
        <p className="text-[10px] text-text-2 mb-2 line-clamp-2 leading-relaxed">
          {plugin.description}
        </p>
      )}

      <div className="mb-2">
        <code className="text-[9px] font-mono text-text-3 bg-surface-3 px-1.5 py-0.5 rounded truncate block">
          {plugin.module || plugin.path}
        </code>
      </div>

      {plugin.hooks && plugin.hooks.length > 0 && (
        <div className="space-y-1">
          <span className="text-[9px] font-bold uppercase tracking-wider text-text-3">{t('plugins.hooks_label')}</span>
          <div className="flex flex-wrap gap-1">
            {plugin.hooks.map((hook) => (
              <span
                key={hook}
                className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-accent/5 text-accent border border-accent/10"
              >
                {hook}
              </span>
            ))}
          </div>
        </div>
      )}

      {plugin.error && (
        <div className="mt-2 p-2 bg-severity-critical/10 border border-severity-critical/20 rounded-lg">
          <p className="text-[10px] text-severity-critical font-mono">{plugin.error}</p>
        </div>
      )}
    </div>
  );
};
