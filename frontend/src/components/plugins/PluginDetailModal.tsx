import React from 'react';
import { FileCode, X } from 'lucide-react';
import { clsx } from 'clsx';
import { PluginConfigForm } from '../../plugins/PluginConfigForm';
import type { PluginInfo } from '../../pages/PluginsPage';

interface PluginDetailModalProps {
  plugin: PluginInfo;
  onClose: () => void;
  onSaveConfig: (pluginId: string, configData: Record<string, unknown>) => Promise<void>;
  t: (key: string, params?: Record<string, string>) => string;
}

export const PluginDetailModal: React.FC<PluginDetailModalProps> = ({
  plugin, onClose, onSaveConfig, t,
}) => {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg bg-surface-2 border border-border-strong/20 rounded-2xl shadow-xl overflow-hidden animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-5 border-b border-border-strong/10 bg-surface-3/50">
          <div className="flex items-center gap-3">
            <div className={clsx(
              'w-10 h-10 rounded-xl flex items-center justify-center',
              plugin.loaded ? 'bg-accent/15' : 'bg-surface-3'
            )}>
              <FileCode className={clsx(
                'w-5 h-5',
                plugin.loaded ? 'text-accent' : 'text-text-3'
              )} />
            </div>
            <div>
              <h2 className="text-sm font-bold text-text-1">{plugin.name}</h2>
              <div className="flex items-center gap-2 mt-0.5">
                {plugin.version && (
                  <span className="text-[10px] font-mono font-bold text-text-3">v{plugin.version}</span>
                )}
                <span className={clsx(
                  'text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-full',
                  plugin.loaded ? 'bg-severity-ok/10 text-severity-ok' : 'bg-surface-3 text-text-3'
                )}>
                  {plugin.loaded ? t('plugins.loaded') : t('plugins.unloaded')}
                </span>
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-surface-3 text-text-3 hover:text-text-1 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6 space-y-5 max-h-[60vh] overflow-y-auto">
          <div>
            <h4 className="text-[10px] font-bold uppercase tracking-wider text-text-3 mb-1.5">Description</h4>
            <p className="text-xs text-text-2 leading-relaxed whitespace-pre-line">
              {plugin.description || "Aucune description fournie pour cette extension."}
            </p>
          </div>

          {plugin.schema && Object.keys(plugin.schema).length > 0 && (
            <div>
              <PluginConfigForm
                schema={plugin.schema}
                initialConfig={plugin.config || {}}
                onSubmit={(cfg) => onSaveConfig(plugin.id, cfg)}
                onCancel={onClose}
              />
            </div>
          )}

          {plugin.hooks && plugin.hooks.length > 0 && (
            <div>
              <h4 className="text-[10px] font-bold uppercase tracking-wider text-text-3 mb-2">Points d'ancrage (Hooks)</h4>
              <div className="flex flex-wrap gap-1.5">
                {plugin.hooks.map((hook) => (
                  <span
                    key={hook}
                    className="text-[9px] font-mono px-2 py-0.5 rounded-md bg-accent/5 text-accent border border-accent/10"
                  >
                    {hook}
                  </span>
                ))}
              </div>
            </div>
          )}

          {(plugin.path || plugin.module) && (
            <div>
              <h4 className="text-[10px] font-bold uppercase tracking-wider text-text-3 mb-1.5">Module / Chemin</h4>
              <code className="text-[10px] font-mono text-text-3 bg-surface-3 px-2 py-1 rounded block truncate" title={plugin.path || plugin.module}>
                {plugin.module || plugin.path}
              </code>
            </div>
          )}
        </div>

        <div className="flex justify-end p-4 border-t border-border-strong/10 bg-surface-3/30">
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-[10px] font-bold uppercase tracking-wider bg-surface border border-border-strong/20 hover:border-accent/30 text-text-2 hover:text-text-1 rounded-lg transition-colors cursor-pointer"
          >
            Fermer
          </button>
        </div>
      </div>
    </div>
  );
};
