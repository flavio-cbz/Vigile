import React, { useState, useEffect } from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Cpu } from 'lucide-react';
import { api } from '../../hooks/useApi';
import { useLocale } from '../../i18n';
import { ChartSkeleton } from '../ui/CardSkeleton';
import type { Node } from '../../store/nodeStore';

interface Snapshot {
  collected_at: number;
  cpu_percent: number;
  mem_percent: number;
  disk_percent: number;
}

interface NodeStatsResponse {
  node_id: string;
  snapshots: Snapshot[];
}

interface TrendChartProps {
  nodes: Node[];
}

export const TrendChart: React.FC<TrendChartProps> = ({ nodes }) => {
  const { t } = useLocale();
  const onlineNodes = nodes.filter((n) => n.online);

  const [selectedNodeId, setSelectedNodeId] = useState<string>('');
  const [metric, setMetric] = useState<'cpu' | 'ram' | 'disk'>('cpu');
  const [period, setPeriod] = useState<'24h' | '7d'>('24h');
  const [data, setData] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  useEffect(() => {
    if (onlineNodes.length > 0 && !selectedNodeId) {
      setSelectedNodeId(onlineNodes[0].id);
    }
  }, [onlineNodes, selectedNodeId]);

  useEffect(() => {
    if (!selectedNodeId) return;

    const fetchStats = async () => {
      setIsLoading(true);
      try {
        const limit = period === '24h' ? 24 : 100;
        const res = await api<NodeStatsResponse>(
          `/api/nodes/${selectedNodeId}/stats?limit=${limit}`
        );
        if (res && res.snapshots) {
          // Sort ascending by time
          const sorted = [...res.snapshots].sort((a, b) => a.collected_at - b.collected_at);
          const chartData = sorted.map((s) => ({
            time: new Date(s.collected_at * 1000).toLocaleTimeString('fr-FR', {
              hour: '2-digit',
              minute: '2-digit',
              ...(period === '7d' ? { day: 'numeric', month: 'short' } : {}),
            }),
            cpu: Math.round(s.cpu_percent),
            ram: Math.round(s.mem_percent),
            disk: Math.round(s.disk_percent),
          }));
          setData(chartData);
        }
      } catch (err) {
        console.error('Failed to fetch trend statistics:', err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchStats();
  }, [selectedNodeId, metric, period]);

  if (onlineNodes.length === 0) {
    return null;
  }

  const getMetricColor = () => {
    if (metric === 'cpu') return { stroke: '#6366f1', fill: 'rgba(99, 102, 241, 0.1)' };
    if (metric === 'ram') return { stroke: '#f59e0b', fill: 'rgba(245, 158, 11, 0.1)' };
    return { stroke: '#22c55e', fill: 'rgba(34, 197, 94, 0.1)' };
  };

  const style = getMetricColor();

  return (
    <div className="card w-full flex flex-col gap-4 animate-fade-in">
      {/* Header and filters */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-3">
        <div>
          <h4 className="text-sm font-bold text-ink-primary tracking-wide uppercase flex items-center gap-1.5">
            <Cpu size={16} className="text-accent-primary" />
            {t('swim.trends')}
          </h4>
          <p className="text-[10px] text-ink-secondary mt-0.5">
            Surveillez l'activité des ressources dans le temps.
          </p>
        </div>

        {/* Filters Grid */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Node selector */}
          <select
            value={selectedNodeId}
            onChange={(e) => setSelectedNodeId(e.target.value)}
            className="select text-xs py-1 px-2.5 max-w-[150px]"
          >
            {onlineNodes.map((n) => (
              <option key={n.id} value={n.id}>
                {n.name}
              </option>
            ))}
          </select>

          {/* Metric Selector Buttons */}
          <div className="flex bg-surface-1 border border-border rounded-lg p-0.5">
            <button
              onClick={() => setMetric('cpu')}
              className={`px-2.5 py-1 text-[10px] font-semibold rounded-md transition-colors cursor-pointer ${
                metric === 'cpu' ? 'bg-accent-primary text-ink-primary' : 'text-ink-secondary hover:text-ink-primary'
              }`}
            >
              CPU
            </button>
            <button
              onClick={() => setMetric('ram')}
              className={`px-2.5 py-1 text-[10px] font-semibold rounded-md transition-colors cursor-pointer ${
                metric === 'ram' ? 'bg-warning text-ink-primary' : 'text-ink-secondary hover:text-ink-primary'
              }`}
            >
              RAM
            </button>
            <button
              onClick={() => setMetric('disk')}
              className={`px-2.5 py-1 text-[10px] font-semibold rounded-md transition-colors cursor-pointer ${
                metric === 'disk' ? 'bg-success text-ink-primary' : 'text-ink-secondary hover:text-ink-primary'
              }`}
            >
              Disk
            </button>
          </div>

          {/* Period Selector Buttons */}
          <div className="flex bg-surface-1 border border-border rounded-lg p-0.5">
            <button
              onClick={() => setPeriod('24h')}
              className={`px-2.5 py-1 text-[10px] font-semibold rounded-md transition-colors cursor-pointer ${
                period === '24h' ? 'bg-surface-2 text-ink-primary' : 'text-ink-secondary hover:text-ink-primary'
              }`}
            >
              24h
            </button>
            <button
              onClick={() => setPeriod('7d')}
              className={`px-2.5 py-1 text-[10px] font-semibold rounded-md transition-colors cursor-pointer ${
                period === '7d' ? 'bg-surface-2 text-ink-primary' : 'text-ink-secondary hover:text-ink-primary'
              }`}
            >
              7j
            </button>
          </div>
        </div>
      </div>

      {/* Chart container */}
      <div className="h-[200px] w-full mt-2 relative">
        {isLoading ? (
          <div className="absolute inset-0 flex items-center justify-center bg-surface-0/60 z-10 rounded-lg">
            <ChartSkeleton />
          </div>
        ) : data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-xs text-ink-muted italic">
            {t('dash.empty_state')}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
              <XAxis
                dataKey="time"
                tick={{ fill: 'var(--color-ink-muted)', fontSize: 9 }}
                axisLine={{ stroke: 'var(--color-border)' }}
                tickLine={false}
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fill: 'var(--color-ink-muted)', fontSize: 9 }}
                axisLine={{ stroke: 'var(--color-border)' }}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--color-surface-1)',
                  borderColor: 'var(--color-border)',
                  color: 'var(--color-ink-primary)',
                  fontSize: 11,
                  borderRadius: 'var(--radius-md)',
                }}
              />
              <Area
                type="monotone"
                dataKey={metric}
                stroke={style.stroke}
                fill={style.fill}
                strokeWidth={1.5}
                activeDot={{ r: 4 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
};
