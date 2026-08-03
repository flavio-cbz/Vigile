import React, { useState } from 'react';
import { Link } from 'react-router';
import { AlertTriangle, ChevronRight } from 'lucide-react';
import { Card, CardHeader, CardContent } from '../ui/Card';
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
}

export const MetricsTooltip: React.FC<MetricsTooltipProps> = ({ active, payload, label, locale, history, alerts }) => {
  const [nowSec] = useState(() => Date.now() / 1000);

  if (!active || !payload || payload.length === 0) return null;

  const localT = (frText: string, enText: string) => {
    return locale === 'fr' ? frText : enText;
  };

  const index = typeof label === 'number' ? label : parseInt(String(label), 10);
  const point = history && history[index] ? history[index] : null;
  const timeLabel = point ? point.time : label;

  const relativeDiff = history ? index - (history.length - 1) : 0;
  const relativeLabel = relativeDiff === 0 
    ? localT('Maintenant', 'Now') 
    : `${relativeDiff}m`;

  const pointTs = point?.collected_at;
  const activeAlerts = pointTs && alerts
    ? alerts.filter((a) => {
        const start = a.created_at - 120;
        const end = a.resolved_at ? a.resolved_at + 120 : nowSec + 120;
        return pointTs >= start && pointTs <= end;
      })
    : [];

  const formatAlertName = (name: string) => {
    const labels = ALERT_NAME_LABELS[name];
    if (labels) return localT(labels.fr, labels.en);
    return name.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  };

  return (
    <Card className="backdrop-blur-md animate-fade-in min-w-[180px] max-w-[260px] z-50">
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

        {activeAlerts.length > 0 && (
          <div className="pt-2 border-t border-border space-y-1">
            <div className="text-[9px] font-interface font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              {localT('ÉVÉNEMENT ACTIF', 'ACTIVE EVENT')} ({activeAlerts.length})
            </div>
            {activeAlerts.map((alt) => (
              <Link
                key={alt.id}
                to={`/events/${alt.id}`}
                className="flex items-center justify-between p-1.5 rounded bg-amber-500/10 border border-amber-500/20 hover:border-amber-500/50 transition-all text-left group"
              >
                <div className="truncate pr-1">
                  <div className="font-interface text-[9px] font-bold text-amber-300 truncate">
                    {formatAlertName(alt.alert_name)}
                  </div>
                  <div className="font-mono text-[8px] text-text-3 uppercase">
                    {alt.severity} • {alt.status}
                  </div>
                </div>
                <ChevronRight className="w-3 h-3 text-amber-400 opacity-60 group-hover:opacity-100 shrink-0" />
              </Link>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

