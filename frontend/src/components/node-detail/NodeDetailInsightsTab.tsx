import React, { useState } from 'react';
import { Sparkles, RefreshCw, RotateCw, Clock } from 'lucide-react';
import { Spinner } from '../primitives/Spinner';
import { SeverityTag } from '../primitives/SeverityTag';
import { InsightText } from '../primitives/InsightText';
import { useUiStore } from '../../store/uiStore';
import { useToastStore } from '../../store/useToastStore';
import { api } from '../../hooks/useApi';
import { usePolling } from '../../hooks/usePolling';
import { useLocale } from '../../i18n';
import { formatOfflineDuration } from '../../utils/formatTime';
import type { InsightRecord, InsightsMeta } from './types';

/* ── Observation Card ─────────────────────────────────────────────── */

const ObservationCard: React.FC<{ meta: InsightsMeta }> = ({ meta }) => {
  const { t } = useLocale();
  const [now] = useState(() => Date.now());

  if (!meta.per_type_readiness) return null;

  const { cpu, ram, disk, profile } = meta.per_type_readiness;
  const types = [
    { label: 'CPU', data: cpu },
    { label: 'RAM', data: ram },
    { label: 'Disque', data: disk },
    { label: 'Profil', data: profile }
  ];

  const readyCount = types.filter((t) => t.data.ready).length;

  // Auto-hide completely when all 4 metrics are ready (no useless clutter)
  if (readyCount === 4) return null;

  // Compute remaining time & estimated ready timestamp
  let targetTimeMs: number;

  if (meta.next_profile_refresh_at) {
    targetTimeMs = new Date(meta.next_profile_refresh_at).getTime();
  } else {
    const unready = types.filter((t) => !t.data.ready);
    const maxReq = unready.length > 0 ? Math.max(...unready.map((t) => t.data.required)) : 24;
    const hoursLeft = Math.max(0.1, maxReq - meta.data_window_hours);
    targetTimeMs = now + hoursLeft * 3600 * 1000;
  }

  const diffMs = Math.max(0, targetTimeMs - now);
  const totalMinutes = Math.max(1, Math.round(diffMs / (1000 * 60)));
  const hoursLeft = Math.floor(totalMinutes / 60);
  const minsLeft = totalMinutes % 60;

  const formattedTimeRemaining = hoursLeft > 0
    ? `${hoursLeft}h ${minsLeft}m`
    : `${minsLeft} min`;

  const targetDate = new Date(targetTimeMs);
  const targetClockString = targetDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).replace(':', 'h');

  const readyLabels = types.filter((t) => t.data.ready).map((t) => t.label);
  const inProgressLabels = types.filter((t) => !t.data.ready).map((t) => t.label);

  const contextualText = readyLabels.length > 0
    ? `${readyLabels.join(' & ')} prêtes. Collecte d'historique en cours pour ${inProgressLabels.join(' & ')}.`
    : `Collecte d'historique en cours pour toutes les métriques.`;

  return (
    <div className="p-4 rounded-xl border border-amber-500/30 bg-surface-2/80 backdrop-blur-md shadow-md transition-all">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <Clock className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-interface font-bold text-xs uppercase tracking-wider text-text-1">
                {t('insights.observation_window', { defaultValue: "Période d'observation" })}
              </span>
              <span className="px-2 py-0.5 rounded-full text-[9px] font-mono font-bold bg-amber-500/15 text-amber-400 border border-amber-500/25">
                Maturité {readyCount}/4
              </span>
            </div>
            <p className="text-[11px] text-text-2 font-sans mt-0.5">
              {contextualText}
            </p>
          </div>
        </div>

        {/* Sober countdown & ready clock pill */}
        <div className="flex flex-col items-end shrink-0 ml-auto bg-surface-3 px-3 py-1.5 rounded-lg border border-border">
          <div className="text-[10px] font-mono text-text-2 flex items-center gap-1">
            Prêt à <span className="font-bold text-amber-400">{targetClockString}</span>
          </div>
          <div className="text-xs font-mono font-bold text-text-1">
            dans <span className="text-amber-400">{formattedTimeRemaining}</span>
          </div>
        </div>
      </div>

      {/* Segmented Progress Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-border/50">
        {types.map((type, idx) => (
          <div key={idx} className="flex flex-col gap-1">
            <div className="flex items-center justify-between text-[10px] font-mono">
              <span className="text-text-2 uppercase tracking-wider">{type.label}</span>
              <span className={type.data.ready ? "text-emerald-400 font-bold" : "text-amber-400"}>
                {type.data.ready ? 'Prêt' : `${type.data.hours.toFixed(1)}h/${type.data.required}h`}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-surface-3 overflow-hidden border border-border">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  type.data.ready
                    ? 'bg-emerald-500'
                    : 'bg-amber-500'
                }`}
                style={{ width: `${Math.min(100, Math.max(5, (type.data.hours / type.data.required) * 100))}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

/* ── Offline Insight Card ───────────────────────────────────────────── */

const OfflineInsightCard: React.FC<{ insight: InsightRecord; nodeId: string | undefined }> = ({ insight, nodeId }) => {
  const { t } = useLocale();
  const { openCopilot } = useUiStore();
  const [tick, setTick] = useState(0);
  const [isExpanded, setIsExpanded] = useState(false);

  usePolling(
    `offline_insight_tick_${(insight.raw as Record<string, unknown> | undefined)?.last_heartbeat ?? 'none'}`,
    () => setTick((t) => t + 1),
    30000,
    Boolean((insight.raw as Record<string, unknown> | undefined)?.last_heartbeat)
  );

  let headline = insight.headline;
  let detail = insight.detail;
  const raw = insight.raw as Record<string, unknown> | undefined;
  if (raw?.last_heartbeat) {
    const hbTime = Number(raw.last_heartbeat);
    const durationStr = formatOfflineDuration(hbTime);
    headline = t('node_detail.offline_headline', { duration: durationStr });
    const hbLabel = new Date(hbTime < 9999999999 ? hbTime * 1000 : hbTime).toLocaleString('fr-FR');
    detail = t('node_detail.offline_detail', { date: hbLabel });
  }

  return (
    <div
      data-tick={tick}
      className={`p-5 border border-text-3/20 rounded-xl bg-surface hover:border-text-2/40 flex flex-col justify-between shadow-md transition-all group ${isExpanded ? '!h-auto' : 'h-52'}`}
      style={{ background: 'linear-gradient(135deg, rgba(92, 87, 112, 0.02), var(--surface))' }}
    >
      <div className="flex items-center justify-between gap-2 shrink-0">
        <SeverityTag severity="offline" className="whitespace-nowrap" />
        <span className="text-[8px] font-extrabold font-interface tracking-widest text-text-3 uppercase whitespace-nowrap">
          {t('node_detail.ai_report_badge')}
        </span>
      </div>

      <div className="my-2.5 flex-1 flex flex-col justify-center min-w-0">
        <InsightText size="sm" className="block text-text-1 leading-snug font-serif !text-[16px] md:!text-[17px] line-clamp-2 group-hover:text-text-2 transition-colors" title={headline}>
          {headline}
        </InsightText>
        <p className={`text-text-3 text-[10px] font-sans mt-1 leading-relaxed ${isExpanded ? '' : 'line-clamp-2'}`} title={detail}>
          {detail}
          {detail.length > 80 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsExpanded(!isExpanded);
              }}
              className="ml-1 text-accent hover:text-accent-hover font-bold inline-block cursor-pointer hover:underline text-[9px]"
            >
              {isExpanded ? t('common.less') : t('common.more')}
            </button>
          )}
        </p>
      </div>

      <div className="pt-2 border-t border-border/40 flex items-center justify-between shrink-0">
        <span title="Assistant IA" className="flex items-center shrink-0">
          <Sparkles className="w-3.5 h-3.5 text-text-2 animate-pulse" />
        </span>
        <button
          onClick={() =>
            openCopilot({
              trigger: 'diagnostic',
              insight,
              node_id: nodeId,
            })
          }
          className="text-[10px] font-extrabold font-interface text-text-2 hover:underline flex items-center gap-0.5 cursor-pointer"
        >
          {t('card.analyze_ai')}
        </button>
      </div>
    </div>
  );
};

