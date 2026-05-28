import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router';
import { Server, Terminal, MessageSquare, ShieldAlert, Layers } from 'lucide-react';
import { useNodeStore } from '../store/nodeStore';
import { useAuthStore } from '../store/authStore';
import { useChatStore } from '../store/chatStore';
import { useLocale } from '../i18n';
import { usePolling } from '../hooks/usePolling';
import { api } from '../hooks/useApi';

// Component imports
import { HeroBanner } from '../components/dashboard/HeroBanner';
import { SwimLane } from '../components/dashboard/SwimLane';
import { ServerCard } from '../components/dashboard/ServerCard';
import { ContainerCard } from '../components/dashboard/ContainerCard';
import { InsightCard } from '../components/dashboard/InsightCard';
import { ActivityCard } from '../components/dashboard/ActivityCard';
import { TrendChart } from '../components/dashboard/TrendChart';
import { EmptyState } from '../components/ui/EmptyState';
import { CardSkeleton } from '../components/ui/CardSkeleton';
import { ProposalModal } from '../components/modals/ProposalModal';
import { AllChatsModal } from '../components/modals/AllChatsModal';

interface MetricsMap {
  [nodeId: string]: {
    cpu: number;
    mem: number;
    disk: number;
    uptime: string;
    loading: boolean;
  };
}

