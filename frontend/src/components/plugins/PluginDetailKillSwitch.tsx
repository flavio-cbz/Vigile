import React, { useState } from 'react';
import { Shield, AlertTriangle, RefreshCw } from 'lucide-react';
import { clsx } from 'clsx';
import { Spinner } from '../primitives/Spinner';
import type { PluginInfo, PluginKillSwitch } from '../../hooks/usePluginsData';

interface PluginDetailKillSwitchProps {
  plugin: PluginInfo;
  isAdmin: boolean;
  disabling: boolean;
  enabling: boolean;
  onDisable: (pluginId: string, hard: boolean, reason: string) => Promise<void>;
  onEnable: (pluginId: string) => Promise<void>;
  onFetchPlugins: () => Promise<void>;
  t: (key: string, params?: Record<string, string>) => string;
}

export const PluginDetailKillSwitch: React.FC<PluginDetailKillSwitchProps> = ({
  plugin, isAdmin, disabling, enabling, onDisable, onEnable, onFetchPlugins, t,
}) => {
  const [showReasonDialog, setShowReasonDialog] = useState(false);
  const [reasonInput, setReasonInput] = useState('');

  if (!isAdmin) return null;

  const ks: PluginKillSwitch | null = plugin.kill_switch || null;

  const handleSoftDisable = () => {
    onDisable(plugin.id, false, 'Maintenance');
  };

  const handleHardDisable = () => {
    if (!reasonInput.trim()) return;
    onDisable(plugin.id, true, reasonInput.trim());
    setShowReasonDialog(false);
    setReasonInput('');
  };

  const handleEnable = () => {
    onEnable(plugin.id);
  };

  const handleRefresh = () => {
    onFetchPlugins();
  };

  return (
    <div className="space-y-4">
      {/* Status display */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={clsx(
            'w-8 h-8 rounded-lg flex items-center justify-center',
            ks
              ? 'bg-severity-critical/10'
              : 'bg-severity-ok/10',
          )}>
            {ks ? (
              <AlertTriangle className="w-4 h-4 text-severity-critical" />
            ) : (
              <Shield className="w-4 h-4 text-severity-ok" />
            )}
          </div>
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-text-3">
              {t('plugins.kill_switch.title')}
            </h4>
            {ks ? (
              <p className="text-[10px] text-text-2 mt-0.5">
                {ks.hard
                  ? t('plugins.kill_switch.hard')
                  : t('plugins.kill_switch.maintenance')}
                {ks.reason && (
                  <span> — {ks.reason}</span>
                )}
              </p>
            ) : (
              <p className="text-[10px] text-text-2 mt-0.5">
                Plugin is operating normally
              </p>
            )}
          </div>
        </div>
        <button
          onClick={handleRefresh}
          className="p-1 rounded hover:bg-surface-3 transition-colors cursor-pointer text-text-3 hover:text-text-1"
          title="Refresh"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Kill switch details */}
      {ks && (
        <div className="text-[10px] text-text-3 space-y-0.5">
          {ks.reason && (
            <div>
              <span className="font-bold">{t('plugins.kill_switch.reason')}</span>: {ks.reason}
            </div>
          )}
          {ks.user_id && (
            <div>
              <span className="font-bold">{t('plugins.kill_switch.user')}</span>: {ks.user_id}
            </div>
          )}
          {ks.disabled_at && (
            <div>
              <span className="font-bold">{ks.disabled_at ? t('plugins.kill_switch.enabled_at') : ''}</span>
              : {new Date(ks.disabled_at * 1000).toLocaleString()}
            </div>
          )}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2">
        {ks ? (
          <button
            onClick={handleEnable}
            disabled={enabling}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border-strong/30 bg-surface-2 hover:bg-surface-hover/80 text-text-1 font-mono text-[10px] font-bold uppercase tracking-wider transition-colors cursor-pointer disabled:opacity-50"
          >
            {enabling ? <Spinner size="sm" /> : null}
            {t('plugins.kill_switch.enable')}
          </button>
        ) : (
          <>
            <button
              onClick={handleSoftDisable}
              disabled={disabling}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-severity-warning/30 bg-severity-warning/10 hover:bg-severity-warning/20 text-severity-warning font-mono text-[10px] font-bold uppercase tracking-wider transition-colors cursor-pointer disabled:opacity-50"
            >
              {disabling ? <Spinner size="sm" /> : null}
              {t('plugins.kill_switch.disable_maintenance')}
            </button>
            <button
              onClick={() => setShowReasonDialog(true)}
              disabled={disabling}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-severity-critical/30 bg-severity-critical/10 hover:bg-severity-critical/20 text-severity-critical font-mono text-[10px] font-bold uppercase tracking-wider transition-colors cursor-pointer disabled:opacity-50"
            >
              {t('plugins.kill_switch.disable_hard')}
            </button>
          </>
        )}
      </div>

      {/* Hard disable reason dialog */}
      {showReasonDialog && (
        <div className="p-3 bg-surface-2 border border-border-strong/20 rounded-lg space-y-3">
          <p className="text-[10px] text-text-2">
            {t('plugins.kill_switch.reason_required')}
          </p>
          <input
            type="text"
            value={reasonInput}
            onChange={(e) => setReasonInput(e.target.value)}
            placeholder={t('plugins.kill_switch.reason_placeholder')}
            className="w-full px-2 py-1.5 text-xs bg-surface-3 border border-border-strong/30 rounded text-text-1 placeholder:text-text-3 focus:outline-none focus:border-accent/50"
          />
          <div className="flex gap-2">
            <button
              onClick={handleHardDisable}
              disabled={!reasonInput.trim() || disabling}
              className="px-3 py-1 rounded bg-accent text-bg font-mono text-[10px] font-bold uppercase tracking-wider cursor-pointer disabled:opacity-50"
            >
              {disabling ? <Spinner size="sm" /> : null}
              {t('plugins.kill_switch.disable_hard')}
            </button>
            <button
              onClick={() => {
                setShowReasonDialog(false);
                setReasonInput('');
              }}
              className="px-3 py-1 rounded bg-surface border border-border-strong/30 text-text-2 font-mono text-[10px] font-bold uppercase tracking-wider cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
