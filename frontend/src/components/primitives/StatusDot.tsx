import React from 'react';

interface StatusDotProps {
  state: string;
  className?: string;
}

export const StatusDot: React.FC<StatusDotProps> = ({ state, className = '' }) => {
  const getColors = () => {
    switch (state.toLowerCase()) {
      case 'connected':
        return {
          bg: 'bg-severity-ok',
          pulse: 'bg-severity-ok/40',
          shouldPulse: true,
        };
      case 'enrolling':
      case 'reconnecting':
        return {
          bg: 'bg-severity-warning',
          pulse: 'bg-severity-warning/40',
          shouldPulse: true,
        };
      case 'lost':
      case 'critical':
        return {
          bg: 'bg-severity-critical',
          pulse: 'bg-severity-critical/40',
          shouldPulse: true,
        };
      case 'pending':
        return {
          bg: 'bg-accent',
          pulse: 'bg-accent/40',
          shouldPulse: false,
        };
      case 'stale':
      case 'revoked':
      default:
        return {
          bg: 'bg-text-3',
          shouldPulse: false,
        };
    }
  };

  const { bg, pulse, shouldPulse } = getColors();

  return (
    <span className={`relative inline-flex h-2.5 w-2.5 shrink-0 ${className}`}>
      {shouldPulse && (
        <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${pulse}`} />
      )}
      <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${bg}`} />
    </span>
  );
};
