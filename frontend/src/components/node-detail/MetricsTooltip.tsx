import React, { useState } from 'react';
import { Link } from 'react-router';
import { AlertTriangle, ChevronRight } from 'lucide-react';
import { Card, CardHeader, CardContent } from '../ui/Card';
import { formatRelativeDuration } from '../../utils/formatTime';
import type { StatsPoint, AlertRecord } from './types';

const ALERT_NAME_LABELS: Record<string, { fr: string; en: string }> = {
  cpu_high_percent: { fr: 'Processeur très sollicité', en: 'CPU heavily loaded' },
  cpu_high_load: { fr: 'Charge CPU élevée', en: 'High CPU load' },
  cpu_load_per_core_high: { fr: 'Charge par cœur élevée', en: 'High per-core load' },
  memory_usage_high: { fr: 'Mémoire très utilisée', en: 'Memory heavily used' },
  memory_swap_active: { fr: 'Swap actif', en: 'Swap active' },
  disk_usage_high: { fr: 'Stockage presque plein', en: 'Storage nearly full' },
  disk_io_high: { fr: 'I/O disque élevé', en: 'High disk I/O' },
  swap_usage_percent_high: { fr: 'Swap fortement utilisé', en: 'Swap heavily used' },
  psi_cpu_pressure: { fr: 'Pression CPU élevée', en: 'High CPU pressure' },
  psi_io_pressure: { fr: 'Pression I/O élevée', en: 'High I/O pressure' },
  psi_mem_pressure: { fr: 'Pression mémoire élevée', en: 'High memory pressure' },
  process_count_high: { fr: 'Trop de processus', en: 'Too many processes' },
  file_handle_usage_high: { fr: 'Limite de fichiers atteinte', en: 'File handle limit reached' },
  network_drops_high: { fr: 'Pertes réseau élevées', en: 'High network drops' },
  temperature_high: { fr: 'Température élevée', en: 'High temperature' },
  entropy_low: { fr: 'Entropie faible', en: 'Low entropy' },
  node_state_lost: { fr: 'Nœud perdu', en: 'Node lost' },
  node_state_stale: { fr: 'Nœud inactif', en: 'Node stale' },
};

interface TooltipPayloadItem {
  name: string;
  value: number;
  color?: string;
  stroke?: string;
  fill?: string;
  dataKey?: string;
}

interface MetricsTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string | number;
  locale: string;
  history: StatsPoint[];
  alerts?: AlertRecord[];
  onSelectAlert?: (alert: AlertRecord) => void;
}

