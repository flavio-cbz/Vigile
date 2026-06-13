import React from 'react';

interface MetricPillProps {
  cpu?: number | null;
  mem?: number | null;
  disk?: number | null;
  uptime?: number | null;
  text?: string;
  className?: string;
}

export const MetricPill: React.FC<MetricPillProps> = ({
  cpu,
  mem,
  disk,
  uptime,
  text,
  className = '',
}) => {
  const formatUptime = (seconds: number) => {
    const days = Math.floor(seconds / (24 * 3600));
    if (days > 0) return `${days}j`;
    const hours = Math.floor(seconds / 3600);
    return `${hours}h`;
  };

  const renderContent = () => {
    if (text) return text;

    const parts: string[] = [];
    if (cpu !== undefined && cpu !== null) parts.push(`CPU ${Math.round(cpu)}%`);
    if (mem !== undefined && mem !== null) parts.push(`RAM ${Math.round(mem)}%`);
    if (disk !== undefined && disk !== null) parts.push(`DISK ${Math.round(disk)}%`);
    if (uptime !== undefined && uptime !== null) parts.push(`UP ${formatUptime(uptime)}`);

    return parts.join(' · ');
  };

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded bg-surface-2 border border-border text-xs font-medium font-mono text-text-2 tracking-wide ${className}`}
    >
      {renderContent()}
    </span>
  );
};
