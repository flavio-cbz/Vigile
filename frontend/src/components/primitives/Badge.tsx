import React from 'react';
import { useLocale } from '../../i18n';

type BadgeSeverity = 'ok' | 'warning' | 'critical' | 'offline' | 'pending' | 'info';

interface BadgeProps {
  severity: BadgeSeverity;
  label?: string;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({ severity, label, className = '' }) => {
  const { t } = useLocale();
  const getStyles = () => {
    switch (severity) {
      case 'ok':
        return 'bg-severity-ok/10 text-severity-ok border-severity-ok/20';
      case 'warning':
        return 'bg-severity-warning/10 text-severity-warning border-severity-warning/20';
      case 'critical':
        return 'bg-severity-critical/10 text-severity-critical border-severity-critical/20 animate-pulse';
      case 'offline':
        return 'bg-text-3/10 text-text-3 border-text-3/20';
      case 'info':
        return 'bg-severity-info/10 text-severity-info border-severity-info/20';
      case 'pending':
      default:
        return 'bg-accent/10 text-accent border-accent/20';
    }
  };

  const getLabel = () => {
    if (label) return label;
    switch (severity) {
      case 'ok':
        return t('card.stable');
      case 'warning':
        return t('card.attention');
      case 'critical':
        return t('card.critical');
      case 'offline':
        return t('card.outage');
      case 'info':
        return t('card.info');
      case 'pending':
        return t('card.pending');
    }
  };

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase border font-interface whitespace-nowrap ${getStyles()} ${className}`}
    >
      {getLabel()}
    </span>
  );
};
