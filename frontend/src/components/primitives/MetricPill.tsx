import React from 'react';
import { Clock } from 'lucide-react';

interface MetricPillProps {
  cpu?: number | null;
  mem?: number | null;
  disk?: number | null;
  uptime?: number | null;
  text?: string;
  className?: string;
}

const severityColor = (pct: number): string => {
  if (pct >= 85) return 'var(--severity-critical)';
  if (pct >= 70) return 'var(--severity-warning)';
  return 'var(--accent)';
};

const MiniGauge: React.FC<{ label: string; value: number }> = ({ label, value }) => {
  const display = Number.isInteger(value) ? `${value}%` : `${value.toFixed(1)}%`;
  return (
    <div className="flex items-center gap-1.5 min-w-0">
      <span className="text-[9px] font-interface font-bold uppercase tracking-wider text-text-3 shrink-0">
        {label}
      </span>
      <div className="w-12 h-1.5 bg-surface-2 rounded-full overflow-hidden border border-border shrink-0">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${Math.min(100, Math.max(0, value))}%`,
            backgroundColor: severityColor(value),
          }}
        />
      </div>
      <span className="text-[9px] font-mono font-semibold text-text-2 tabular-nums shrink-0">
        {display}
      </span>
    </div>
  );
};

const formatUptime = (seconds: number): string => {
  const days = Math.floor(seconds / (24 * 3600));
  if (days > 0) return `${days}j`;
  const hours = Math.floor(seconds / 3600);
  return `${hours}h`;
};

export const MetricPill: React.FC<MetricPillProps> = ({
  cpu,
  mem,
  disk,
  uptime,
  text,
  className = '',
}) => {
  // Legacy text-only mode: preserve original behavior
  if (text) {
    return (
      <span
        className={`inline-flex items-center px-2 py-0.5 rounded bg-surface-2 border border-border text-xs font-medium font-mono text-text-2 tracking-wide ${className}`}
      >
        {text}
      </span>
    );
  }

  const hasMetrics = cpu != null || mem != null || disk != null;
  const hasUptime = uptime != null;

  if (!hasMetrics && !hasUptime) return null;

  return (
    <span
      className={`inline-flex items-center gap-2.5 px-2 py-1 rounded bg-surface-2 border border-border text-xs font-mono ${className}`}
    >
      {cpu != null && <MiniGauge label="CPU" value={cpu} />}
      {mem != null && <MiniGauge label="RAM" value={mem} />}
      {disk != null && <MiniGauge label="DISK" value={disk} />}
      {hasUptime && (
        <span className="inline-flex items-center gap-1 text-text-3 shrink-0">
          <Clock className="w-3 h-3" />
          <span className="text-[9px] font-semibold tabular-nums">{formatUptime(uptime!)}</span>
        </span>
      )}
    </span>
  );
};
