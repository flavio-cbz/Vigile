import React, { useEffect, useState } from 'react';
import type { PluginAPI } from '../../../types/plugins';
import { useNodeStore } from '../../../store/nodeStore';
import { Server, Activity } from 'lucide-react';
import { useBlockData } from '../../../hooks/useBlockData';
import { PageHeader } from '../../../components/blocks/PageHeader';
import { FilterPanel } from '../../../components/blocks/FilterPanel';
import { DataTable } from '../../../components/blocks/DataTable';
import { StatusPill } from '../../../components/blocks/StatusPill';
import { ActionButtonRow } from '../../../components/blocks/ActionButtonRow';
import { Banner } from '../../../components/blocks/Banner';
import type { ColumnConfig, BlockAction } from '../../../components/blocks/types';
import { t } from '../../../i18n';
import { formatAgo } from '../../../utils/formatTime';
import { useAuthStore } from '../../../store/authStore';

type Service = {
  node_id: string;
  name: string;
  state: string;
  status: string;
};

interface SystemdServicesProps {
  api: PluginAPI;
}

const PROTECTED_SERVICES = new Set([
  'ssh',
  'sshd',
  'docker',
  'dockerd',
  'containerd',
  'networking',
  'systemd-networkd',
  'networkmanager',
  'systemd-resolved',
  'systemd-journald',
  'systemd-logind',
  'dbus',
  'vigile',
  'vigile-worker',
]);

function isProtectedService(name: string): boolean {
  const canonical = name.trim().toLowerCase().replace(/\.(service|socket|target|timer|slice)$/, '');
  return PROTECTED_SERVICES.has(canonical);
}

// Contrat §4.3 : les tokens de hover sont portés par les variantes de bloc
// (danger/success/warning → DEFAULT_HOVER_TOKENS), jamais codés en dur dans la page.
const ACTION_STOP: BlockAction = { label: 'Arrêter le service', command: 'stop', variant: 'danger' };
const ACTION_START: BlockAction = { label: 'Démarrer le service', command: 'start', variant: 'success' };
const ACTION_RESTART: BlockAction = { label: 'Redémarrer le service', command: 'restart', variant: 'warning' };

