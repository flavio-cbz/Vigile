import React from 'react';
import { Shield, AlertTriangle } from 'lucide-react';
import { clsx } from 'clsx';
import type { PluginKillSwitch } from '../../hooks/usePluginsData';

interface KillSwitchBadgeProps {
  killSwitch: PluginKillSwitch | null | undefined;
  t: (key: string, params?: Record<string, string>) => string;
}

export const KillSwitchBadge: React.FC<KillSwitchBadgeProps> = ({ killSwitch, t }) => {
  if (!killSwitch) return null;

  const isHard = killSwitch.hard;
  const mode = isHard ? t('plugins.kill_switch.hard') : t('plugins.kill_switch.maintenance');
  const Icon = isHard ? AlertTriangle : Shield;

  return (
    <div
      className={clsx(
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[9px] font-bold uppercase tracking-wider',
        isHard
          ? 'bg-severity-critical/10 text-severity-critical border border-severity-critical/20'
          : 'bg-severity-warning/10 text-severity-warning border border-severity-warning/20',
      )}
      title={t('plugins.kill_switch.disabled_tooltip')}
    >
      <Icon className="w-3 h-3" />
      {mode}
    </div>
  );
};