export const MetricsTooltip: React.FC<MetricsTooltipProps> = ({
  active,
  payload,
  label,
  locale,
  history,
  alerts,
  onSelectAlert,
}) => {
  const [nowSec] = useState(() => Date.now() / 1000);

  if (!active || !payload || payload.length === 0) return null;

  const localT = (frText: string, enText: string) => {
    return locale === 'fr' ? frText : enText;
  };

  const index = typeof label === 'number' ? label : parseInt(String(label), 10);
  const point = history && history[index] ? history[index] : null;
  const timeLabel = point ? point.time : label;

  const lastPoint = history ? history[history.length - 1] : null;
  const relativeDiffSec = point?.collected_at != null && lastPoint?.collected_at != null
    ? point.collected_at - lastPoint.collected_at
    : (index - (history.length - 1)) * 60;
  const relativeLabel = Math.abs(relativeDiffSec) < 1
    ? localT('Maintenant', 'Now')
    : formatRelativeDuration(relativeDiffSec);

  const pointTs = point?.collected_at;
  const activeAlerts = pointTs && alerts
    ? alerts.filter((a) => {
        const start = a.created_at - 120;
        const end = a.resolved_at ? a.resolved_at + 120 : nowSec + 120;
        return pointTs >= start && pointTs <= end;
      })
    : [];

  const topPointProc = point?.top_processes && point.top_processes.length > 0 ? point.top_processes[0] : null;

  const formatAlertName = (name: string) => {
    const labels = ALERT_NAME_LABELS[name];
    if (labels) return localT(labels.fr, labels.en);
    return name.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  };

  return (
    <Card className="backdrop-blur-md animate-fade-in min-w-[200px] max-w-[280px] z-50 pointer-events-auto shadow-xl border-border-strong">
      <CardHeader>
        <div className="text-[9px] font-mono text-text-3 uppercase tracking-wider">
          {localT('Temps', 'Time')} : {relativeLabel} {timeLabel ? `(${timeLabel})` : ''}
        </div>
      </CardHeader>
      <CardContent className="pt-0 space-y-2">
        <div className="space-y-1 max-h-40 overflow-y-auto pr-1">
          {payload.map((item, idx) => {
            const color = item.stroke || item.color;
            const name = item.name;
            const value = item.value;
            return (
              <div key={idx} className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} />
                <span className="font-interface text-[10px] font-bold uppercase text-text-2 truncate max-w-[120px]">{name}</span>
                <span className="ml-auto font-mono text-[11px] font-bold text-text-1">
                  {typeof value === 'number' ? `${value.toFixed(1)}%` : value}
                </span>
              </div>
            );
          })}
        </div>

        {topPointProc && activeAlerts.length === 0 && (
          <div className="pt-1.5 border-t border-border/50">
            <div className="text-[8px] font-interface font-bold uppercase tracking-wider text-text-3 mb-0.5">
              {localT('Proc. principal', 'Top Process')}
            </div>
            <div className="flex items-center justify-between text-[9px] font-mono text-text-2 bg-surface-2/60 px-1.5 py-0.5 rounded border border-border/40">
              <span className="truncate max-w-[120px] font-bold text-accent">{topPointProc.name}</span>
              <span className="shrink-0 text-[8px] text-text-3">
                (PID {topPointProc.pid}) {typeof topPointProc.cpu_percent === 'number' ? `${topPointProc.cpu_percent.toFixed(1)}%` : ''}
              </span>
            </div>
          </div>
        )}

        {activeAlerts.length > 0 && (
          <div className="pt-2 border-t border-border space-y-1.5">
            <div className="text-[9px] font-interface font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3 animate-pulse" />
              {localT('ÉVÉNEMENT ACTIF', 'ACTIVE EVENT')} ({activeAlerts.length})
            </div>
            {activeAlerts.map((alt) => {
              const topProc = alt.details?.top_process || topPointProc;
              return (
                <div
                  key={alt.id}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (onSelectAlert) onSelectAlert(alt);
                  }}
                  className="p-1.5 rounded bg-amber-500/10 border border-amber-500/20 hover:border-amber-500/60 hover:bg-amber-500/15 transition-all text-left group cursor-pointer"
                >
                  <div className="flex items-center justify-between">
                    <div className="truncate pr-1">
                      <div className="font-interface text-[9px] font-bold text-amber-300 truncate">
                        {formatAlertName(alt.alert_name)}
                      </div>
                      <div className="font-mono text-[8px] text-text-3 uppercase">
                        {alt.severity} • {alt.status}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <Link
                        to={`/events/${alt.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="p-0.5 hover:text-amber-300 text-text-3 transition-colors"
                        title={localT('Page événement complète', 'Full event page')}
                      >
                        <ChevronRight className="w-3.5 h-3.5 opacity-70 group-hover:opacity-100" />
                      </Link>
                    </div>
                  </div>

                  {topProc && (
                    <div className="mt-1 pt-1 border-t border-amber-500/20 text-[8px] font-mono text-amber-200/90 flex items-center justify-between">
                      <span className="truncate max-w-[130px]">
                        🎯 <strong className="text-amber-100">{topProc.name}</strong> (PID {topProc.pid})
                      </span>
                      <span className="shrink-0 font-bold ml-1">
                        {typeof topProc.cpu_percent === 'number' ? `${topProc.cpu_percent.toFixed(1)}%` : ''}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
};