export const Dashboard: React.FC = () => {
  const { t } = useLocale();
  const navigate = useNavigate();
  const { nodes, fetchNodes, selectNode, isLoading: isNodesLoading } = useNodeStore();
  const { accessToken } = useAuthStore();

  const {
    sessions: chatSessions,
    fetchSessions
  } = useChatStore();

  // Local state
  const [proposals, setProposals] = useState<any[]>([]);
  const [isProposalsLoading, setIsProposalsLoading] = useState(false);
  const [nodeMetrics, setNodeMetrics] = useState<MetricsMap>({});
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);

  // Aggregated lists
  const [containers, setContainers] = useState<any[]>([]);
  const [isContainersLoading, setIsContainersLoading] = useState(false);
  const [insights, setInsights] = useState<any[]>([]);
  const [isInsightsLoading, setIsInsightsLoading] = useState(false);

  // Modals state
  const [selectedProposal, setSelectedProposal] = useState<any | null>(null);
  const [showAllChatsModal, setShowAllChatsModal] = useState(false);

  useEffect(() => {
    selectNode('all');
    fetchNodes();
    fetchSessions();
  }, [selectNode, fetchNodes, fetchSessions]);

  // Fetch proposals
  const fetchProposals = async () => {
    if (!accessToken) return;
    setIsProposalsLoading(true);
    try {
      const data = await api<any[]>('/api/chat/proposals');
      if (data) {
        setProposals(data);
      }
    } catch (e) {
      console.error('Failed to load proposals:', e);
    } finally {
      setIsProposalsLoading(false);
    }
  };

  useEffect(() => {
    fetchProposals();
  }, [accessToken]);

  // Global polling for active lists
  usePolling('dashboard_lists', () => {
    fetchNodes();
    fetchProposals();
    fetchSessions();
  }, 30000);

  // Fetch live metrics, containers, and insights for online nodes
  useEffect(() => {
    const onlineNodes = nodes.filter((n) => n.online);
    if (onlineNodes.length === 0) {
      setContainers([]);
      setInsights([]);
      return;
    }

    const fetchAllNodeMetrics = async () => {
      // Set initial loading states
      setNodeMetrics((prev) => {
        const next = { ...prev };
        onlineNodes.forEach((node) => {
          if (!next[node.id]) {
            next[node.id] = { cpu: 0, mem: 0, disk: 0, uptime: 'N/A', loading: true };
          }
        });
        return next;
      });

      const fetchedMetrics: MetricsMap = {};
      await Promise.all(
        onlineNodes.map(async (node) => {
          try {
            const data = await api<any>(`/api/nodes/${node.id}/stats?limit=1`);
            if (data && data.snapshots && data.snapshots.length > 0) {
              const snap = data.snapshots[0];
              const cpu = Math.round(snap.cpu_percent);
              const mem = Math.round(snap.mem_percent);
              const disk = Math.round(snap.disk_percent);
              
              const uptSec = snap.uptime_seconds;
              const days = Math.floor(uptSec / 86400);
              const hrs = Math.floor((uptSec % 86400) / 3600);
              const uptimeStr = days > 0 ? `${days}j ${hrs}h` : `${hrs}h`;

              fetchedMetrics[node.id] = { cpu, mem, disk, uptime: uptimeStr, loading: false };
            } else {
              fetchedMetrics[node.id] = { cpu: 0, mem: 0, disk: 0, uptime: 'N/A', loading: false };
            }
          } catch (e) {
            fetchedMetrics[node.id] = { cpu: 0, mem: 0, disk: 0, uptime: 'Erreur', loading: false };
          }
        })
      );

      setNodeMetrics((prev) => ({ ...prev, ...fetchedMetrics }));
      setLastUpdated(Date.now());
    };

    const fetchAllContainers = async () => {
      setIsContainersLoading(true);
      try {
        const list = await Promise.all(
          onlineNodes.map(async (node) => {
            try {
              const data = await api<{ containers: any[] }>(`/api/nodes/${node.id}/containers`);
              if (data && data.containers) {
                return data.containers.map((c) => ({
                  ...c,
                  nodeId: node.id,
                  nodeName: node.name
                }));
              }
            } catch (err) {
              console.error(`Failed to fetch containers for ${node.name}:`, err);
            }
            return [];
          })
        );
        setContainers(list.flat());
      } catch (err) {
        console.error('Failed to load aggregated containers:', err);
      } finally {
        setIsContainersLoading(false);
      }
    };

    const fetchAllInsights = async () => {
      setIsInsightsLoading(true);
      try {
        const list = await Promise.all(
          onlineNodes.map(async (node) => {
            try {
              const data = await api<{ insights: any[] }>(`/api/nodes/${node.id}/insights`);
              if (data && data.insights) {
                return data.insights.map((i) => ({
                  ...i,
                  nodeId: node.id,
                  nodeName: node.name
                }));
              }
            } catch (err) {
              console.error(`Failed to fetch insights for ${node.name}:`, err);
            }
            return [];
          })
        );
        setInsights(list.flat());
      } catch (err) {
        console.error('Failed to load aggregated insights:', err);
      } finally {
        setIsInsightsLoading(false);
      }
    };

    fetchAllNodeMetrics();
    fetchAllContainers();
    fetchAllInsights();
  }, [nodes]);

  const handleProposalUpdated = () => {
    setSelectedProposal(null);
    fetchProposals();
  };

  const handleSessionDeleted = () => {
    fetchSessions();
  };

  // Sorting Docker containers: crit/stopped first, then running
  const isRunning = (c: any) =>
    c.state.toLowerCase() === 'running' || c.status.toLowerCase().includes('up');

  const sortedContainers = [...containers].sort((a, b) => {
    const aRun = isRunning(a);
    const bRun = isRunning(b);
    if (!aRun && bRun) return -1;
    if (aRun && !bRun) return 1;
    return 0;
  });

  return (
    <div className="flex-grow space-y-6 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
      {/* Hero Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/40 pb-5">
        <div>
          <h1 className="text-xl font-bold text-ink-primary tracking-tight">
            {t('nav.dashboard')}
          </h1>
          <p className="text-xs text-ink-secondary mt-0.5">
            {nodes.length <= 1
              ? "Gérez votre serveur avec l'assistance autonome de Vigile."
              : "Gérez votre infrastructure de serveurs avec l'assistance autonome de Vigile."}
          </p>
        </div>
      </div>

      {/* Global Health Status Banner */}
      <HeroBanner nodes={nodes} lastUpdated={lastUpdated} />

      {/* horizontal lists wrapper */}
      <div className="space-y-8 mt-6">
        {/* Row 1: Servers */}
        <SwimLane
          title={t('swim.servers')}
          icon={Server}
          isLoading={isNodesLoading}
          skeletonComponent={<CardSkeleton />}
        >
          {nodes.length === 0 ? (
            <EmptyState
              compact
              icon={<Server size={32} />}
              title="Aucun serveur"
              description="Ajoutez votre premier serveur dans le menu Administration."
            />
          ) : (
            nodes.map((node) => (
              <ServerCard
                key={node.id}
                node={node}
                metrics={nodeMetrics[node.id]}
                onClick={() => navigate(`/nodes/${node.id}`)}
              />
            ))
          )}
        </SwimLane>

        {/* Row 2: Containers */}
        {nodes.some(n => n.online) && (
          <SwimLane
            title={t('swim.containers')}
            icon={Layers}
            isLoading={isContainersLoading}
            skeletonComponent={<CardSkeleton />}
          >
            {sortedContainers.length === 0 ? (
              <EmptyState
                compact
                icon={<Layers size={32} />}
                title="Aucun conteneur"
                description="Aucun conteneur Docker détecté sur les serveurs actifs."
              />
            ) : (
              sortedContainers.map((container) => (
                <ContainerCard
                  key={`${container.nodeId}-${container.id}`}
                  nodeId={container.nodeId}
                  nodeName={container.nodeName}
                  container={container}
                />
              ))
            )}
          </SwimLane>
        )}

        {/* Row 3: Insights IA */}
        {nodes.some(n => n.online) && (
          <SwimLane
            title={t('swim.insights')}
            icon={ShieldAlert}
            isLoading={isInsightsLoading}
            skeletonComponent={<CardSkeleton />}
          >
            {insights.length === 0 ? (
              <EmptyState
                compact
                icon={<ShieldAlert size={32} />}
                title="Aucune alerte"
                description="Tous vos serveurs actifs sont en bonne santé."
              />
            ) : (
              insights.map((insight, idx) => (
                <InsightCard
                  key={`${insight.nodeId}-${idx}`}
                  nodeId={insight.nodeId}
                  nodeName={insight.nodeName}
                  insight={insight}
                />
              ))
            )}
          </SwimLane>
        )}

        {/* Row 4: Tasks (Proposals) */}
        <SwimLane
          title={t('swim.activity')}
          icon={Terminal}
          onSeeAll={() => navigate('/proposals')}
          seeAllLabel={t('dash.view_all')}
          isLoading={isProposalsLoading}
          skeletonComponent={<CardSkeleton />}
        >
          {proposals.length === 0 ? (
            <EmptyState
              compact
              icon={<Terminal size={32} />}
              title="Aucune tâche récente"
              description="Les propositions de commandes apparaîtront ici."
            />
          ) : (
            proposals.slice(0, 10).map((prop) => (
              <ActivityCard
                key={prop.id}
                proposal={prop}
                nodeName={nodes.find((n) => n.id === prop.node_id)?.name || prop.node_id}
                onClick={() => setSelectedProposal(prop)}
              />
            ))
          )}
        </SwimLane>

        {/* Row 5: Chat Sessions */}
        <SwimLane
          title="Conversations Récentes"
          icon={MessageSquare}
          onSeeAll={() => setShowAllChatsModal(true)}
          seeAllLabel={t('dash.view_all')}
        >
          {chatSessions.length === 0 ? (
            <EmptyState
              compact
              icon={<MessageSquare size={32} />}
              title="Aucun chat récent"
              description="Vos conversations avec l'IA s'afficheront ici."
            />
          ) : (
            chatSessions.slice(0, 10).map((session) => (
              <Link
                key={session.id}
                to={`/chat/${session.id}`}
                className="w-[240px] h-[130px] shrink-0 card p-4 flex flex-col justify-between hover:border-border-hover hover:bg-surface-1 transition-all duration-200"
              >
                <div className="flex items-center gap-1 border-b border-border/40 pb-1">
                  <MessageSquare size={10} className="text-accent-primary" />
                  <span className="text-[10px] font-bold text-ink-muted truncate">
                    {session.node_id
                      ? (nodes.find((n) => n.id === session.node_id)?.name || 'Serveur')
                      : 'Global'}
                  </span>
                </div>
                <div className="my-1.5 text-xs font-bold text-ink-primary line-clamp-2 leading-snug">
                  {session.title}
                </div>
                <div className="text-[10px] text-ink-muted font-mono italic">
                  {new Date(session.updated_at * 1000).toLocaleDateString('fr-FR')}
                </div>
              </Link>
            ))
          )}
        </SwimLane>
      </div>

      {/* Uptime Trend sparklines */}
      <TrendChart nodes={nodes} />

      {/* Modal: Proposal Detail */}
      {selectedProposal && (
        <ProposalModal
          proposal={selectedProposal}
          onClose={() => setSelectedProposal(null)}
          onProposalUpdated={handleProposalUpdated}
        />
      )}

      {/* Modal: All Chats History */}
      {showAllChatsModal && (
        <AllChatsModal
          chatSessions={chatSessions}
          onClose={() => setShowAllChatsModal(false)}
          onSessionDeleted={handleSessionDeleted}
        />
      )}
    </div>
  );
};
