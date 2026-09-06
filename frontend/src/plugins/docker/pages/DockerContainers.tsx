import React, { useEffect, useState } from 'react';
import type { PluginAPI } from '../../../types/plugins';
import { useNodeStore } from '../../../store/nodeStore';
import { Server } from 'lucide-react';
import { useBlockData } from '../../../hooks/useBlockData';
import { PageHeader } from '../../../components/blocks/PageHeader';
import { FilterPanel } from '../../../components/blocks/FilterPanel';
import { DataTable } from '../../../components/blocks/DataTable';
import { StatusPill } from '../../../components/blocks/StatusPill';
import { ActionButtonRow } from '../../../components/blocks/ActionButtonRow';
import type { ColumnConfig, BlockAction } from '../../../components/blocks/types';
import { t } from '../../../i18n';
import { formatAgo } from '../../../utils/formatTime';
import { useAuthStore } from '../../../store/authStore';
import { ConfirmDeleteModal } from '../../../components/modals/ConfirmDeleteModal';

type Container = {
  node_id: string;
  id: string;
  name: string;
  image: string;
  state: string;
  ports: string[];
};

interface DockerContainersProps {
  api: PluginAPI;
}

// Contrat §4.3 : les tokens de hover sont portés par les variantes de bloc
// (danger/success/warning → DEFAULT_HOVER_TOKENS), jamais codés en dur dans la page.
const ACTION_STOP: BlockAction = { label: 'Arrêter le conteneur', command: 'stop', variant: 'danger' };
const ACTION_START: BlockAction = { label: 'Démarrer le conteneur', command: 'start', variant: 'success' };
const ACTION_RESTART: BlockAction = { label: 'Redémarrer le conteneur', command: 'restart', variant: 'warning' };
const ACTION_DELETE: BlockAction = { label: 'Supprimer le conteneur', command: 'delete', variant: 'danger', icon: 'trash' };

