import React, { useEffect, useState } from 'react';
import type { PluginAPI } from '../../../types/plugins';
import { useNodeStore } from '../../../store/nodeStore';
import { Activity, AlertTriangle, AlertCircle } from 'lucide-react';
import { t } from '../../../i18n';
import { formatAgo } from '../../../utils/formatTime';
import { useBlockData } from '../../../hooks/useBlockData';
import { PageHeader } from '../../../components/blocks/PageHeader';
import { FilterPanel } from '../../../components/blocks/FilterPanel';
import { ChartCard } from '../../../components/blocks/ChartCard';
import type { MetricPoint } from '../../../components/blocks/ChartCard';

type Period = '1h' | '6h' | '24h' | '7d';

interface MetricHistoryData {
  history: MetricPoint[];
  count: number;
  cached_at?: number | null;
}

interface MetricsHistoryProps {
  api: PluginAPI;
}

export const MetricsHistory: React.FC<MetricsHistoryProps> = () => {
  const { nodes } = useNodeStore();
  const [selectedNode, setSelectedNode] = useState<string>('all');
  const [period, setPeriod] = useState<Period>('24h');

  const { data, error, isLoading, isValidating, mutate, fetchedAt } = useBlockData<MetricHistoryData>(
    {
      command: 'metrics.get_metrics_history',
      params: { node_id: selectedNode !== 'all' ? selectedNode : undefined, period },
    },
    { revalidateInterval: 30_000 },
  );

  // B5 #12 : tick de fraîcheur périodique (toutes les 5s) pour recalculer dynamiquement formatAgo(cachedAt)
  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => {
      setTick((t) => t + 1);
    }, 5_000);
    return () => window.clearInterval(timer);
  }, []);

  const cachedAt = data?.cached_at ?? (fetchedAt ? Math.floor(fetchedAt / 1000) : null);

  const serveurOptions = [
    { value: 'all', label: 'Tous les serveurs' },
    ...nodes.map((n) => ({ value: n.id, label: n.name })),
  ];

  const periodeOptions: { value: Period; label: string }[] = [
    { value: '1h', label: 'Dernière heure' },
    { value: '6h', label: 'Dernières 6 heures' },
    { value: '24h', label: 'Dernières 24 heures' },
    { value: '7d', label: 'Derniers 7 jours' },
  ];

  return (
    <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 space-y-6 pb-12 animate-fade-in">
      <PageHeader
        title="Historique des Métriques"
        subtitle="Supervisez les tendances d'utilisation des ressources système de votre flotte."
        icon={<Activity className="w-5 h-5" />}
        actions={
          /* B5 #12 — Indicateur passif remplaçant le bouton Rafraîchir (polling SWR 30s actif) */
          cachedAt != null ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border-strong/30 bg-surface-2 text-text-3 font-mono text-xs font-semibold">
              {isValidating && (
                <span className="w-2 h-2 rounded-full bg-accent animate-pulse inline-block" />
              )}
              {t('common.last_updated', { time: formatAgo(cachedAt) })}
            </span>
          ) : undefined
        }
      />

      <FilterPanel
        fields={[
          {
            name: 'serveur',
            label: 'Serveur',
            type: 'select',
            options: serveurOptions,
            value: selectedNode,
            onChange: setSelectedNode,
          },
          {
            name: 'periode',
            label: 'Période',
            type: 'select',
            options: periodeOptions,
            value: period,
            onChange: (value: string) => setPeriod(value as Period),
          },
        ]}
      />

      {isLoading && !data ? (
        <div className="flex flex-col items-center justify-center py-20 bg-surface-2/40 rounded-2xl border border-border-strong/40">
          <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-accent border-border-strong mb-4"></div>
          <span className="text-text-3 text-sm font-mono">Chargement de l'historique...</span>
        </div>
      ) : error && !data ? (
        <div className="flex flex-col items-center justify-center py-16 bg-surface-2/40 rounded-2xl border border-border-strong/40 text-center px-6">
          <AlertTriangle className="w-12 h-12 text-red-500 mb-4" />
          <h3 className="text-lg font-bold text-text-1">{t('error_boundary.title')}</h3>
          <p className="text-text-3 text-sm max-w-md mt-1">{error.message}</p>
          <button
            onClick={() => void mutate()}
            className="mt-4 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-border-strong/50 bg-surface-2 hover:bg-surface-hover/80 text-text-1 font-mono text-xs font-semibold uppercase tracking-wider transition-colors duration-150 disabled:opacity-50 cursor-pointer"
          >
            Réessayer
          </button>
        </div>
      ) : !data || data.history.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 bg-surface-2/40 rounded-2xl border border-border-strong/40 text-center px-6">
          <AlertCircle className="w-12 h-12 text-text-3 mb-4" />
          <h3 className="text-lg font-bold text-text-1">Aucune métrique enregistrée</h3>
          <p className="text-text-3 text-sm max-w-md mt-1">
            Aucun point de métrique n'est encore enregistré pour la période et le serveur sélectionnés.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ChartCard
            context={{ params: { node_id: selectedNode, period }, node_id: selectedNode }}
            config={{
              title: 'Utilisation du Processeur (CPU)',
              dataKey: 'cpu_percent',
              color: '#f97316',
              gradientId: 'cpuColor',
              period,
            }}
            state="data"
            data={data.history}
          />
          <ChartCard
            context={{ params: { node_id: selectedNode, period }, node_id: selectedNode }}
            config={{
              title: 'Utilisation de la Mémoire RAM',
              dataKey: 'mem_percent',
              color: '#10b981',
              gradientId: 'memColor',
              period,
            }}
            state="data"
            data={data.history}
          />
        </div>
      )}
    </div>
  );
};

export default MetricsHistory;