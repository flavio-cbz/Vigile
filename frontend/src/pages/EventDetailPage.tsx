import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router';
import { ArrowLeft, AlertTriangle, CheckCircle, ShieldAlert, Sparkles, Clock, Server, Cpu } from 'lucide-react';
import { api } from '../hooks/useApi';
import { usePageTitle } from '../hooks/usePageTitle';
import { useLocale } from '../i18n';
import { Spinner } from '../components/primitives/Spinner';
import type { AlertRecord } from '../components/node-detail/types';

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

interface DiagnosticResult {
  headline?: string;
  explanation?: string;
  suggested_action?: string;
  correlated_cause?: string[];
}

interface InvestigationRecord {
  id: string;
  alert_id?: string;
  node_id: string;
  status: string;
  result?: DiagnosticResult;
  created_at: number;
  completed_at?: number;
}

interface AlertDetailResponse {
  alert: AlertRecord;
  investigation?: InvestigationRecord | null;
}

export const EventDetailPage: React.FC = () => {
  const { alertId } = useParams<{ alertId: string }>();
  const navigate = useNavigate();
  const { locale } = useLocale();

  const [data, setData] = useState<AlertDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [nowSec] = useState(() => Date.now() / 1000);

  const localT = useCallback((frText: string, enText: string) => (locale === 'fr' ? frText : enText), [locale]);

  usePageTitle(data?.alert ? `${localT('Événement', 'Event')} ${data.alert.alert_name}` : 'Événement Vigile');

  useEffect(() => {
    if (!alertId) return;
    setLoading(true);
    setError(null);
    api<AlertDetailResponse>(`/api/nodes/alerts/${alertId}`)
      .then((res) => {
        if (res && res.alert) {
          setData(res);
        } else {
          setError(localT('Événement introuvable', 'Event not found'));
        }
      })
      .catch((err) => {
        console.error('Failed to fetch alert detail:', err);
        setError(localT('Erreur lors du chargement de l\'événement', 'Failed to load event details'));
      })
      .finally(() => setLoading(false));
  }, [alertId, localT]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="max-w-4xl mx-auto p-6 space-y-4">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 text-text-3 hover:text-text-1 text-xs font-mono transition-colors cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          {localT('RETOUR', 'BACK')}
        </button>
        <div className="p-6 border border-red-500/30 bg-red-500/10 rounded-2xl text-severity-critical">
          <p className="font-mono text-sm">{error || localT('Événement non trouvé', 'Event not found')}</p>
        </div>
      </div>
    );
  }

  const { alert, investigation } = data;

  const severityBadge = (sev: string) => {
    switch (sev) {
      case 'critical':
        return 'bg-red-500/10 text-severity-critical border-red-500/30';
      case 'warning':
        return 'bg-amber-500/10 text-severity-warning border-amber-500/30';
      default:
        return 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30';
    }
  };

  const formatAlertName = (name: string) => {
    const labels = ALERT_NAME_LABELS[name];
    if (labels) return localT(labels.fr, labels.en);
    return name.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  };

  const formatTS = (ts?: number | null) => {
    if (!ts) return '—';
    return new Date(ts * 1000).toLocaleString(locale === 'fr' ? 'fr-FR' : 'en-US', {
      dateStyle: 'medium',
      timeStyle: 'medium',
    });
  };

  const durationSec = alert.resolved_at ? alert.resolved_at - alert.created_at : nowSec - alert.created_at;
  const durationText = durationSec < 60 ? `${Math.round(durationSec)}s` : `${Math.round(durationSec / 60)} min`;

  return (
    <div className="max-w-4xl mx-auto p-4 sm:p-6 space-y-6 animate-fade-in">
      {/* Header with Navigation */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-4">
        <div>
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-2 text-text-3 hover:text-text-1 text-xs font-mono transition-colors mb-2 cursor-pointer"
          >
            <ArrowLeft className="w-4 h-4" />
            {localT('RETOUR', 'BACK')}
          </button>
          <div className="flex items-center gap-3">
            <span className={`text-[10px] font-mono font-bold uppercase px-2.5 py-1 rounded border ${severityBadge(alert.severity)}`}>
              {alert.severity}
            </span>
            <h1 className="font-interface font-black text-xl uppercase tracking-wider text-text-1">
              {formatAlertName(alert.alert_name)}
            </h1>
          </div>
        </div>

        <Link
          to={`/nodes/${alert.node_id}`}
          className="flex items-center gap-2 px-3 py-1.5 border border-border hover:border-accent rounded-lg text-xs font-mono text-text-2 hover:text-accent transition-all self-start sm:self-auto"
        >
          <Server className="w-3.5 h-3.5" />
          {localT('VOIR LE NŒUD', 'VIEW NODE')} ({alert.node_id.slice(0, 8)})
        </Link>
      </div>

      {/* Main Details Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Status Card */}
        <div className="p-4 border border-border rounded-xl bg-surface/40 backdrop-blur-sm space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-interface font-bold uppercase tracking-wider text-text-3">
              {localT('STATUT', 'STATUS')}
            </span>
            {alert.status === 'firing' ? (
              <span className="flex items-center gap-1.5 text-xs font-mono font-bold text-severity-critical">
                <AlertTriangle className="w-4 h-4 animate-pulse" />
                {localT('EN COURS', 'FIRING')}
              </span>
            ) : (
              <span className="flex items-center gap-1.5 text-xs font-mono font-bold text-severity-ok">
                <CheckCircle className="w-4 h-4" />
                {localT('RÉSOLU', 'RESOLVED')}
              </span>
            )}
          </div>
          <div className="text-xs font-mono text-text-2 pt-1 border-t border-border/50 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-text-3" />
            {localT('Durée :', 'Duration:')} {durationText}
          </div>
        </div>

        {/* Value Card */}
        <div className="p-4 border border-border rounded-xl bg-surface/40 backdrop-blur-sm space-y-2">
          <span className="text-[10px] font-interface font-bold uppercase tracking-wider text-text-3">
            {localT('MESURE ET SEUIL', 'MEASURED VALUE & THRESHOLD')}
          </span>
          <div className="flex items-baseline gap-3 pt-1">
            <span className="font-mono text-2xl font-black text-text-1">
              {alert.metric_value != null ? alert.metric_value.toFixed(1) : '—'}
            </span>
            {alert.threshold != null && (
              <span className="font-mono text-xs text-text-3">
                / {localT('Seuil :', 'Threshold:')} {alert.threshold}
              </span>
            )}
          </div>
        </div>

        {/* Timestamp Card */}
        <div className="p-4 border border-border rounded-xl bg-surface/40 backdrop-blur-sm space-y-2">
          <span className="text-[10px] font-interface font-bold uppercase tracking-wider text-text-3">
            {localT('CHRONOLOGIE', 'TIMELINE')}
          </span>
          <div className="text-xs font-mono space-y-1 pt-1">
            <div><span className="text-text-3">{localT('Déclenchement :', 'Fired:')}</span> {formatTS(alert.created_at)}</div>
            {alert.resolved_at && (
              <div><span className="text-text-3">{localT('Résolution :', 'Resolved:')}</span> {formatTS(alert.resolved_at)}</div>
            )}
          </div>
        </div>
      </div>

      {/* Alert Message Box */}
      <div className="p-5 border border-border rounded-2xl bg-surface/50 space-y-2">
        <div className="text-[10px] font-interface font-bold uppercase tracking-wider text-text-3 flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-accent" />
          {localT('MESSAGE DE L\'ALERTE', 'ALERT MESSAGE')}
        </div>
        <p className="font-mono text-sm text-text-1 leading-relaxed">
          {alert.message}
        </p>
      </div>

      {/* Processus suspect identifié */}
      {alert.details?.top_process && (
        <div className="p-5 border border-amber-500/30 rounded-2xl bg-amber-500/10 space-y-3">
          <div className="text-[10px] font-interface font-bold uppercase tracking-wider text-amber-400 flex items-center gap-2">
            <Cpu className="w-4 h-4 text-amber-400" />
            {localT('PROCESSUS SUSPECT ET CONSOMMATEUR IDENTIFIÉ', 'SUSPECT RESOURCE-HEAVY PROCESS IDENTIFIED')}
          </div>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-surface/60 border border-amber-500/20 rounded-xl">
            <div className="space-y-0.5">
              <span className="font-mono text-base font-black text-amber-200">
                {alert.details.top_process.name}
              </span>
              <div className="text-xs font-mono text-text-3">
                PID : <span className="text-text-1 font-bold">{alert.details.top_process.pid}</span>
                {alert.details.top_process.state && ` • État : ${alert.details.top_process.state}`}
              </div>
            </div>
            <div className="flex items-center gap-4 font-mono text-xs">
              <div className="px-2.5 py-1 rounded bg-amber-500/20 border border-amber-500/30 text-amber-300 font-bold">
                {typeof alert.details.top_process.cpu_percent === 'number'
                  ? `${alert.details.top_process.cpu_percent.toFixed(1)}% CPU`
                  : '—'}
              </div>
              {alert.details.top_process.mem_rss_kb != null && (
                <div className="px-2.5 py-1 rounded bg-surface-2 border border-border text-text-2">
                  {(alert.details.top_process.mem_rss_kb / 1024).toFixed(1)} MB RAM
                </div>
              )}
            </div>
          </div>

          {alert.details.top_processes && alert.details.top_processes.length > 1 && (
            <div className="space-y-1.5 pt-1">
              <div className="text-[9px] font-interface font-bold uppercase tracking-wider text-amber-400/80">
                {localT('AUTRES PROCESSUS CONSOMMATEURS AU MOMENT DE L\'ÉVÉNEMENT :', 'OTHER HEAVY PROCESSES AT EVENT TIME:')}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {alert.details.top_processes.slice(1, 5).map((p, idx) => (
                  <div key={idx} className="flex items-center justify-between p-2 rounded-lg bg-surface/40 border border-border/50 font-mono text-xs">
                    <span className="truncate max-w-[140px] text-text-2">{p.name} (PID {p.pid})</span>
                    <span className="font-bold text-amber-300">
                      {typeof p.cpu_percent === 'number' ? `${p.cpu_percent.toFixed(1)}%` : '—'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Diagnostic LLM Section */}
      {investigation?.result && (
        <div className="p-6 border border-accent/30 rounded-2xl bg-accent/5 space-y-4">
          <div className="flex items-center gap-2.5">
            <Sparkles className="w-5 h-5 text-accent animate-pulse" />
            <h2 className="font-interface font-black text-base uppercase tracking-wider text-accent">
              {localT('DIAGNOSTIC AUTOMATIQUE (COPILOT LLM)', 'AUTOMATIC LLM DIAGNOSTIC')}
            </h2>
          </div>

          {investigation.result.headline && (
            <div className="p-3 bg-surface/60 border border-border rounded-xl font-interface font-bold text-sm text-text-1">
              {investigation.result.headline}
            </div>
          )}

          {investigation.result.explanation && (
            <div className="space-y-1">
              <div className="text-[10px] font-interface font-bold uppercase tracking-wider text-text-3">
                {localT('EXPLICATION', 'EXPLANATION')}
              </div>
              <p className="font-mono text-xs text-text-2 leading-relaxed whitespace-pre-wrap">
                {investigation.result.explanation}
              </p>
            </div>
          )}

          {investigation.result.suggested_action && (
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-xl space-y-1">
              <div className="text-[10px] font-interface font-bold uppercase tracking-wider text-severity-ok">
                {localT('ACTION RECOMMANDÉE', 'RECOMMENDED ACTION')}
              </div>
              <p className="font-interface font-bold text-xs text-text-1 leading-relaxed">
                {investigation.result.suggested_action}
              </p>
            </div>
          )}

          {investigation.result.correlated_cause && investigation.result.correlated_cause.length > 0 && (
            <div className="space-y-1">
              <div className="text-[10px] font-interface font-bold uppercase tracking-wider text-text-3">
                {localT('CAUSES CORRÉLÉES DÉTECTÉES', 'CORRELATED CAUSES DETECTED')}
              </div>
              <ul className="list-disc list-inside font-mono text-xs text-text-2 space-y-1">
                {investigation.result.correlated_cause.map((cause, i) => (
                  <li key={i}>{cause}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
