import React from 'react';

type Severity = 'ok' | 'warning' | 'critical' | 'offline' | 'info';

interface SeverityTagProps {
  severity: Severity;
  className?: string;
}

export const SeverityTag: React.FC<SeverityTagProps> = ({ severity, className = '' }) => {
  const getStyles = () => {
    switch (severity) {
      case 'critical':
        return 'bg-severity-critical/10 text-severity-critical border-severity-critical/20';
      case 'warning':
        return 'bg-severity-warning/10 text-severity-warning border-severity-warning/20';
      case 'info':
        return 'bg-severity-info/10 text-severity-info border-severity-info/20';
      case 'ok':
        return 'bg-severity-ok/10 text-severity-ok border-severity-ok/20';
      case 'offline':
      default:
        return 'bg-text-3/10 text-text-2 border-text-3/20';
    }
  };

  const getLabel = () => {
    switch (severity) {
      case 'critical':
        return 'CRITIQUE';
      case 'warning':
        return 'ATTENTION';
      case 'info':
        return 'INFO';
      case 'ok':
        return 'NORMAL';
      case 'offline':
        return 'HORS-LIGNE';
    }
  };

  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[9px] font-extrabold tracking-widest border font-interface ${getStyles()} ${className}`}>
      <span className={`w-1 h-1 rounded-full bg-current ${severity === 'critical' ? 'animate-ping' : ''}`} />
      {getLabel()}
    </span>
  );
};
