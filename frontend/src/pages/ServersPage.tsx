import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { Server, Search, HardDrive, Cpu, Clock, Plus } from 'lucide-react';
import { useNodeStore, type Node } from '../store/nodeStore';
import { useLayoutStore } from '../store/layoutStore';
import { StatusDot } from '../components/primitives/StatusDot';
import { EmptyState } from '../components/ui/EmptyState';
import { KebabMenu } from '../components/ui/KebabMenu';
import { ConfirmDeleteModal } from '../components/modals/ConfirmDeleteModal';
import { RenameNodeModal } from '../components/modals/RenameNodeModal';
import { useLocale } from '../i18n';
import { usePageTitle } from '../hooks/usePageTitle';
import { usePermission } from '../hooks/usePermission';
import { useToastStore } from '../store/useToastStore';
import { nodeMutations } from '../store/nodeMutations';
import { clsx } from 'clsx';
import { api } from '../hooks/useApi';
import { formatOfflineDuration } from '../utils/formatTime';

const formatHeartbeatTime = (ts: number | null): string => {
  if (!ts) return '—';
  const date = new Date(ts < 9999999999 ? ts * 1000 : ts);
  const hrs = date.getHours().toString().padStart(2, '0');
  const mins = date.getMinutes().toString().padStart(2, '0');
  return `${hrs}h${mins}`;
};

const getOfflineMiniInsight = (metrics: any, t: (k: string) => string): string | null => {
  if (!metrics || (metrics.cpu === undefined && metrics.mem === undefined)) {
    return null;
  }
  const cpu = metrics.cpu;
  const mem = metrics.mem;
  const disk = metrics.disk;

  const parts: string[] = [];
  if (cpu !== null) parts.push(`CPU ${cpu}%`);
  if (mem !== null) parts.push(`RAM ${mem}%`);
  if (disk !== null) parts.push(`Disque ${disk}%`);

  if (parts.length === 0) return null;

  const base = t('servers.offline_last_metrics').replace('{parts}', parts.join(', '));

  if (mem !== null && mem >= 85 && cpu !== null && cpu >= 90) {
    return `${base} — ${t('servers.offline_oom_crash')}`;
  }
  if (mem !== null && mem >= 85) {
    return `${base} — ${t('servers.offline_oom')}`;
  }
  if (cpu !== null && cpu >= 90) {
    return `${base} — ${t('servers.offline_cpu_crash')}`;
  }
  if (disk !== null && disk >= 90) {
    return `${base} — ${t('servers.offline_disk_full')}`;
  }
  return base;
};

const getResourceColor = (val: number, type: 'cpu' | 'mem' | 'disk') => {
  const limits = {
    cpu: { warn: 40, crit: 75 },
    mem: { warn: 60, crit: 80 },
    disk: { warn: 65, crit: 85 },
  };
  const { warn, crit } = limits[type];
  if (val >= crit) return 'progress-bar-fill-danger';
  if (val >= warn) return 'progress-bar-fill-warning';
  return 'progress-bar-fill-success';
};

