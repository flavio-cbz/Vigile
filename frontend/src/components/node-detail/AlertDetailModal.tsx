import React, { useEffect } from 'react';
import { Link } from 'react-router';
import { X, ExternalLink, Cpu } from 'lucide-react';
import type { AlertRecord } from './types';

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

interface AlertDetailModalProps {
  alert: AlertRecord | null;
  locale: string;
  onClose: () => void;
}

export const AlertDetailModal: React.FC<AlertDetailModalProps> = ({ alert, locale, onClose }) => {
  const localT = (frText: string, enText: string) => {
    return locale === 'fr' ? frText : enText;
  };

  // Fermeture avec la touche Échap
  useEffect(() => {
    if (!alert) return;
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [alert, onClose]);

  if (!alert) return null;

  const severityBadge = (severity: string) => {
    const map: Record<string, string> = {
      critical: 'bg-red-500/10 text-severity-critical border-red-500/30',
      warning: 'bg-amber-500/10 text-severity-warning border-amber-500/30',
      info: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30',
    };
    return map[severity] || map.info;
  };

  const severityLabel = (severity: string) => {
    const map: Record<string, { fr: string; en: string }> = {
      critical: { fr: 'Critique', en: 'Critical' },
      warning: { fr: 'Avertissement', en: 'Warning' },
      info: { fr: 'Information', en: 'Info' },
    };
    const labels = map[severity] || map.info;
    return localT(labels.fr, labels.en);
  };

  const statusLabel = (status: string) => {
    if (status === 'firing') return localT('En cours', 'Firing');
    if (status === 'resolved') return localT('Résolue', 'Resolved');
    return status;
  };

  const formatTimestamp = (ts: number) => {
    if (!ts) return '—';
    const date = new Date(ts * 1000);
    return date.toLocaleString(locale === 'fr' ? 'fr-FR' : 'en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const formatAlertName = (name: string) => {
    const labels = ALERT_NAME_LABELS[name];
    if (labels) return localT(labels.fr, labels.en);
    return name
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const valueStr = alert.metric_value != null
    ? `${alert.metric_value.toFixed(1)}`
    : null;
  const thresholdStr = alert.threshold != null
    ? `${alert.threshold}`
    : null;

  const topProc = alert.details?.top_process;
  const topProcs = alert.details?.top_processes;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-md bg-surface border border-border-strong rounded-2xl shadow-2xl animate-fade-in overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* En-tête */}
        <div className="flex items-start justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2.5 pr-4">
            <span className={`text-[9px] font-mono font-bold uppercase px-2 py-1 rounded border ${severityBadge(alert.severity)}`}>
              {severityLabel(alert.severity)}
            </span>
            <h3 className="font-interface font-black text-sm uppercase tracking-wider text-text-1">
              {formatAlertName(alert.alert_name)}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 text-text-3 hover:text-text-1 transition-colors cursor-pointer p-1 -m-1 rounded hover:bg-surface-2"
            aria-label={localT('Fermer', 'Close')}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Corps */}
        <div className="p-4 space-y-3 max-h-[75vh] overflow-y-auto">
          {/* Message complet */}
          <div>
            <div className="text-[9px] font-interface font-bold uppercase tracking-wider text-text-3 mb-1">
              {localT('Message', 'Message')}
            </div>
            <p className="font-interface text-xs text-text-1 leading-relaxed break-words">
              {alert.message}
            </p>
          </div>

          {/* Processus le plus gourmand */}
          {topProc && (
            <div className="p-3 border border-amber-500/30 rounded-xl bg-amber-500/10 space-y-2">
              <div className="text-[9px] font-interface font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                {localT('PROCESSUS SUSPECT IDENTIFIÉ', 'SUSPECT PROCESS IDENTIFIED')}
              </div>
              <div className="flex items-baseline justify-between font-mono">
                <span className="text-sm font-black text-amber-200">{topProc.name}</span>
                <span className="text-xs font-bold text-amber-300">
                  {typeof topProc.cpu_percent === 'number' ? `${topProc.cpu_percent.toFixed(1)}% CPU` : ''}
                </span>
              </div>
              <div className="flex items-center gap-3 text-[10px] font-mono text-text-3 border-t border-amber-500/20 pt-1.5">
                <span>PID : {topProc.pid}</span>
                {topProc.mem_rss_kb != null && (
                  <span>RAM : {(topProc.mem_rss_kb / 1024).toFixed(1)} MB</span>
                )}
                {topProc.state && <span>État : {topProc.state}</span>}
              </div>

              {topProcs && topProcs.length > 1 && (
                <div className="pt-1 space-y-1">
                  <div className="text-[8px] font-interface font-bold uppercase text-amber-400/80">
                    {localT('Top processus de cette période :', 'Top processes in timeframe:')}
                  </div>
                  <div className="space-y-0.5">
                    {topProcs.slice(0, 3).map((p, idx) => (
                      <div key={idx} className="flex items-center justify-between text-[9px] font-mono text-text-2 bg-surface/50 px-2 py-0.5 rounded">
                        <span className="truncate max-w-[180px]">{p.name} (PID {p.pid})</span>
                        <span className="font-bold text-amber-300">{typeof p.cpu_percent === 'number' ? `${p.cpu_percent.toFixed(1)}%` : ''}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Valeur et seuil */}
          {(valueStr || thresholdStr) && (
            <div className="grid grid-cols-2 gap-2">
              {valueStr && (
                <div className="p-2.5 rounded-lg bg-surface-2/50 border border-border">
                  <div className="text-[9px] font-interface font-bold uppercase tracking-wider text-text-3 mb-0.5">
                    {localT('Valeur mesurée', 'Measured value')}
                  </div>
                  <div className="font-mono text-base font-black text-text-1">
                    {valueStr}
                  </div>
                </div>
              )}
              {thresholdStr && (
                <div className="p-2.5 rounded-lg bg-surface-2/50 border border-border">
                  <div className="text-[9px] font-interface font-bold uppercase tracking-wider text-text-3 mb-0.5">
                    {localT('Seuil', 'Threshold')}
                  </div>
                  <div className="font-mono text-base font-black text-text-2">
                    {thresholdStr}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Statut */}
          <div className="flex items-center justify-between p-2.5 rounded-lg bg-surface-2/50 border border-border">
            <span className="text-[9px] font-interface font-bold uppercase tracking-wider text-text-3">
              {localT('Statut', 'Status')}
            </span>
            <span
              className={`text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded border ${
                alert.status === 'firing'
                  ? 'bg-red-500/10 text-severity-critical border-red-500/30'
                  : 'bg-emerald-500/10 text-severity-ok border-emerald-500/30'
              }`}
            >
              {statusLabel(alert.status)}
            </span>
          </div>

          {/* Timestamps */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[10px]">
              <span className="font-interface font-bold uppercase tracking-wider text-text-3">
                {localT('Créée le', 'Created at')}
              </span>
              <span className="font-mono text-text-2">
                {formatTimestamp(alert.created_at)}
              </span>
            </div>
            {alert.resolved_at && (
              <div className="flex items-center justify-between text-[10px]">
                <span className="font-interface font-bold uppercase tracking-wider text-text-3">
                  {localT('Résolue le', 'Resolved at')}
                </span>
                <span className="font-mono text-text-2">
                  {formatTimestamp(alert.resolved_at)}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Pied */}
        <div className="p-3 border-t border-border flex items-center justify-between gap-2 bg-surface-2/30">
          <Link
            to={`/events/${alert.id}`}
            onClick={onClose}
            className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-interface font-bold uppercase tracking-wider border border-accent/40 text-accent hover:bg-accent/10 rounded cursor-pointer transition-all duration-150"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            {localT('Page Événement', 'Event Page')}
          </Link>

          <button
            onClick={onClose}
            className="px-4 py-1.5 text-[10px] font-interface font-bold uppercase tracking-wider border border-border hover:border-text-3 text-text-2 hover:text-text-1 rounded cursor-pointer transition-all duration-150"
          >
            {localT('Fermer', 'Close')}
          </button>
        </div>
      </div>
    </div>
  );
};
