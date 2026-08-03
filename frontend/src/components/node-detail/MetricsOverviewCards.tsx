import React from 'react';
import {
  Cpu,
  Database,
  Layers,
  TrendingUp,
  TrendingDown,
  Activity,
} from 'lucide-react';

const METRIC_THEMES = {
  cpu: { stroke: '#06B6D4' },
  ram: { stroke: '#8B5CF6' },
  disk: { stroke: '#F59E0B' },
};

const Sparkline: React.FC<{ paths: { line: string; area: string }; color: string }> = ({ paths, color }) => {
  if (!paths.line) return null;
  return (
    <svg width="120" height="32" className="overflow-visible opacity-80">
      <defs>
        <linearGradient id={`spark-${color}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0.0" />
        </linearGradient>
      </defs>
      <path d={paths.area} fill={`url(#spark-${color})`} />
      <path d={paths.line} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

interface MetricsOverviewCardsProps {
  lastSnap: { cpu: number; ram: number; disk: number } | undefined;
  cpuTrend: { dir: string; val: number };
  ramTrend: { dir: string; val: number };
  diskTrend: { dir: string; val: number };
  cpuSpark: { line: string; area: string };
  ramSpark: { line: string; area: string };
  diskSpark: { line: string; area: string };
  focusedMetric: 'all' | 'cpu' | 'ram' | 'disk';
  onToggleMetric: (metric: 'cpu' | 'ram' | 'disk') => void;
  getStatus: (val: number, type: 'cpu' | 'ram' | 'disk') => { text: string; bg: string };
  dataWindowHours?: number;
}

const TrendIcon: React.FC<{ dir: string; val: number }> = ({ dir, val }) => (
  <>
    {dir === 'up' ? (
      <TrendingUp className="w-3.5 h-3.5 text-red-400" />
    ) : dir === 'down' ? (
      <TrendingDown className="w-3.5 h-3.5 text-emerald-400" />
    ) : (
      <Activity className="w-3.5 h-3.5 text-text-3" />
    )}
    <span className={`font-mono text-[9px] font-bold ${
      dir === 'up' ? 'text-red-400' : dir === 'down' ? 'text-emerald-400' : 'text-text-3'
    }`}>
      {dir !== 'flat' ? `${val.toFixed(1)}%` : 'stable'}
    </span>
  </>
);

export const MetricsOverviewCards: React.FC<MetricsOverviewCardsProps> = ({
  lastSnap, cpuTrend, ramTrend, diskTrend,
  cpuSpark, ramSpark, diskSpark,
  focusedMetric, onToggleMetric, getStatus,
  dataWindowHours = 999,
}) => {
  const cpuValue = lastSnap?.cpu ?? 0;
  const ramValue = lastSnap?.ram ?? 0;
  const diskValue = lastSnap?.disk ?? 0;
  const cpuStatus = getStatus(cpuValue, 'cpu');
  const ramStatus = getStatus(ramValue, 'ram');
  const diskStatus = getStatus(diskValue, 'disk');
  const isLearningTrend = dataWindowHours < 2;

  const renderTrend = (dir: string, val: number) => (
    <div
      className="flex items-center gap-1.5 mt-0.5"
      title={isLearningTrend ? "Tendance disponible après 2h d'observation" : undefined}
      style={isLearningTrend ? { opacity: 0.3, filter: 'grayscale(1)' } : undefined}
    >
      <TrendIcon dir={dir} val={val} />
    </div>
  );

  return (
    <div className="grid gap-4 grid-cols-1 md:grid-cols-3">
      <div
        onClick={() => onToggleMetric('cpu')}
        className={`p-4 rounded-xl bg-surface/50 border backdrop-blur-md cursor-pointer transition-all duration-300 flex flex-col justify-between h-36 ${
          focusedMetric === 'cpu'
            ? 'border-cyan-500/80 shadow-[0_0_20px_rgba(6,182,212,0.15)] ring-1 ring-cyan-500/20'
            : 'border-border hover:border-cyan-500/40 hover:shadow-[0_0_15px_rgba(6,182,212,0.06)]'
        }`}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 shadow-inner">
              <Cpu className="w-4 h-4" />
            </div>
            <span className="font-interface font-extrabold uppercase text-[10px] tracking-wider text-text-2">CPU</span>
          </div>
          <span className={`text-[9px] font-mono px-2 py-0.5 rounded-full border ${cpuStatus.bg}`}>{cpuStatus.text}</span>
        </div>
        <div className="flex items-end justify-between mt-2">
          <div>
            <div className="font-mono text-3xl font-black text-text-1 tracking-tight">{cpuValue.toFixed(1)}%</div>
            {renderTrend(cpuTrend.dir, cpuTrend.val)}
          </div>
          <div style={isLearningTrend ? { opacity: 0.3 } : undefined}>
            <Sparkline paths={cpuSpark} color={METRIC_THEMES.cpu.stroke} />
          </div>
        </div>
      </div>

      <div
        onClick={() => onToggleMetric('ram')}
        className={`p-4 rounded-xl bg-surface/50 border backdrop-blur-md cursor-pointer transition-all duration-300 flex flex-col justify-between h-36 ${
          focusedMetric === 'ram'
            ? 'border-purple-500/80 shadow-[0_0_20px_rgba(139,92,246,0.15)] ring-1 ring-purple-500/20'
            : 'border-border hover:border-purple-500/40 hover:shadow-[0_0_15px_rgba(139,92,246,0.06)]'
        }`}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20 shadow-inner">
              <Database className="w-4 h-4" />
            </div>
            <span className="font-interface font-extrabold uppercase text-[10px] tracking-wider text-text-2">RAM</span>
          </div>
          <span className={`text-[9px] font-mono px-2 py-0.5 rounded-full border ${ramStatus.bg}`}>{ramStatus.text}</span>
        </div>
        <div className="flex items-end justify-between mt-2">
          <div>
            <div className="font-mono text-3xl font-black text-text-1 tracking-tight">{ramValue.toFixed(1)}%</div>
            {renderTrend(ramTrend.dir, ramTrend.val)}
          </div>
          <div style={isLearningTrend ? { opacity: 0.3 } : undefined}>
            <Sparkline paths={ramSpark} color={METRIC_THEMES.ram.stroke} />
          </div>
        </div>
      </div>

      <div
        onClick={() => onToggleMetric('disk')}
        className={`p-4 rounded-xl bg-surface/50 border backdrop-blur-md cursor-pointer transition-all duration-300 flex flex-col justify-between h-36 ${
          focusedMetric === 'disk'
            ? 'border-amber-500/80 shadow-[0_0_20px_rgba(245,158,11,0.15)] ring-1 ring-amber-500/20'
            : 'border-border hover:border-amber-500/40 hover:shadow-[0_0_15px_rgba(245,158,11,0.06)]'
        }`}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 shadow-inner">
              <Layers className="w-4 h-4" />
            </div>
            <span className="font-interface font-extrabold uppercase text-[10px] tracking-wider text-text-2">STORAGE</span>
          </div>
          <span className={`text-[9px] font-mono px-2 py-0.5 rounded-full border ${diskStatus.bg}`}>{diskStatus.text}</span>
        </div>
        <div className="flex items-end justify-between mt-2">
          <div>
            <div className="font-mono text-3xl font-black text-text-1 tracking-tight">{diskValue.toFixed(1)}%</div>
            {renderTrend(diskTrend.dir, diskTrend.val)}
          </div>
          <div style={isLearningTrend ? { opacity: 0.3 } : undefined}>
            <Sparkline paths={diskSpark} color={METRIC_THEMES.disk.stroke} />
          </div>
        </div>
      </div>
    </div>
  );
};