export const ServersPage: React.FC = () => {
  const { t } = useLocale();
  usePageTitle(t('page_title.servers'));
  const { nodes, isLoading, fetchNodes } = useNodeStore();
  const [search, setSearch] = useState('');
  const [bulkStatus, setBulkStatus] = useState<Record<string, any>>({});
  const navigate = useNavigate();
  const { isAdmin } = usePermission();
  const addToast = useToastStore((s) => s.addToast);
  const [renameNode, setRenameNode] = useState<Node | null>(null);
  const [deleteNode, setDeleteNode] = useState<Node | null>(null);
  const setAddNodeModalOpen = useLayoutStore((s) => s.setAddNodeModalOpen);

  const fetchBulkMetrics = async () => {
    try {
      const data = await api<{ statuses: Record<string, any> }>('/api/nodes/bulk/status');
      if (data && data.statuses) {
        setBulkStatus(data.statuses);
      }
    } catch (err) {
      console.error('Failed to fetch bulk statuses:', err);
    }
  };

  useEffect(() => {
    fetchNodes();
    fetchBulkMetrics();
  }, []);

  const filtered = nodes.filter((n: Node) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (n.hostname || '').toLowerCase().includes(q) ||
      (n.os || '').toLowerCase().includes(q) ||
      n.id.toLowerCase().includes(q)
    );
  });

  const activeCount = nodes.length;

  const formatTime = (ts: number | null): string => {
    if (!ts) return '—';
    const seconds = Math.floor((Date.now() / 1000) - ts);
    if (seconds < 60) return `il y a ${seconds}s`;
    if (seconds < 3600) return `il y a ${Math.floor(seconds / 60)}min`;
    if (seconds < 86400) return `il y a ${Math.floor(seconds / 3600)}h`;
    return `il y a ${Math.floor(seconds / 86400)}j`;
  };

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold uppercase tracking-wider text-text-1 flex items-center gap-2">
            <Server className="w-5 h-5 text-accent" />
            {t('nav.servers')}
          </h1>
          <p className="text-[10px] text-text-3 font-semibold uppercase tracking-wider mt-0.5">
            {activeCount} serveur{activeCount !== 1 ? 's' : ''} actif{activeCount !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-3" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('servers.search_placeholder')}
            className="w-full bg-surface border border-border-strong/20 rounded-lg pl-9 pr-3 py-2 text-xs text-text-1 placeholder:text-text-3 focus:outline-none focus:border-accent transition-colors"
          />
        </div>
      </div>

      {isLoading && nodes.length === 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-surface-2 border border-border-strong/20 rounded-xl p-4 animate-pulse space-y-3">
              <div className="h-4 bg-surface-3 rounded w-3/4" />
              <div className="h-3 bg-surface-3 rounded w-1/2" />
              <div className="h-3 bg-surface-3 rounded w-2/3" />
            </div>
          ))}
        </div>
      )}

      {!isLoading && filtered.length === 0 && (
        <EmptyState
          icon={<Server className="w-12 h-12" />}
          title={search ? t('servers.empty_search_title') : t('servers.empty_title')}
          description={search ? t('servers.empty_search_description') : t('servers.empty_description')}
          action={!search ? {
            label: t('servers.add_server'),
            onClick: () => setAddNodeModalOpen(true),
          } : undefined}
        />
      )}

      {filtered.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map((node: Node) => {
            const metrics = bulkStatus[node.id];
            return (
              <div
                key={node.id}
                onClick={() => navigate(`/nodes/${node.id}`)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/nodes/${node.id}`); }}
                className={clsx(
                  "bg-surface-2 border rounded-xl p-4 text-left transition-all duration-200 cursor-pointer group text-start flex flex-col justify-between min-h-[200px] w-full relative",
                  node.online
                    ? "border-border-strong/20 hover:border-accent/30 hover:bg-surface-2/80 card-glow-success"
                    : "border-severity-critical/20 hover:border-severity-critical/40 hover:bg-surface-2/80 card-glow-danger"
                )}
              >
                <div className="w-full">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <StatusDot state={node.state} />
                      <span className="text-sm font-bold text-text-1 break-all leading-tight flex-1 group-hover:text-accent transition-colors">
                        {node.hostname || node.name || node.id.substring(0, 8)}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={clsx(
                        'text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded',
                        node.online
                          ? 'bg-severity-ok/10 text-severity-ok'
                          : 'bg-severity-critical/10 text-severity-critical'
                      )}>
                        {node.online ? t('servers.badge_online') : t('servers.badge_offline')}
                      </span>
                      <KebabMenu
                        items={[
                          {
                            label: t('servers.menu.view_details'),
                            onClick: () => navigate(`/nodes/${node.id}`),
                          },
                          {
                            label: t('servers.menu.rename'),
                            onClick: () => setRenameNode(node),
                          },
                          {
                            label: t('servers.menu.settings'),
                            onClick: () => navigate(`/nodes/${node.id}?tab=settings`),
                          },
                          {
                            label: t('servers.menu.delete'),
                            danger: true,
                            hidden: !isAdmin,
                            onClick: () => setDeleteNode(node),
                          },
                        ]}
                      />
                    </div>
                  </div>

                  <div className="space-y-1.5 text-[11px] text-text-2">
                    {node.os && (
                      <div className="flex items-center gap-2">
                        <HardDrive className="w-3 h-3 text-text-3 shrink-0" />
                        <span className="truncate">{node.os}</span>
                      </div>
                    )}
                    {node.arch && (
                      <div className="flex items-center gap-2">
                        <Cpu className="w-3 h-3 text-text-3 shrink-0" />
                        <span>{node.arch}</span>
                      </div>
                    )}
                    {node.online && node.last_heartbeat && (
                      <div className="flex items-center gap-2">
                        <Clock className="w-3 h-3 text-text-3 shrink-0" />
                        <span>{t('servers.last_contact', { time: formatTime(node.last_heartbeat) })}</span>
                      </div>
                    )}
                  </div>

                  {node.online && (
                    <div className="mt-4 pt-4 border-t border-border-strong/10 space-y-2.5">
                      <div className="space-y-1">
                        <div className="flex justify-between text-[10px] font-bold">
                          <span className="text-text-2 flex items-center gap-1"><Cpu className="w-3 h-3 text-text-3" /> {t('card.cpu')}</span>
                          <span className="font-mono text-text-1">{(metrics && metrics.cpu !== null && metrics.cpu !== undefined) ? `${Math.round(metrics.cpu)}%` : '—'}</span>
                        </div>
                        <div className="progress-bar-track bg-surface-3">
                          <div
                            className={clsx('progress-bar-fill', (metrics && metrics.cpu !== null && metrics.cpu !== undefined) && getResourceColor(metrics.cpu, 'cpu'))}
                            style={{ width: (metrics && metrics.cpu !== null && metrics.cpu !== undefined) ? `${metrics.cpu}%` : '0%' }}
                          />
                        </div>
                      </div>
                      <div className="space-y-1">
                        <div className="flex justify-between text-[10px] font-bold">
                          <span className="text-text-2 flex items-center gap-1"><Cpu className="w-3 h-3 text-text-3" /> {t('card.ram')}</span>
                          <span className="font-mono text-text-1">{(metrics && metrics.mem !== null && metrics.mem !== undefined) ? `${Math.round(metrics.mem)}%` : '—'}</span>
                        </div>
                        <div className="progress-bar-track bg-surface-3">
                          <div
                            className={clsx('progress-bar-fill', (metrics && metrics.mem !== null && metrics.mem !== undefined) && getResourceColor(metrics.mem, 'mem'))}
                            style={{ width: (metrics && metrics.mem !== null && metrics.mem !== undefined) ? `${metrics.mem}%` : '0%' }}
                          />
                        </div>
                      </div>
                      <div className="space-y-1">
                        <div className="flex justify-between text-[10px] font-bold">
                          <span className="text-text-2 flex items-center gap-1"><HardDrive className="w-3 h-3 text-text-3" /> {t('card.disk')}</span>
                          <span className="font-mono text-text-1">{(metrics && metrics.disk !== null && metrics.disk !== undefined) ? `${Math.round(metrics.disk)}%` : '—'}</span>
                        </div>
                        <div className="progress-bar-track bg-surface-3">
                          <div
                            className={clsx('progress-bar-fill', (metrics && metrics.disk !== null && metrics.disk !== undefined) && getResourceColor(metrics.disk, 'disk'))}
                            style={{ width: (metrics && metrics.disk !== null && metrics.disk !== undefined) ? `${metrics.disk}%` : '0%' }}
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {!node.online && (
                    <div className="mt-4 pt-4 border-t border-border-strong/10 space-y-2.5">
                      <div className="text-[11px] text-severity-critical font-medium space-y-1">
                        <div className="flex items-center gap-1.5 font-semibold">
                          <Clock className="w-3.5 h-3.5 shrink-0" />
                          <span>{t('servers.offline_since', { duration: formatOfflineDuration(node.last_heartbeat) })}</span>
                        </div>
                        {node.last_heartbeat && (
                          <div className="text-[10px] text-text-3 font-mono pl-5">
                            {t('servers.last_heartbeat_at', { time: formatHeartbeatTime(node.last_heartbeat) })}
                          </div>
                        )}
                      </div>
                      {metrics && (metrics.cpu !== null || metrics.mem !== null) && (
                        <div className="p-2.5 rounded bg-severity-critical/5 border border-severity-critical/10 text-[10px] text-text-2 w-full whitespace-normal">
                          <span className="font-semibold text-text-1 block mb-1">{t('servers.offline_diagnostic')}</span>
                          <span>{getOfflineMiniInsight(metrics, t)}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="mt-4 pt-3 border-t border-border-strong/10 w-full">
                  <span className="text-[9px] font-mono text-text-3">
                    {t('common.id_prefix', { id: `${node.id.substring(0, 12)}…` })}
                  </span>
                </div>
              </div>
            );
          })}

          <div
            onClick={() => setAddNodeModalOpen(true)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter') setAddNodeModalOpen(true); }}
            className="bg-surface border-2 border-dashed border-accent/30 hover:bg-surface-2 rounded-xl p-4 text-center transition-all duration-200 cursor-pointer group flex flex-col items-center justify-center min-h-[200px] w-full card-glow-accent"
          >
            <div className="flex flex-col items-center justify-center space-y-3">
              <div className="p-3 rounded-full bg-accent/5 group-hover:bg-accent/10 transition-colors">
                <Plus className="w-6 h-6 text-accent group-hover:scale-110 transition-transform duration-200" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-text-1 group-hover:text-accent transition-colors">
                  {t('servers.add_server')}
                </h3>
                <p className="text-[11px] text-text-3 mt-1 max-w-[200px] leading-relaxed">
                  {t('servers.empty_description')}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {renameNode && (
        <RenameNodeModal
          node={renameNode}
          onClose={() => setRenameNode(null)}
        />
      )}

      {deleteNode && (
        <ConfirmDeleteModal
          title={t('settings.confirm.revoke_title')}
          message={t('settings.confirm.revoke_message')}
          confirmWord={deleteNode.hostname || deleteNode.name}
          confirmLabel={t('settings.confirm.revoke_action')}
          uninstallCommand={`curl -sSL ${window.location.origin}/api/nodes/kickstart.sh | sudo sh -s -- --uninstall`}
          onClose={() => setDeleteNode(null)}
          onConfirm={async () => {
            const id = deleteNode.id;
            const name = deleteNode.hostname || deleteNode.name;
            try {
              await nodeMutations.deleteNode(id);
              addToast('success', t('servers.toast.deleted'), name);
              setDeleteNode(null);
            } catch (err) {
              addToast('error', t('settings.error'), err instanceof Error ? err.message : String(err));
              throw err;
            }
          }}
        />
      )}
    </div>
  );
};
