import React from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
} from 'recharts';
import { Activity, AlertCircle } from 'lucide-react';

/* ── Local block types (T7 may reconcile later) ─────────────────────── */

export interface BlockContext {
  params?: Record<string, string>;
  node_id?: string;
}

export interface ChartCardConfig {
  title: string;
  dataKey: string;
  color: string;
  gradientId: string;
  period: '1h' | '6h' | '24h' | '7d';
}

export interface MetricPoint {
  node_id: string;
  collected_at: number;
  [key: string]: number | string;
}

export interface ChartCardProps {
  context: BlockContext;
  config: ChartCardConfig;
  state: 'idle' | 'busy' | 'error' | 'empty' | 'data';
  data: MetricPoint[];
  error?: string;
  onRetry?: () => void;
}

import { formatXAxis, formatTooltipDate } from './chart-utils';

export const ChartCard: React.FC<ChartCardProps> = ({
  config,
  state,
  data,
  error,
  onRetry,
}) => {
  if (state === 'idle') {
    return (
      <div className="p-5 rounded-xl border border-border-strong/30 bg-surface-2/10 backdrop-blur-xs animate-pulse">
        <div className="h-4 w-40 rounded bg-zinc-800 mb-4" />
        <div className="h-64 rounded bg-zinc-800/50" />
      </div>
    );
  }

  if (state === 'busy') {
    return (
      <div className="flex flex-col items-center justify-center py-20 bg-zinc-900/10 rounded-2xl border border-zinc-800/40">
        <div
          role="status"
          className="animate-spin rounded-full h-10 w-10 border-t-2 border-orange-500 border-zinc-800 mb-4"
        />
        <span className="text-zinc-500 text-sm font-mono">Chargement de l'historique...</span>
      </div>
    );
  }

  if (state === 'error') {
    return (
      <div className="flex flex-col items-center justify-center py-16 bg-zinc-900/15 rounded-2xl border border-zinc-800/40 text-center px-6">
        <AlertCircle className="w-12 h-12 text-red-500 mb-4" />
        <h3 className="text-lg font-bold text-zinc-300">Erreur de chargement</h3>
        {error && (
          <p className="text-zinc-500 text-sm max-w-md mt-1">{error}</p>
        )}
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-4 px-4 py-2 rounded-lg border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-sm font-mono cursor-pointer transition-colors"
          >
            Réessayer
          </button>
        )}
      </div>
    );
  }

  if (state === 'empty') {
    return (
      <div className="flex flex-col items-center justify-center py-16 bg-zinc-900/15 rounded-2xl border border-zinc-800/40 text-center px-6">
        <AlertCircle className="w-12 h-12 text-zinc-600 mb-4" />
        <h3 className="text-lg font-bold text-zinc-300">Aucune métrique enregistrée</h3>
        <p className="text-zinc-500 text-sm max-w-md mt-1">
          Aucun point de métrique n'est encore enregistré pour la période et le serveur sélectionnés.
        </p>
      </div>
    );
  }

  const formatX = (tickItem: number) => formatXAxis(tickItem, config.period);

  return (
    <div className="p-5 rounded-xl border border-border-strong/30 bg-surface-2/10 backdrop-blur-xs flex flex-col gap-4">
      <h3 className="text-sm font-bold uppercase font-mono text-text-2 flex items-center gap-2">
        <Activity className="w-4 h-4" style={{ color: config.color }} />
        {config.title}
      </h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id={config.gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={config.color} stopOpacity={0.2} />
                <stop offset="95%" stopColor={config.color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a/30" />
            <XAxis
              dataKey="collected_at"
              tickFormatter={formatX}
              stroke="#71717a"
              fontSize={10}
            />
            <YAxis domain={[0, 100]} stroke="#71717a" fontSize={10} />
            <Tooltip
              labelFormatter={formatTooltipDate}
              contentStyle={{
                backgroundColor: '#18181b',
                borderColor: '#27272a',
                color: '#f4f4f5',
              }}
            />
            <Area
              type="monotone"
              dataKey={config.dataKey}
              stroke={config.color}
              fillOpacity={1}
              fill={`url(#${config.gradientId})`}
              name={config.title}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default ChartCard;