/* ── Standard Insight Card ──────────────────────────────────────────── */

const StandardInsightCard: React.FC<{ insight: InsightRecord; nodeId: string | undefined }> = ({ insight, nodeId }) => {
  const { t } = useLocale();
  const { openCopilot } = useUiStore();

  return (
    <div
      className="p-5 border border-border rounded-xl bg-surface hover:border-border-strong flex flex-col justify-between h-52 shadow-md transition-all group"
    >
      <div className="flex items-center justify-between gap-2 shrink-0">
        <SeverityTag severity={insight.severity} className="whitespace-nowrap" />
        <span className="text-[8px] font-extrabold font-interface tracking-widest text-text-3 uppercase whitespace-nowrap">
          {t('node_detail.ai_report_badge')}
        </span>
      </div>

      <div className="my-2.5 flex-1 flex flex-col justify-center min-w-0">
        <InsightText size="sm" className="block text-text-1 leading-snug font-serif !text-[16px] md:!text-[17px] line-clamp-2" title={insight.headline}>
          {insight.headline}
        </InsightText>
        <p className="text-text-3 text-[10px] font-sans mt-1 line-clamp-2 leading-relaxed" title={insight.detail}>
          {insight.detail}
        </p>
      </div>

      <div className="pt-2 border-t border-border/40 flex items-center justify-between shrink-0">
        <span title="Assistant IA" className="flex items-center shrink-0">
          <Sparkles className="w-3.5 h-3.5 text-accent animate-pulse" />
        </span>
        <button
          onClick={() =>
            openCopilot({
              trigger: 'diagnostic',
              insight,
              node_id: nodeId,
            })
          }
          className="text-[10px] font-extrabold font-interface text-accent hover:underline flex items-center gap-0.5 cursor-pointer"
        >
          {t('card.analyze_ai')}
        </button>
      </div>
    </div>
  );
};

