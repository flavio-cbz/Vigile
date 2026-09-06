import React, { useState } from 'react';
import { RotateCw, Calendar } from 'lucide-react';
import { api } from '../../hooks/useApi';
import { useToastStore } from '../../store/useToastStore';
import {
  TIME_RANGE_PRESETS,
  sanitizeCustomRangeSeconds,
  type SelectableTimeRangePreset,
  type TimeRangePreset,
} from './metricsRanges';

export type { TimeRangePreset };

const RANGE_LABELS: Record<SelectableTimeRangePreset, string> = {
  '1h': '1H',
  '6h': '6H',
  '12h': '12H',
  '24h': '24H',
  '7d': '7J',
  '30d': '30J',
};

const timeRanges: { id: SelectableTimeRangePreset; label: string }[] = TIME_RANGE_PRESETS.map((id) => ({
  id,
  label: RANGE_LABELS[id],
}));

interface MetricsOverviewProps {
  timeRange: TimeRangePreset;
  isRefreshing: boolean;
  lastRefreshed: string;
  locale: string;
  nodeId?: string;
  onTimeRangeChange: (range: TimeRangePreset, customStartSec?: number, customEndSec?: number) => void;
  /** Callback de rafraîchissement invoqué après recalcul d'analyse/baselines. */
  onRefresh?: () => void;
}

export const MetricsOverview: React.FC<MetricsOverviewProps> = ({
  timeRange, isRefreshing, lastRefreshed, locale, nodeId,
  onTimeRangeChange, onRefresh,
}) => {
  const [isRecalculating, setIsRecalculating] = useState(false);
  const [showCustomPicker, setShowCustomPicker] = useState(false);
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');

  const localT = (frText: string, enText: string) => {
    return locale === 'fr' ? frText : enText;
  };

  const handleRecalculate = async () => {
    if (!nodeId || isRecalculating) return;
    setIsRecalculating(true);
    try {
      const results = await Promise.allSettled([
        api(`/api/nodes/${nodeId}/profile/regenerate`, { method: 'POST', timeoutMs: 60000 }),
        api(`/api/nodes/${nodeId}/baseline/recalculate`, { method: 'POST', timeoutMs: 30000 }),
      ]);
      const failed = results.filter((r) => r.status === 'rejected').length;
      if (failed === results.length) {
        useToastStore.getState().addToast(
          'error',
          localT('Erreur', 'Error'),
          localT("Échec du recalcul de l'analyse", 'Failed to recalculate analysis'),
        );
      } else if (failed > 0) {
        useToastStore.getState().addToast(
          'warning',
          localT('Partiel', 'Partial'),
          localT(
            "Recalcul partiel : une des opérations a échoué, les données affichées peuvent être incomplètes",
            'Partial recalculation: one operation failed, displayed data may be incomplete',
          ),
        );
        onRefresh?.();
      } else {
        useToastStore.getState().addToast(
          'success',
          localT('Succès', 'Success'),
          localT('Analyse et baselines recalculées avec succès', 'Analysis and baselines successfully recalculated'),
        );
        onRefresh?.();
      }
    } finally {
      setIsRecalculating(false);
    }
  };

  const handleApplyCustomRange = () => {
    if (!customStart || !customEnd) return;
    const startSec = Math.floor(new Date(customStart).getTime() / 1000);
    const endSec = Math.floor(new Date(customEnd).getTime() / 1000);
    // Fail-closed mirror of the hook validation — reject before propagating
    if (!sanitizeCustomRangeSeconds({ start: startSec, end: endSec })) return;
    onTimeRangeChange('custom', startSec, endSec);
    setShowCustomPicker(false);
  };

  return (
    <div className="flex flex-col space-y-3 border-b border-border/80 pb-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-interface font-extrabold uppercase tracking-wider text-text-1">
              {localT('Moniteur de Télémétrie', 'Telemetry Monitor')}
            </h3>
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
          </div>
          <p className="text-[10px] text-text-3 font-medium">
            {localT('Dernière synchronisation :', 'Last synchronization :')} {lastRefreshed}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex bg-surface-2 p-1 rounded-lg border border-border">
            {timeRanges.map((r) => {
              // timeRange is guaranteed valid upstream (hook fails-closed)
              const isSelected = timeRange === r.id;
              return (
                <button
                  key={r.id}
                  onClick={() => {
                    setShowCustomPicker(false);
                    onTimeRangeChange(r.id);
                  }}
                  disabled={isRefreshing || isRecalculating}
                  className={`px-2.5 py-1 text-[10px] font-interface font-bold uppercase rounded transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer ${
                    isSelected
                      ? 'bg-accent text-bg shadow'
                      : 'text-text-3 hover:text-text-2'
                  }`}
                >
                  {r.label}
                </button>
              );
            })}

            <button
              onClick={() => setShowCustomPicker(!showCustomPicker)}
              disabled={isRefreshing || isRecalculating}
              className={`px-2.5 py-1 text-[10px] font-interface font-bold uppercase rounded transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center gap-1 ${
                timeRange === 'custom'
                  ? 'bg-accent text-bg shadow'
                  : 'text-text-3 hover:text-text-2'
              }`}
            >
              <Calendar className="w-3 h-3" />
              {localT('Personnalisé...', 'Custom...')}
            </button>
          </div>


          <button
            onClick={handleRecalculate}
            disabled={isRecalculating || isRefreshing}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-surface-2 hover:bg-surface-3 border border-border text-xs rounded-lg font-interface font-medium text-text-2 hover:text-text-1 transition-all cursor-pointer disabled:opacity-50 shadow-sm"
            title={localT("Force le recalcul immédiat de l'analyse et des baselines", "Force immediate analysis and baselines recalculation")}
          >
            <RotateCw className={`w-3.5 h-3.5 text-accent ${isRecalculating ? 'animate-spin' : ''}`} />
            <span>{localT("Recalculer l'analyse", "Recalculate analysis")}</span>
          </button>
        </div>
      </div>

      {showCustomPicker && (
        <div className="p-3 bg-surface-2/80 border border-border rounded-xl flex flex-wrap items-center gap-3 animate-fade-in font-mono text-xs">
          <div className="flex items-center gap-2">
            <span className="text-text-3 uppercase text-[10px]">{localT('Début :', 'Start:')}</span>
            <input
              type="datetime-local"
              value={customStart}
              onChange={(e) => setCustomStart(e.target.value)}
              className="bg-surface border border-border rounded px-2 py-1 text-text-1 text-xs"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-text-3 uppercase text-[10px]">{localT('Fin :', 'End:')}</span>
            <input
              type="datetime-local"
              value={customEnd}
              onChange={(e) => setCustomEnd(e.target.value)}
              className="bg-surface border border-border rounded px-2 py-1 text-text-1 text-xs"
            />
          </div>
          <button
            onClick={handleApplyCustomRange}
            disabled={!customStart || !customEnd}
            className="px-3 py-1 bg-accent text-bg font-interface font-bold uppercase text-[10px] rounded hover:bg-accent-hover transition-colors disabled:opacity-50 cursor-pointer"
          >
            {localT('Appliquer', 'Apply')}
          </button>
        </div>
      )}
    </div>
  );
};

