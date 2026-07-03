import React from 'react';
import { Cpu, Layers, Database } from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { Spinner } from '../primitives/Spinner';
import { useLocale } from '../../i18n';
import type { StatsPoint } from './types';

const ChartCard: React.FC<{
  title: string;
  icon: React.ReactNode;
  dataKey: 'cpu' | 'ram' | 'disk';
  color: string;
  data: StatsPoint[];
}> = ({ title, icon, dataKey, color, data }) => (
  <div className="p-4 border border-border rounded-xl bg-surface flex flex-col gap-2">
    <div className="flex items-center gap-2 text-text-1 font-interface font-bold text-xs uppercase tracking-wide">
      {icon} {title}
    </div>
    <div className="h-48 w-full mt-2">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--text-3)" />
          <XAxis dataKey="time" stroke="var(--text-2)" fontSize={8} tickLine={false} />
          <YAxis stroke="var(--text-2)" fontSize={8} tickLine={false} domain={[0, 100]} />
          <Tooltip contentStyle={{ background: 'var(--surface-2)', borderColor: 'var(--border-strong)', fontSize: '10px' }} />
          <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={1.5} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  </div>
);

export const NodeDetailMetricsTab: React.FC<{
  statsHistory: StatsPoint[];
  loading: boolean;
  onRefresh: () => void;
}> = ({ statsHistory, loading }) => {
  const { t } = useLocale();

  return (
    <div className="space-y-6">
      <h3 className="text-xs font-interface font-bold uppercase tracking-widest text-text-3 px-1">
        {t('node_detail.metrics_title')}
      </h3>
      {loading && statsHistory.length === 0 ? (
        <div className="py-20 text-center text-text-3 flex flex-col items-center justify-center gap-2">
          <Spinner size="sm" />
          <span>{t('node_detail.metrics_loading')}</span>
        </div>
      ) : statsHistory.length === 0 ? (
        <div className="py-20 text-center text-text-3">{t('node_detail.metrics_empty')}</div>
      ) : (
        <div className="grid gap-6 md:grid-cols-3">
          <ChartCard
            title={t('node_detail.chart_cpu')}
            icon={<Cpu className="w-4 h-4 text-accent" />}
            dataKey="cpu"
            color="var(--accent)"
            data={statsHistory}
          />
          <ChartCard
            title={t('node_detail.chart_ram')}
            icon={<Database className="w-4 h-4 text-severity-warning" />}
            dataKey="ram"
            color="var(--severity-warning)"
            data={statsHistory}
          />
          <ChartCard
            title={t('node_detail.chart_disk')}
            icon={<Layers className="w-4 h-4 text-severity-info" />}
            dataKey="disk"
            color="var(--severity-info)"
            data={statsHistory}
          />
        </div>
      )}
    </div>
  );
};