/* ── Main Tab Component ─────────────────────────────────────────────── */

export const NodeDetailInsightsTab: React.FC<{
  insights: InsightRecord[];
  loading: boolean;
  nodeId: string | undefined;
  onRefresh: () => void;
  meta?: InsightsMeta | null;
}> = ({ insights, loading, nodeId, onRefresh, meta }) => {
  const { t } = useLocale();
  const [isRecalculating, setIsRecalculating] = useState(false);

  const handleRecalculate = async () => {
    if (!nodeId || isRecalculating) return;
    setIsRecalculating(true);
    try {
      await api(`/api/nodes/${nodeId}/profile/regenerate`, { method: 'POST', timeoutMs: 60000 });
      useToastStore.getState().addToast(
        'success',
        t('common.success', { defaultValue: 'Succès' }),
        'Analyse et profil LLM recalculés avec succès',
      );
      onRefresh();
    } catch (err) {
      console.error('Failed to recalculate profile:', err);
      useToastStore.getState().addToast(
        'error',
        t('common.error', { defaultValue: 'Erreur' }),
        'Échec du recalcul de l\'analyse',
      );
    } finally {
      setIsRecalculating(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center px-1">
        <h3 className="text-xs font-interface font-bold uppercase tracking-widest text-text-3">
          {t('node_detail.insights_section_title')}
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRecalculate}
            disabled={isRecalculating || loading}
            className="inline-flex items-center gap-1.5 px-3 py-1 bg-surface hover:bg-surface-2 border border-border text-xs rounded font-interface font-medium text-text-2 hover:text-text-1 transition-all cursor-pointer disabled:opacity-50 shadow-sm"
            title="Force le recalcul immédiat de l'analyse et du profil LLM"
          >
            <RotateCw className={`w-3.5 h-3.5 text-accent ${isRecalculating ? 'animate-spin' : ''}`} />
            <span>Recalculer l'analyse</span>
          </button>
          <button
            onClick={onRefresh}
            disabled={loading || isRecalculating}
            className="p-1.5 rounded bg-surface hover:bg-surface-2 border border-border text-text-3 hover:text-text-1 cursor-pointer transition-colors"
            title={t('node_detail.refresh_insights')}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Observation banner — shown when profile is still learning */}
      {meta && (
        <ObservationCard meta={meta} />
      )}

      {loading && insights.length === 0 ? (
        <div className="py-20 text-center text-text-3 flex flex-col items-center justify-center gap-3">
          <Spinner size="sm" />
          <span>{t('node_detail.insights_loading')}</span>
        </div>
      ) : insights.length === 0 ? (
        <div className="py-20 border border-dashed border-border rounded-xl bg-surface/30 text-center select-none text-text-3 space-y-2 max-w-lg mx-auto">
          <Sparkles className="w-8 h-8 mx-auto text-severity-ok opacity-45" />
          <h4 className="font-interface text-xs font-bold uppercase tracking-wider text-text-2">{t('node_detail.insights_empty_title')}</h4>
          <p className="text-[10px] leading-relaxed max-w-xs mx-auto text-text-3">
            {t('node_detail.insights_empty_description')}
          </p>
        </div>
      ) : (
        <div className="grid gap-3.5 md:grid-cols-2">
          {insights.map((ins, idx) =>
            ins.type === 'offline' ? (
              <OfflineInsightCard key={idx} insight={ins} nodeId={nodeId} />
            ) : (
              <StandardInsightCard key={idx} insight={ins} nodeId={nodeId} />
            )
          )}
        </div>
      )}
    </div>
  );
};
