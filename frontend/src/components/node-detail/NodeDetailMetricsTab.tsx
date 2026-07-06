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

const DiskPredictionCard: React.FC<{
  statsHistory: StatsPoint[];
  t: (key: string, variables?: Record<string, string | number>) => string;
}> = ({ statsHistory, t }) => {
  const n = statsHistory.length;
  const values = statsHistory.map((p) => p.disk);

  const sumX = values.reduce((sum, _, i) => sum + i, 0);
  const sumY = values.reduce((sum, y) => sum + y, 0);
  const sumXY = values.reduce((sum, y, i) => sum + i * y, 0);
  const sumX2 = values.reduce((sum, _, i) => sum + i * i, 0);

  const divider = n * sumX2 - sumX * sumX;
  if (divider === 0) return null;

  const slope = (n * sumXY - sumX * sumY) / divider;
  const intercept = (sumY - slope * sumX) / n;

  const meanY = sumY / n;
  const ssRes = values.reduce((sum, y, i) => sum + (y - (slope * i + intercept)) ** 2, 0);
  const ssTot = values.reduce((sum, y) => sum + (y - meanY) ** 2, 0);
  const r2 = ssTot === 0 ? 1 : 1 - ssRes / ssTot;

  if (r2 < 0.3) {
    return (
      <div className="p-4 border border-border rounded-xl bg-surface col-span-full">
        <p className="text-xs text-text-3">{t('metrics.prediction_low_confidence')}</p>
      </div>
    );
  }

  const predict = (indexDelta: number) => {
    const idx = n - 1 + indexDelta;
    const val = slope * idx + intercept;
    return Math.min(100, Math.max(0, val));
  };

  const timeTo90 = slope > 0 ? Math.round((90 - intercept) / slope) : Infinity;
  const hoursTo90 = Math.round((timeTo90 - (n - 1)) / 60);

  return (
    <div className="p-4 border border-border rounded-xl bg-surface col-span-full">
      <div className="text-xs font-interface font-bold uppercase tracking-wide text-text-1 mb-3">
        {t('metrics.prediction_title')}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-[10px] font-mono">
        <div className="flex flex-col gap-0.5">
          <span className="text-text-3">{t('metrics.prediction_1h')}</span>
          <span className="font-semibold">{predict(60).toFixed(1)}%</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-text-3">{t('metrics.prediction_6h')}</span>
          <span className="font-semibold">{predict(360).toFixed(1)}%</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-text-3">{t('metrics.prediction_24h')}</span>
          <span className="font-semibold">{predict(1440).toFixed(1)}%</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-text-3">{t('metrics.prediction_48h')}</span>
          <span className="font-semibold">{predict(2880).toFixed(1)}%</span>
        </div>
      </div>
      {slope > 0 && hoursTo90 > 0 && hoursTo90 < 720 && (
        <div className="mt-2 text-[10px] text-severity-warning">
          {t('metrics.prediction_full', { hours: hoursTo90 })}
        </div>
      )}
    </div>
  );
};

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
          {statsHistory.length >= 10 && <DiskPredictionCard statsHistory={statsHistory} t={t} />}
        </div>
      )}
    </div>
  );
};
