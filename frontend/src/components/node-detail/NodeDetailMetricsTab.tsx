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

const DISK_COLORS = [
  'var(--severity-info)',     // Blue
  '#06B6D4',                  // Cyan
  '#10B981',                  // Emerald
  '#6366F1',                  // Indigo
  '#8B5CF6',                  // Violet
  '#EC4899',                  // Pink
];

/* ---------- Days-remaining linear regression per mount point ---------- */

const DISPLAY_MAX_DAYS = 365; // cap the Y axis so the chart stays readable

interface DaysRemainingResult {
  mountPoint: string;
  days: number; // -1 = no fill trend (stable/declining), 0…DISPLAY_MAX_DAYS = capped
}

function computeDaysRemaining(data: StatsPoint[], mountPoint: string): DaysRemainingResult {
  const points = data
    .map((p, i) => {
      const disk = p.disks?.find((d) => d.mount_point === mountPoint);
      return disk ? { index: i, percent: disk.percent } : null;
    })
    .filter((x): x is { index: number; percent: number } => x !== null);

  if (points.length < 2) return { mountPoint, days: -1 };

  const n = points.length;
  const sumX = points.reduce((s, p) => s + p.index, 0);
  const sumY = points.reduce((s, p) => s + p.percent, 0);
  const sumXY = points.reduce((s, p) => s + p.index * p.percent, 0);
  const sumX2 = points.reduce((s, p) => s + p.index * p.index, 0);

  const denom = n * sumX2 - sumX * sumX;
  if (denom === 0) return { mountPoint, days: -1 };

  const slope = (n * sumXY - sumX * sumY) / denom; // percent per minute

  if (slope <= 0) return { mountPoint, days: -1 }; // not filling

  const lastPercent = points[points.length - 1].percent;
  const minutesRemaining = (100 - lastPercent) / slope;
  const days = minutesRemaining / 1440;

  if (days <= 0) return { mountPoint, days: -1 };
  if (days > DISPLAY_MAX_DAYS) return { mountPoint, days: DISPLAY_MAX_DAYS };
  return { mountPoint, days: Math.round(days) };
}

/* ---------- Custom disk tooltip ---------- */

const CustomDiskTooltip: React.FC<{
  active?: boolean;
  label?: string;
  payload?: Array<{ name: string; value: number; color: string }>;
}> = ({ active, label, payload }) => {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div
      className="rounded-lg border border-border-strong px-3 py-2 shadow-lg"
      style={{ background: 'var(--surface-2)', fontSize: '10px' }}
    >
      <div className="font-mono font-bold text-text-1 mb-1">{label}</div>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-1.5 py-0.5">
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-text-3 font-mono truncate max-w-[120px]">
            {entry.name.replace('days:', '')}
          </span>
          <span className="font-semibold text-text-1 ml-auto">
            {entry.value === 0 ? '—' : entry.value >= DISPLAY_MAX_DAYS ? `> ${DISPLAY_MAX_DAYS} j` : `${entry.value} j`}
          </span>
        </div>
      ))}
    </div>
  );
};

/* ---------- ChartCard ---------- */