export const DockerContainers: React.FC<DockerContainersProps> = ({ api }) => {
  const { nodes } = useNodeStore();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';

  const [searchTerm, setSearchTerm] = useState('');
  const [selectedNode, setSelectedNode] = useState<string>('all');
  const [stateFilter, setStateFilter] = useState<string>('all');
  const [actionInProgress, setActionInProgress] = useState<Record<string, boolean>>({});
  const [containerToDelete, setContainerToDelete] = useState<Container | null>(null);

  const { data, error, isLoading, isValidating, mutate, fetchedAt } = useBlockData<{
    containers: Container[];
    cached_at?: number | null;
  }>(
    {
      command: 'docker.list_containers_route',
      params: { node_id: selectedNode !== 'all' ? selectedNode : undefined },
    },
    { revalidateInterval: 30_000 },
  );

  // B5 #11 : tick de fraîcheur périodique (toutes les 5s) pour recalculer dynamiquement formatAgo(cachedAt)
  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => {
      setTick((t) => t + 1);
    }, 5_000);
    return () => window.clearInterval(timer);
  }, []);

  const containers = data?.containers ?? [];
  const cachedAt = data?.cached_at ?? (fetchedAt ? Math.floor(fetchedAt / 1000) : null);

  const handleContainerAction = async (
    nodeId: string,
    containerId: string,
    action: string,
    containerName?: string,
  ) => {
    const key = `${nodeId}-${containerId}`;
    setActionInProgress((prev) => ({ ...prev, [key]: true }));
    try {
      const res = await api.fetch<{ success?: boolean; error?: string }>(
        `/containers/${containerId}/${action}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            node_id: nodeId,
            ...(containerName ? { container_name: containerName } : {}),
          }),
        },
      );
      if (!res || !res.success) {
        api.toast(res?.error || `Échec de l'action ${action}`, 'error');
        return;
      }
      api.toast(`Action ${action} exécutée avec succès`, 'success');
      setTimeout(() => void mutate(), 2000); // Rechargement après délai pour laisser la transition d'état
    } catch (err) {
      console.error(`Failed to trigger action ${action} on container ${containerId}:`, err);
      api.toast(
        err instanceof Error ? err.message : `L'action ${action} a échoué`,
        'error',
      );
      throw err;
    } finally {
      setActionInProgress((prev) => ({ ...prev, [key]: false }));
    }
  };

  const getNodeName = (nodeId: string) => {
    const n = nodes.find((node) => node.id === nodeId);
    return n ? n.name : nodeId.slice(0, 8);
  };

  const filteredContainers = containers.filter((c) => {
    // 1. Search term
    const matchesSearch =
      c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.image.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.id.toLowerCase().includes(searchTerm.toLowerCase());

    // 2. State filter
    let matchesState = true;
    if (stateFilter === 'running') {
      matchesState = c.state.toLowerCase() === 'running';
    } else if (stateFilter === 'stopped') {
      matchesState = c.state.toLowerCase() === 'exited' || c.state.toLowerCase() === 'created';
    } else if (stateFilter === 'failed') {
      matchesState =
        c.state.toLowerCase() === 'dead' ||
        (c.state.toLowerCase() === 'exited' && c.name.includes('fail')); // Simplification for failed state check
    }

    return matchesSearch && matchesState;
  });

  const serveurOptions = [
    { value: 'all', label: 'Tous les serveurs' },
    ...nodes.map((n) => ({ value: n.id, label: n.name })),
  ];

  const statutOptions = [
    { value: 'all', label: 'Tous les statuts' },
    { value: 'running', label: "En cours d'exécution" },
    { value: 'stopped', label: 'Arrêtés' },
    { value: 'failed', label: 'Échoués' },
  ];

  const columns: ColumnConfig<Container>[] = [
    {
      key: 'name',
      label: 'Conteneur',
      render: (c) => (
        <div className="flex flex-col">
          <span className="font-semibold text-text-1">{c.name}</span>
          <span className="text-[10px] text-text-3 font-mono mt-0.5">{c.id.slice(0, 12)}</span>
        </div>
      ),
    },
    {
      key: 'image',
      label: 'Image',
      render: (c) => (
        <span className="block font-mono text-xs text-text-2 max-w-[200px] truncate" title={c.image}>
          {c.image}
        </span>
      ),
    },
    {
      key: 'node_id',
      label: 'Serveur',
      render: (c) => (
        <span className="flex items-center gap-1.5 text-text-3 font-mono text-xs">
          <Server className="w-3.5 h-3.5 text-text-3" />
          {getNodeName(c.node_id)}
        </span>
      ),
    },
    {
      key: 'ports',
      label: 'Ports',
      render: (c) =>
        c.ports && c.ports.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {c.ports.slice(0, 3).map((p, idx) => (
              <span
                key={idx}
                className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface-2 text-text-3 border border-border-strong/40"
              >
                {p}
              </span>
            ))}
            {c.ports.length > 3 && (
              <span className="text-[9px] font-mono text-text-3 px-1">
                +{c.ports.length - 3}
              </span>
            )}
          </div>
        ) : (
          <span className="text-xs text-text-3 font-mono">—</span>
        ),
    },
    {
      key: 'state',
      label: 'Statut',
      render: (c) => <StatusPill status={c.state} />,
    },
  ];

  const showBusy = isLoading && !data;
  const showError = !!error && !data;
  const showEmpty = !showBusy && !showError && containers.length === 0;
  const showFilteredEmpty = !showBusy && !showError && containers.length > 0 && filteredContainers.length === 0;

  return (
    <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 space-y-6 pb-12 animate-fade-in">
      <PageHeader
        title="🐳 Conteneurs Docker"
        subtitle="Gérez et supervisez les conteneurs Docker en temps réel sur l'ensemble de votre flotte."
        actions={
          /* B5 #11 — Indicateur passif remplaçant le bouton Rafraîchir (polling SWR 30s actif) */
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
            name: 'search',
            type: 'search',
            label: 'Rechercher par nom, image ou ID...',
            placeholder: 'Rechercher par nom, image ou ID...',
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
            name: 'statut',
            label: 'Statut',
            type: 'select',
            options: statutOptions,
            value: stateFilter,
            onChange: setStateFilter,
          },
        ]}
      />

      <DataTable
        columns={columns}
        data={filteredContainers.map((c) => ({ ...c, _rowKey: `${c.node_id}-${c.id}` }))}
        rowKey="_rowKey"
        state={showBusy ? 'busy' : showError ? 'error' : showEmpty || showFilteredEmpty ? 'empty' : 'data'}
        busyMessage="Chargement des conteneurs..."
        emptyMessage={
          showEmpty
            ? 'Aucun conteneur trouvé'
            : 'Aucun conteneur Docker ne correspond aux critères de recherche actuels.'
        }
        error={error?.message}
        onRetry={() => void mutate()}
        actions={(c) => {
          const inProgress = actionInProgress[`${c.node_id}-${c.id}`];
          const stateLower = c.state.toLowerCase();
          const isRunning = stateLower === 'running';
          const isExitedOrCreated = stateLower === 'exited' || stateLower === 'dead' || stateLower === 'created';

          let rowActions: BlockAction[];
          if (isRunning) {
            rowActions = isAdmin ? [ACTION_STOP, ACTION_RESTART] : [ACTION_RESTART];
          } else if (isExitedOrCreated) {
            rowActions = [ACTION_START, ACTION_RESTART, ...(isAdmin ? [ACTION_DELETE] : [])];
          } else {
            rowActions = [ACTION_RESTART];
          }

          return (
            <ActionButtonRow
              actions={rowActions}
              busyCommands={inProgress ? new Set(['stop', 'start', 'restart', 'delete']) : new Set()}
              onAction={(command) => {
                if (command === 'delete') {
                  setContainerToDelete(c);
                } else {
                  void handleContainerAction(c.node_id, c.id, command, c.name);
                }
              }}
            />
          );
        }}
      />

      {containerToDelete && (
        <ConfirmDeleteModal
          title="Supprimer le conteneur Docker"
          message={`Cette action est irréversible. Le conteneur "${containerToDelete.name}" (${containerToDelete.id.slice(0, 12)}) sera définitivement détruit.`}
          confirmWord={containerToDelete.name}
          confirmLabel="Supprimer définitivement"
          onClose={() => setContainerToDelete(null)}
          onConfirm={async () => {
            await handleContainerAction(
              containerToDelete.node_id,
              containerToDelete.id,
              'delete',
              containerToDelete.name,
            );
            setContainerToDelete(null);
          }}
        />
      )}
    </div>
  );
};

export default DockerContainers;