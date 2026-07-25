import React from 'react';
import { ShieldCheck } from 'lucide-react';
import { useLocale } from '../../i18n';
import type { SystemSettingsResponse } from './types';

interface SecuritySettingsTabProps {
  settings: SystemSettingsResponse;
}

const formatDuration = (seconds: number): string => {
  if (seconds >= 86400) {
    const days = Math.round(seconds / 86400);
    return `${days} jour${days > 1 ? 's' : ''}`;
  }
  if (seconds >= 3600) {
    const hours = Math.round(seconds / 3600);
    return `${hours} heure${hours > 1 ? 's' : ''}`;
  }
  if (seconds >= 60) {
    const mins = Math.round(seconds / 60);
    return `${mins} minute${mins > 1 ? 's' : ''}`;
  }
  return `${seconds} secondes`;
};

export const SecuritySettingsTab: React.FC<SecuritySettingsTabProps> = ({ settings }) => {
  const { t } = useLocale();

  return (
    <div className="p-5 border border-border rounded-xl bg-surface shadow space-y-4">
      <h3 className="text-xs font-bold text-text-1 uppercase tracking-wider flex items-center gap-2 border-b border-border pb-2 font-interface">
        <ShieldCheck className="w-4 h-4 text-accent" />
        <span>{t('settings.sessions_security')}</span>
      </h3>
      <div className="space-y-3 text-xs">
        <div className="flex justify-between items-center py-1 border-b border-border/40">
          <span className="text-text-3">{t('settings.enforce_https')}</span>
          <span className={`font-bold ${settings.enforce_https ? 'text-severity-ok' : 'text-severity-warning'}`}>
            {settings.enforce_https ? t('settings.active') : t('settings.inactive')}
          </span>
        </div>
        <div className="flex justify-between items-center py-1 border-b border-border/40">
          <span className="text-text-3">{t('settings.jwt_signature')}</span>
          <span className="font-mono text-text-1 font-semibold">{settings.jwt_algorithm}</span>
        </div>
        <div className="flex justify-between items-center py-1 border-b border-border/40">
          <span className="text-text-3">{t('settings.access_ttl')}</span>
          <span className="font-mono text-text-1 font-semibold">{formatDuration(settings.jwt_access_token_ttl)}</span>
        </div>
        <div className="flex justify-between items-center py-1">
          <span className="text-text-3">{t('settings.refresh_ttl')}</span>
          <span className="font-mono text-text-1 font-semibold">{formatDuration(settings.jwt_refresh_token_ttl)}</span>
        </div>
      </div>
    </div>
  );
};