const ChartCard: React.FC<{
  title: string;
  icon: React.ReactNode;
  dataKey: 'cpu' | 'ram' | 'disk';
  color: string;
  data: StatsPoint[];
}> = ({ title, icon, dataKey, color, data }) => {
  if (dataKey === 'disk') {
    const uniqueMountPoints = Array.from(
      new Set(
        data.flatMap((p) => p.disks || []).map((d) => d.mount_point)
      )
    ).filter(Boolean);

    // Compute days remaining per mount point
    const daysResults = uniqueMountPoints.map((mp) =>
      computeDaysRemaining(data, mp)
    );

    // Build enrichedData with days:${mount_point} keys
    const enrichedData = data.map((p) => {
      const newPoint: Record<string, string | number> = {
        time: p.time,
        cpu: p.cpu,
        ram: p.ram,
        disk: p.disk,
      };
      if (p.disks) {
        p.disks.forEach((d) => {
          if (d.mount_point) {
            const result = daysResults.find((r) => r.mountPoint === d.mount_point);
            const val = result ? result.days : -1;
            // Clamp -1 (no trend) to 0 so Recharts can plot it without skewing the axis
            newPoint[`days:${d.mount_point}`] = val === -1 ? 0 : val;
          }
        });
      }
      return newPoint;
    });

    // Find max finite days for Y axis (ignore 0 = no trend)
    const fillingDays = daysResults
      .map((r) => r.days)
      .filter((d) => d > 0);
    const maxDays = fillingDays.length > 0
      ? Math.max(...fillingDays)
      : DISPLAY_MAX_DAYS;
    // Add 10% padding
    const yMax = Math.ceil(maxDays * 1.1);

    return (
      <div className="p-4 border border-border rounded-xl bg-surface flex flex-col gap-2">
        <div className="flex items-center gap-2 text-text-1 font-interface font-bold text-xs uppercase tracking-wide">
          {icon} {title}
        </div>
        <div className="h-48 w-full mt-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={enrichedData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--text-3)" />
              <XAxis dataKey="time" stroke="var(--text-2)" fontSize={8} tickLine={false} />
              <YAxis
                stroke="var(--text-2)"
                fontSize={8}
                tickLine={false}
                domain={[0, yMax]}
                reversed
                tickFormatter={(v: number) => `${v}j`}
              />
              <Tooltip
                content={<CustomDiskTooltip />}
                cursor={{ stroke: 'var(--text-3)', strokeWidth: 1, strokeDasharray: '3 3' }}
              />
              {uniqueMountPoints.length > 0 ? (
                uniqueMountPoints.map((mp, index) => (
                  <Line
                    key={mp}
                    type="monotone"
                    dataKey={`days:${mp}`}
                    name={`days:${mp}`}
                    stroke={DISK_COLORS[index % DISK_COLORS.length]}
                    strokeWidth={1.5}
                    dot={false}
                    activeDot={{ r: 3, strokeWidth: 1, fill: 'var(--surface)' }}
                  />
                ))
              ) : (
                <Line type="monotone" dataKey="disk" stroke={color} strokeWidth={1.5} dot={false} activeDot={{ r: 3, strokeWidth: 1, fill: 'var(--surface)' }} />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  return (
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
            <Tooltip
              contentStyle={{ background: 'var(--surface-2)', borderColor: 'var(--border-strong)', fontSize: '10px' }}
              cursor={{ stroke: 'var(--text-3)', strokeWidth: 1, strokeDasharray: '3 3' }}
            />
            <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={1.5} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

/* ---------- DiskPredictionCard ---------- */

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
    return null;
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

/* ---------- formatBytes ---------- */

const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
};

/* ---------- NodeDetailMetricsTab ---------- */

export const NodeDetailMetricsTab: React.FC<{
  statsHistory: StatsPoint[];
  loading: boolean;
  onRefresh: () => void;
}> = ({ statsHistory, loading }) => {
  const { t } = useLocale();

  const lastSnap = statsHistory[statsHistory.length - 1];
  const disks = lastSnap?.disks || [];

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
            title={t('node_detail.chart_disk_days')}
            icon={<Layers className="w-4 h-4 text-severity-info" />}
            dataKey="disk"
            color="var(--severity-info)"
            data={statsHistory}
          />
          {statsHistory.length >= 10 && <DiskPredictionCard statsHistory={statsHistory} t={t} />}

          {disks.length > 0 && (
            <div className="p-4 border border-border rounded-xl bg-surface col-span-full flex flex-col gap-3">
              <div className="text-xs font-interface font-bold uppercase tracking-wide text-text-1">
                {t('metrics.disks_title') || 'Points de montage disques'}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-[10px] font-mono">
                  <thead>
                    <tr className="border-b border-border text-text-3">
                      <th className="py-2 pb-3">{t('metrics.disk_device') || 'Périphérique'}</th>
                      <th className="py-2 pb-3">{t('metrics.disk_mount') || 'Point de montage'}</th>
                      <th className="py-2 pb-3">{t('metrics.disk_type') || 'Type'}</th>
                      <th className="py-2 pb-3 text-right">{t('metrics.disk_usage') || 'Utilisation'}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {disks.map((d, idx) => (
                      <tr key={idx} className="border-b border-border last:border-0 text-text-2 hover:text-text-1">
                        <td className="py-2.5">{d.device}</td>
                        <td className="py-2.5 font-semibold text-accent">{d.mount_point}</td>
                        <td className="py-2.5 text-text-3">{d.fs_type}</td>
                        <td className="py-2.5 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <div className="w-20 bg-surface-2 rounded-full h-1.5 overflow-hidden border border-border">
                              <div
                                className={`h-full rounded-full ${d.percent > 85 ? 'bg-severity-critical' : d.percent > 70 ? 'bg-severity-warning' : 'bg-accent'}`}
                                style={{ width: `${d.percent}%` }}
                              />
                            </div>
                            <span className="font-semibold w-10 text-right">{d.percent.toFixed(0)}%</span>
                            <span className="text-text-3">({formatBytes(d.used_bytes)} / {formatBytes(d.total_bytes)})</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