export const SystemdServices: React.FC<SystemdServicesProps> = ({ api }) => {
  const { nodes } = useNodeStore();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedNode, setSelectedNode] = useState<string>('all');
  const [stateFilter, setStateFilter] = useState<string>('all');
  const [actionInProgress, setActionInProgress] = useState<Record<string, boolean>>({});
  const [, setTick] = useState(0);

  // Tick de fraîcheur périodique (toutes les 5s) pour recalculer dynamiquement formatAgo(cachedAt)
  useEffect(() => {
    const timer = window.setInterval(() => {
      setTick((t) => t + 1);
    }, 5_000);
    return () => window.clearInterval(timer);
  }, []);

  const { data, error, isLoading, isValidating, mutate, fetchedAt } = useBlockData<{
    services: Service[];
    count: number;
    cached_at: number | null;
    stale: boolean;
    errors?: string[];
  }>(
    {
      command: 'systemd.list_services_route',
      params: { node_id: selectedNode !== 'all' ? selectedNode : undefined },
    },
    { revalidateInterval: 30_000 },
  );

  const services = data?.services ?? [];
  const cachedAt = data?.cached_at ?? (fetchedAt ? Math.floor(fetchedAt / 1000) : null);
  const isStale = data?.stale ?? false;
  const errors = data?.errors ?? [];
  const hasErrors = errors.length > 0;
  const isCacheEmptyOrStale = cachedAt == null || isStale;

  const handleServiceAction = async (nodeId: string, serviceName: string, action: string) => {
    const key = `${nodeId}-${serviceName}`;
    setActionInProgress((prev) => ({ ...prev, [key]: true }));
    try {
      // Dispatch systemd action via the API
      const res = await api.fetch<{ success?: boolean; error?: string }>(
        `/services/${serviceName}/${action}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ node_id: nodeId }),
        },
      );
      if (!res || !res.success) {
        api.toast(res?.error || `Échec de l'action ${action}`, 'error');
        return;
      }
      api.toast(`Action ${action} exécutée avec succès`, 'success');
      setTimeout(() => void mutate({ forceRefresh: true }), 2000); // Rechargement forcé après délai pour laisser la transition d'état
    } catch (err) {
      console.error(`Failed to trigger action ${action} on service ${serviceName}:`, err);
      api.toast(
        err instanceof Error ? err.message : `L'action ${action} a échoué`,
        'error'
      );
    } finally {
      setActionInProgress((prev) => ({ ...prev, [key]: false }));
    }
  };

  const getNodeName = (nodeId: string) => {
    const n = nodes.find((node) => node.id === nodeId);
    return n ? n.name : nodeId.slice(0, 8);
  };

  const filteredServices = services.filter((s) => {
    // 1. Search term
    const matchesSearch = s.name.toLowerCase().includes(searchTerm.toLowerCase());

    // 2. State filter
    let matchesState = true;
    if (stateFilter === 'active') {
      matchesState = s.state.toLowerCase() === 'active';
    } else if (stateFilter === 'inactive') {
      matchesState = s.state.toLowerCase() === 'inactive';
    } else if (stateFilter === 'failed') {
      matchesState = s.state.toLowerCase() === 'failed' || s.status.toLowerCase() === 'failed';
    }

    return matchesSearch && matchesState;
  });

  const serveurOptions = [
    { value: 'all', label: 'Tous les serveurs' },
    ...nodes.map((n) => ({ value: n.id, label: n.name })),
  ];

  const etatOptions = [
    { value: 'all', label: 'Tous les états' },
    { value: 'active', label: 'Actifs (Active)' },
    { value: 'inactive', label: 'Inactifs (Inactive)' },
    { value: 'failed', label: 'Échoués (Failed)' },
  ];

  const columns: ColumnConfig<Service>[] = [
    {
      key: 'name',
      label: 'Nom du service',
      render: (s) => (
        <span className="font-semibold text-text-1 font-mono text-xs">{s.name}</span>
      ),
    },
    {
      key: 'node_id',
      label: 'Serveur',
      render: (s) => (
        <span className="flex items-center gap-1.5 text-text-3 font-mono text-xs">
          <Server className="w-3.5 h-3.5 text-text-3" />
          {getNodeName(s.node_id)}
        </span>
      ),
    },
    {
      key: 'state',
      label: 'État active',
      render: (s) => <StatusPill status={s.state} />,
    },
    {
      key: 'status',
      label: 'Statut sub',
      render: (s) => (
        <span className="font-mono text-xs text-text-3">{s.status}</span>
      ),
    },
  ];

  const showBusy = isLoading && !data;
  const showError = !!error && !data;
  const showEmpty = !showBusy && !showError && services.length === 0;
  const showFilteredEmpty = !showBusy && !showError && services.length > 0 && filteredServices.length === 0;

  return (
    <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 space-y-6 pb-12 animate-fade-in">
      <PageHeader
        title="Services Systemd"
        subtitle="Gérez et supervisez l'état des services et daemons système."
        icon={<Activity className="w-5 h-5" />}
        actions={
          <div className="flex items-center gap-2">
            {isStale && cachedAt != null && (
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-400 font-mono text-[10px] font-semibold uppercase tracking-wider">
                Périmé
              </span>
            )}
            {cachedAt == null && !isLoading && (
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full border border-border-strong/30 bg-surface-2 text-text-3 font-mono text-[10px] font-semibold uppercase tracking-wider">
                Cache vide
              </span>
            )}
            {/* B5 #10 — Indicateur passif cliquable pour forcer le rafraîchissement (bypass TTL 300s) */}
            {cachedAt != null && (
              <button
                type="button"
                onClick={() => void mutate({ forceRefresh: true })}
                title="Forcer l'actualisation"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border-strong/30 bg-surface-2 hover:bg-surface-hover text-text-3 font-mono text-xs font-semibold cursor-pointer transition-colors"
              >
                {isValidating && (
                  <span className="w-2 h-2 rounded-full bg-accent animate-pulse inline-block" />
                )}
                {t('common.last_updated', { time: formatAgo(cachedAt) })}
              </button>
            )}
          </div>
        }
      />

      {hasErrors && isCacheEmptyOrStale && (
        <Banner
          variant="warning"
          title="Échec de synchronisation avec le Worker"
          message={errors.join(' — ')}
          action={{
            label: 'Réessayer',
            onClick: () => void mutate({ forceRefresh: true }),
          }}
        />
      )}

      <FilterPanel
        fields={[
          {
            name: 'search',
            type: 'search',
            label: 'Rechercher par nom de service...',
            placeholder: 'Rechercher par nom de service...',
            value: searchTerm,
            onChange: setSearchTerm,
          },
          {
            name: 'serveur',
            label: 'Serveur',
            type: 'select',
            options: serveurOptions,
            value: selectedNode,
            onChange: setSelectedNode,
          },
          {
            name: 'etat',
            label: 'État',
            type: 'select',
            options: etatOptions,
            value: stateFilter,
            onChange: setStateFilter,
          },
        ]}
      />

      <DataTable
        columns={columns}
        data={filteredServices.map((s) => ({ ...s, _rowKey: `${s.node_id}-${s.name}` }))}
        rowKey="_rowKey"
        state={showBusy ? 'busy' : showError ? 'error' : showEmpty || showFilteredEmpty ? 'empty' : 'data'}
        busyMessage="Chargement des services..."
        emptyMessage={
          showEmpty
            ? 'Aucun service trouvé'
            : 'Aucun service systemd ne correspond aux critères de recherche actuels.'
        }
        error={error?.message}
        onRetry={() => void mutate({ forceRefresh: true })}
        actions={(s) => {
          const inProgress = actionInProgress[`${s.node_id}-${s.name}`];
          const isActive = s.state.toLowerCase() === 'active';
          const isProtected = isProtectedService(s.name);
          const rowActions = isActive
            ? isProtected || !isAdmin
              ? [ACTION_RESTART]
              : [ACTION_STOP, ACTION_RESTART]
            : [ACTION_START, ACTION_RESTART];
          return (
            <ActionButtonRow
              actions={rowActions}
              busyCommands={inProgress ? new Set(['stop', 'start', 'restart']) : new Set()}
              onAction={(command) => void handleServiceAction(s.node_id, s.name, command)}
            />
          );
        }}
      />
    </div>
  );
};

export default SystemdServices;