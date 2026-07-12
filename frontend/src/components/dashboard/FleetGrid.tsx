import React from 'react';
import { useLocale } from '../../i18n';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { Node } from '../../store/nodeStore';
import type { InsightItem } from '../../store/uiStore';
import { formatUptime } from '../../utils/formatTime';

export interface FleetMetrics {
  cpu?: number;
  mem?: number;
  disk?: number;
  uptime?: number;
}

interface FleetGridProps {
  nodes: Node[];
  bulkStatus: Record<string, FleetMetrics>;
  insightsByNode?: Record<string, InsightItem[]>;
  onNodeClick?: (nodeId: string) => void;
}

type Trend = 'up' | 'down' | 'stable';
type Severity = 'critical' | 'warning' | 'ok' | 'offline';

interface Cell {
  node: Node;
  metrics: FleetMetrics | undefined;
  severity: Severity;
  displayValue: string;
  displayLabel: string;
  trend: Trend;
}

const resolveInsightSeverity = (insights?: InsightItem[]): Severity => {
  if (!insights || insights.length === 0) return 'ok';
  const order: Record<string, number> = { critical: 4, offline: 3, warning: 2, info: 1, ok: 0 };
  const top = [...insights].sort(
    (a, b) => (order[b.severity] ?? 0) - (order[a.severity] ?? 0)
  )[0];
  if (!top) return 'ok';
  if (top.severity === 'critical') return 'critical';
  if (top.severity === 'warning') return 'warning';
  if (top.severity === 'offline') return 'offline';
  return 'ok';
};

const pickMetric = (metrics?: FleetMetrics): {
  label: string;
  value: string;
  trend: Trend;
  overloaded: boolean;
} => {
  if (!metrics) {
    return { label: 'CPU', value: '—', trend: 'stable', overloaded: false };
  }
  const cpu = typeof metrics.cpu === 'number' ? metrics.cpu : null;
  const mem = typeof metrics.mem === 'number' ? metrics.mem : null;
  const disk = typeof metrics.disk === 'number' ? metrics.disk : null;

  const candidates: Array<{ label: string; value: number; threshold: number }> = [];
  if (cpu !== null) candidates.push({ label: 'CPU', value: cpu, threshold: 70 });
  if (mem !== null) candidates.push({ label: 'RAM', value: mem, threshold: 75 });
  if (disk !== null) candidates.push({ label: 'DISK', value: disk, threshold: 80 });

  if (candidates.length === 0) {
    return { label: 'CPU', value: '—', trend: 'stable', overloaded: false };
  }

  const top = candidates.reduce((a, b) => (b.value > a.value ? b : a));
  const trend: Trend =
    top.value > top.threshold + 15 ? 'up' : top.value > top.threshold ? 'stable' : 'stable';

  return {
    label: top.label,
    value: `${Math.round(top.value)}%`,
    trend,
    overloaded: top.value > top.threshold,
  };
};

const severityClasses: Record<Severity, { bg: string; text: string; ring: string }> = {
  ok: {
    bg: 'bg-severity-ok/15 hover:bg-severity-ok/25',
    text: 'text-severity-ok',
    ring: 'ring-severity-ok/30 hover:ring-severity-ok/60',
  },
  warning: {
    bg: 'bg-severity-warning/15 hover:bg-severity-warning/25',
    text: 'text-severity-warning',
    ring: 'ring-severity-warning/40 hover:ring-severity-warning/70',
  },
  critical: {
    bg: 'bg-severity-critical/15 hover:bg-severity-critical/25',
    text: 'text-severity-critical',
    ring: 'ring-severity-critical/40 hover:ring-severity-critical/70',
  },
  offline: {
    bg: 'bg-surface-2/40 hover:bg-surface-2/60',
    text: 'text-text-3',
    ring: 'ring-border/40 hover:ring-border-strong/60',
  },
};

const TrendArrow: React.FC<{ trend: Trend; className?: string }> = ({ trend, className = '' }) => {
  if (trend === 'up') {
    return <TrendingUp className={`w-3.5 h-3.5 ${className}`} />;
  }
  if (trend === 'down') {
    return <TrendingDown className={`w-3.5 h-3.5 ${className}`} />;
  }
  return <Minus className={`w-3.5 h-3.5 ${className}`} />;
};

export const FleetGrid: React.FC<FleetGridProps> = ({
  nodes,
  bulkStatus,
  insightsByNode,
  onNodeClick,
}) => {
  const { t } = useLocale();
  const onlineNodes = nodes.filter((n) => n.online);

  if (onlineNodes.length === 0) {
    return (
      <div className="card border border-dashed border-border bg-surface/40 px-6 py-8 flex flex-col items-center justify-center text-center">
        <span className="text-[10px] font-extrabold font-interface tracking-widest text-text-3 uppercase">
          {t('fleet.empty_title')}
        </span>
        <span className="text-xs text-text-2 mt-2 italic">
          {t('fleet.empty_description')}
        </span>
      </div>
    );
  }

  const cells: Cell[] = onlineNodes.map((node) => {
    const metrics = bulkStatus[node.id];
    const insightSeverity = resolveInsightSeverity(insightsByNode?.[node.id]);
    const severity: Severity = insightSeverity === 'ok' ? 'ok' : insightSeverity;
    const pick = pickMetric(metrics);
    return {
      node,
      metrics,
      severity,
      displayValue: pick.value,
      displayLabel: pick.label,
      trend: pick.trend,
    };
  });

  return (
    <div className="grid grid-cols-3 gap-3 w-full">
      {cells.map((cell) => {
        const tone = severityClasses[cell.severity];
        const handleClick = () => onNodeClick?.(cell.node.id);
        const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
          if (!onNodeClick) return;
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onNodeClick(cell.node.id);
          }
        };
        return (
          <div
            key={cell.node.id}
            role={onNodeClick ? 'button' : undefined}
            tabIndex={onNodeClick ? 0 : undefined}
            onClick={onNodeClick ? handleClick : undefined}
            onKeyDown={handleKeyDown}
            className={`relative aspect-square min-h-[110px] rounded-xl ring-1 ${tone.ring} ${tone.bg} px-3 py-2.5 flex flex-col justify-between transition-all duration-200 cursor-pointer focus:outline-none focus:ring-2`}
          >
            <div className="flex items-center justify-between gap-1">
              <span className="text-[9px] font-extrabold font-interface tracking-widest text-text-3 uppercase truncate">
                {cell.displayLabel}
              </span>
              <TrendArrow trend={cell.trend} className={tone.text} />
            </div>

            <div className="flex flex-col items-start">
              <span className={`font-mono text-2xl font-bold leading-none ${tone.text}`}>
                {cell.displayValue}
              </span>
              <span className="text-[10px] font-interface font-semibold text-text-2 truncate w-full mt-1">
                {cell.node.name}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className={`text-[9px] font-extrabold font-interface tracking-widest uppercase ${tone.text}`}>
                {cell.severity === 'ok' && t('severity.ok')}
                {cell.severity === 'warning' && t('severity.alert')}
                {cell.severity === 'critical' && t('severity.critical')}
                {cell.severity === 'offline' && t('severity.outage')}
              </span>
              <span className="text-[9px] font-mono text-text-3">
                {cell.metrics?.uptime !== undefined ? formatUptime(cell.metrics.uptime) : '—'}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default FleetGrid;
