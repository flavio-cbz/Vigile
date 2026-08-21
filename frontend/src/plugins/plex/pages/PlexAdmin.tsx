import React, { useState, useCallback, useEffect } from 'react';
import type { PluginAPI } from '../../../types/plugins';
import { useNodeStore } from '../../../store/nodeStore';
import { useAuthStore } from '../../../store/authStore';
import { Play, Settings, RefreshCw, Server, Users, Zap, HardDrive, Activity, Globe, X } from 'lucide-react';
import { useBlockData } from '../../../hooks/useBlockData';
import { PageHeader } from '../../../components/blocks/PageHeader';
import { NodePills } from '../../../components/blocks/NodeSelector';
import { MetricCardsGrid } from '../../../components/blocks/MetricCardsGrid';
import { Tabs } from '../../../components/blocks/Tabs';
import { Banner } from '../../../components/blocks/Banner';
import { ExternalAuthPopup } from '../../../components/blocks/ExternalAuthPopup';
import { GroupedRadio, ToggleField } from '../../../components/blocks/form-fields';
import { PlexSessionsTab } from '../components/PlexSessionsTab';
import { PlexTranscodesTab } from '../components/PlexTranscodesTab';
import { PlexFilesTab } from '../components/PlexFilesTab';
import { PlexHistoryTab } from '../components/PlexHistoryTab';
import { PlexUsersTab } from '../components/PlexUsersTab';

function formatBytes(bytes: number): string {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'Ko', 'Mo', 'Go', 'To'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const val = (bytes / Math.pow(k, i)).toFixed(1);
  return `${val} ${sizes[i]}`;
}

interface PlexAdminProps {
  api: PluginAPI;
}

export const PlexAdmin: React.FC<PlexAdminProps> = ({ api }) => {
  const { nodes, isLoading: isLoadingNodes, fetchNodes } = useNodeStore();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';

  const [selectedNodeId, setSelectedNodeId] = useState<string>('');
  const [plexActiveTab, setPlexActiveTab] = useState('sessions');
  const [liveAutoRefresh, setLiveAutoRefresh] = useState<boolean>(true);
  const [pollMs, setPollMs] = useState<number>(3_000);
  const [showConfigModal, setShowConfigModal] = useState(false);

  useEffect(() => { fetchNodes(); }, [fetchNodes]);

  useEffect(() => {
    if (nodes.length > 0) {
      if (!selectedNodeId || !nodes.some((n) => n.id === selectedNodeId)) {
        setSelectedNodeId(nodes[0].id);
      }
    } else if (selectedNodeId) {
      setSelectedNodeId('');
    }
  }, [nodes, selectedNodeId]);

  const activeNodeId = selectedNodeId || undefined;

  const { data: detectData, isLoading: detectLoading, error: detectError, mutate: mutateDetect } = useBlockData<{
    detected: boolean;
    configured: boolean;
    port: number;
    type: string;
    status?: string;
    container_name?: string;
    service_name?: string;
    server_url?: string;
    server_name?: string;
  }>(
    activeNodeId
      ? { command: 'plex.detect', params: { node_id: activeNodeId } }
      : null,
    { revalidateInterval: 30_000 },
  );

  const isConfigured = detectData?.detected === true && detectData?.configured === true;
  const isDetected = detectData?.detected === true;

  const { data: sessionsData, isLoading: sessionsLoading, mutate: mutateSessions, error: sessionsError } = useBlockData<{
    sessions: Array<{
      session_key?: string;
      title: string;
      grandparent_title?: string;
      parent_title?: string;
      user: string;
      user_thumb?: string;
      player_device?: string;
      player_platform?: string;
      state: 'playing' | 'paused' | 'buffering';
      progress_percent?: number;
      quality_profile?: string;
      bandwidth_kbps?: number;
      transcode: boolean;
      video_decision?: string;
      speed?: number;
      thumb?: string;
    }>;
  }>(
    isConfigured && activeNodeId
      ? { command: 'plex.sessions', params: { node_id: activeNodeId } }
      : null,
    { revalidateInterval: pollMs },
  );

  const { data: transcodesData, mutate: mutateTranscodes, error: transcodesError } = useBlockData<{
    transcodes: Array<{
      session_key: string;
      title: string;
      grandparent_title?: string;
      user: string;
      device: string;
      video_decision: string;
      audio_decision: string;
      video_codec?: string;
      audio_codec?: string;
      speed: number;
      progress: number;
      throttled: boolean;
      bandwidth_kbps: number;
      context: string;
    }>;
    downloads: Array<{
      id: string;
      title: string;
      user: string;
      state: string;
      progress: number;
      size_bytes: number;
      device_name: string;
    }>;
  }>(
    isConfigured && activeNodeId
      ? { command: 'plex.transcodes', params: { node_id: activeNodeId } }
      : null,
    { revalidateInterval: pollMs },
  );

  const hasPlexApiError = Boolean(sessionsError ?? transcodesError);

  useEffect(() => {
    setPollMs(liveAutoRefresh && !hasPlexApiError ? 3_000 : 30_000);
  }, [liveAutoRefresh, hasPlexApiError]);

  const { data: librariesData } = useBlockData<{
    libraries: Array<{ title: string; type: string }>;
  }>(
    isConfigured && activeNodeId && (plexActiveTab === 'libraries' || plexActiveTab === 'files')
      ? { command: 'plex.library', params: { node_id: activeNodeId } }
      : null,
  );

  const { data: usersData } = useBlockData<{
    users: Array<{
      id?: string;
      name: string;
      default_subtitle_language?: string;
      last_seen_at?: number | null;
      is_online?: boolean;
    }>;
  }>(
    isConfigured && activeNodeId && plexActiveTab === 'users'
      ? { command: 'plex.users', params: { node_id: activeNodeId } }
      : null,
  );

  const { data: filesData } = useBlockData<{
    libraries: Array<{
      key: string;
      title: string;
      type: string;
      locations: string[];
      total_files: number;
      total_size_bytes: number;
    }>;
    largest_files: Array<{
      section: string;
      section_type: string;
      title: string;
      file_path: string;
      size_bytes: number;
      container?: string;
      resolution?: string;
      codec?: string;
      added_at?: number;
    }>;
    total_storage_bytes: number;
  }>(
    isConfigured && activeNodeId && plexActiveTab === 'files'
      ? { command: 'plex.files', params: { node_id: activeNodeId } }
      : null,
  );

  const [historyOffset, setHistoryOffset] = useState(0);
  const [historyQuery, setHistoryQuery] = useState('');
  const [historyMediaType, setHistoryMediaType] = useState('');

  const historyParams: Record<string, unknown> = {
    node_id: activeNodeId,
    limit: 50,
    offset: historyOffset,
  };
  if (historyQuery) historyParams.query = historyQuery;
  if (historyMediaType) historyParams.media_type = historyMediaType;

  const { data: historyData, isLoading: historyLoading } = useBlockData<{
    history: Array<{
      id: number;
      title: string;
      grandparent_title?: string;
      user: string;
      device: string;
      viewed_at: number;
      duration_watched_s: number;
      progress_percent: number;
      media_type: string;
    }>;
    total: number;
    limit: number;
    offset: number;
  }>(
    isConfigured && activeNodeId && plexActiveTab === 'history'
      ? { command: 'plex.history', params: historyParams }
      : null,
  );

  const sessions = sessionsData?.sessions ?? [];
  const transcodes = transcodesData?.transcodes ?? [];
  const downloads = transcodesData?.downloads ?? [];
  const libraries = librariesData?.libraries ?? [];
  const users = usersData?.users ?? [];
  const fileLibraries = filesData?.libraries ?? [];
  const largestFiles = filesData?.largest_files ?? [];
  const totalStorageBytes = filesData?.total_storage_bytes ?? 0;
  const history = historyData?.history ?? [];
  const historyTotal = historyData?.total ?? 0;

  const totalTranscodesDownloads = transcodes.length + downloads.length;
  const busy = sessionsLoading && !sessionsData;

  const handleRefresh = useCallback(() => {
    void mutateDetect();
    void mutateSessions();
    void mutateTranscodes();
  }, [mutateDetect, mutateSessions, mutateTranscodes]);

  const handleKillSession = useCallback(async (sessionKey: string) => {
    if (!activeNodeId) return;
    try {
      await api.fetch(`/${activeNodeId}/sessions/${sessionKey}`, { method: 'DELETE' });
      api.toast(`Session ${sessionKey} interrompue !`, 'success');
      void mutateSessions();
    } catch {
      api.toast('Erreur lors de l\'interruption de la session.', 'error');
    }
  }, [api, activeNodeId, mutateSessions]);

  const handleScanLibrarySection = useCallback(async (sectionId: string) => {
    if (!activeNodeId) return;
    try {
      await api.fetch(`/${activeNodeId}/library/${sectionId}/scan`, { method: 'POST' });
      api.toast('Scan de la bibliothèque Plex démarré !', 'success');
    } catch {
      api.toast('Erreur lors du déclenchement du scan.', 'error');
    }
  }, [api, activeNodeId]);

  const handleHistorySearch = useCallback((query: string, mediaType?: string) => {
    setHistoryQuery(query);
    setHistoryMediaType(mediaType || '');
    setHistoryOffset(0);
  }, []);

  const tabList = [
    { id: 'sessions', label: 'Lectures', icon: <Play className="w-3.5 h-3.5" />, badge: sessions.length },
    { id: 'transcodes', label: 'Transcodages & Téléchargements', icon: <Zap className="w-3.5 h-3.5" />, badge: totalTranscodesDownloads },
    { id: 'files', label: 'Gestion des Fichiers', icon: <HardDrive className="w-3.5 h-3.5" /> },
    { id: 'history', label: 'Historique de Lecture', icon: <Activity className="w-3.5 h-3.5" /> },
    { id: 'users', label: 'Utilisateurs', icon: <Users className="w-3.5 h-3.5" />, badge: users.length },
  ];

  const metricCards = [
    { label: 'Lectures Actives', value: sessions.length, icon: <Activity className="w-4 h-4 text-accent" /> },
    { label: 'Transcode & Downloads', value: totalTranscodesDownloads, delta: transcodes.length > 0 ? `(${transcodes.length} active)` : undefined, deltaColor: 'neutral' as const, icon: <Zap className="w-4 h-4 text-accent" /> },
    { label: 'Bibliothèques & Stockage', value: `${libraries.length} `, delta: `(${formatBytes(totalStorageBytes)})`, deltaColor: 'neutral' as const, icon: <HardDrive className="w-4 h-4 text-accent" /> },
    { label: 'Utilisateurs & Historique', value: users.length, icon: <Users className="w-4 h-4 text-blue-400" /> },
  ];

  const [customUrlMode, setCustomUrlMode] = useState(false);
  const [customServerUrl, setCustomServerUrl] = useState('');
  const [selectedServerUrl, setSelectedServerUrl] = useState('');
  const [selectedServerName, setSelectedServerName] = useState('');
  const [servers, setServers] = useState<Array<{ name: string; clientIdentifier: string; owned: boolean; connections: Array<{ uri: string; local: boolean }> }>>([]);
  const [loadingServers, setLoadingServers] = useState(false);
  const [savingServer, setSavingServer] = useState(false);

  const fetchPlexServers = useCallback(async () => {
    setLoadingServers(true);
    try {
      const res = await api.fetch<{ servers: typeof servers }>('/servers');
      setServers(res?.servers || []);
    } catch {
      // Silently fail — servers list is informational
    } finally {
      setLoadingServers(false);
    }
  }, [api]);

  useEffect(() => {
    if (isConfigured) fetchPlexServers();
  }, [isConfigured, fetchPlexServers]);

  const handleSaveServerConfig = useCallback(async () => {
    setSavingServer(true);
    try {
      const targetUrl = customUrlMode ? customServerUrl.trim() : selectedServerUrl.trim();
      await api.fetch('/config/server', {
        method: 'POST',
        body: JSON.stringify({ server_url: targetUrl, server_name: selectedServerName }),
      });
      api.toast('Configuration du serveur Plex enregistrée !', 'success');
      setShowConfigModal(false);
      handleRefresh();
    } catch {
      api.toast('Erreur lors de la sauvegarde du serveur Plex.', 'error');
    } finally {
      setSavingServer(false);
    }
  }, [api, customUrlMode, customServerUrl, selectedServerUrl, selectedServerName, handleRefresh]);

  return (
    <div className="mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-8 space-y-6 pb-12 animate-fade-in">
      <PageHeader
        title="Plex Media Server"
        subtitle="Supervision complète du streaming, des transcodages, des fichiers et de l'historique."
        icon={<Play className="w-5 h-5 fill-accent" />}
        actions={
          <div className="flex items-center gap-2.5">
            <ToggleField
              name="live-refresh"
              label={liveAutoRefresh ? 'LIVE (3s)' : 'PAUSE'}
              checked={liveAutoRefresh}
              onChange={setLiveAutoRefresh}
            />
            {isAdmin && (
              <button
                onClick={() => setShowConfigModal(true)}
                className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-border-strong/50 bg-surface-2 hover:bg-surface-hover/80 text-text-1 font-mono text-xs font-semibold uppercase tracking-wider transition-colors duration-150 disabled:opacity-50 cursor-pointer"
              >
                <Settings className="w-3.5 h-3.5 text-accent" />
                Configurer Plex
              </button>
            )}
            <button
              onClick={handleRefresh}
              disabled={busy}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-border-strong/50 bg-surface-2 hover:bg-surface-hover/80 text-text-1 font-mono text-xs font-semibold uppercase tracking-wider transition-colors duration-150 disabled:opacity-50 cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} />
              Rafraîchir
            </button>
          </div>
        }
      />

      <NodePills
        nodes={nodes.map((n) => ({ id: n.id, name: n.name, online: n.online }))}
        selected={selectedNodeId}
        onChange={setSelectedNodeId}
        isLoading={isLoadingNodes}
      />

      {nodes.length === 0 && !isLoadingNodes && (
        <Banner variant="info" title="Aucun nœud disponible" message="Aucun serveur ou agent (Worker) n'est actuellement connecté à votre instance Vigile." />
      )}

      {selectedNodeId && detectLoading && !detectData && (
        <div className="flex flex-col items-center justify-center h-48 gap-3">
          <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-accent border-border-strong"></div>
          <span className="text-text-3 font-mono text-xs">Détection du service Plex en cours...</span>
        </div>
      )}

      {selectedNodeId && detectError && !detectData && (
        <Banner
          variant="error"
          title="Erreur lors de la détection de Plex"
          message={`Impossible de récupérer l'état de Plex : ${detectError.message}`}
          action={{ label: 'Réessayer', onClick: () => void mutateDetect() }}
        />
      )}

      {selectedNodeId && !detectLoading && !isConfigured && isDetected && (
        <Banner
          variant="warning"
          title="Plex est détecté mais non authentifié"
          message="Liez Vigile à votre compte Plex.tv pour importer vos serveurs et consulter les flux en direct."
          action={isAdmin ? { label: 'Lier Plex.tv Maintenant', onClick: () => setShowConfigModal(true) } : undefined}
        />
      )}

      {selectedNodeId && !detectLoading && !detectError && !isDetected && detectData && (
        <Banner
          variant="warning"
          title="Plex Non Détecté sur ce nœud"
          message="Aucune instance de Plex n'a été détectée sur le nœud sélectionné. Si votre serveur Plex s'exécute sur une autre machine ou une adresse IP dédiée, associez votre compte Plex.tv pour configurer le lien."
          action={isAdmin ? { label: 'Configurer Plex Maintenant', onClick: () => setShowConfigModal(true) } : undefined}
        />
      )}

      {selectedNodeId && isConfigured && (
        <div className="space-y-6">
          {hasPlexApiError && (
            <Banner
              variant="error"
              title="API Plex injoignable"
              message={`${sessionsError?.message ?? transcodesError?.message ?? ''} Le raffraîchissement repasse en mode lent (30s). Vérifiez que l'URL du serveur Plex est joignable depuis le Master et que le jeton est valide.`}
              action={isAdmin ? { label: 'Configurer Plex', onClick: () => setShowConfigModal(true) } : undefined}
            />
          )}

          <MetricCardsGrid cards={metricCards} />

          <div className="p-5 rounded-xl border border-border-strong/30 bg-surface-2/10 backdrop-blur-xs flex flex-col gap-4">
            <Tabs tabs={tabList} activeTab={plexActiveTab} onChange={setPlexActiveTab} />

            {plexActiveTab === 'sessions' && (
              <PlexSessionsTab
                sessions={sessions}
                nodeId={selectedNodeId}
                isAdmin={isAdmin}
                onKillSession={handleKillSession}
              />
            )}

            {plexActiveTab === 'transcodes' && (
              <PlexTranscodesTab transcodes={transcodes} downloads={downloads} />
            )}

            {plexActiveTab === 'files' && (
              <PlexFilesTab
                libraries={fileLibraries}
                largestFiles={largestFiles}
                totalStorageBytes={totalStorageBytes}
                nodeId={selectedNodeId}
                onScanLibrary={handleScanLibrarySection}
              />
            )}

            {plexActiveTab === 'history' && (
              <PlexHistoryTab
                history={history}
                total={historyTotal}
                limit={50}
                offset={historyOffset}
                onPageChange={setHistoryOffset}
                onSearchChange={handleHistorySearch}
                isLoading={historyLoading}
              />
            )}

            {plexActiveTab === 'users' && (
              <div className="flex flex-col gap-3">
                <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-text-2 flex items-center gap-2">
                  <Users className="w-4 h-4 text-blue-400" /> Comptes Utilisateurs Plex ({users.length})
                </h3>
                <PlexUsersTab users={users} />
              </div>
            )}
          </div>
        </div>
      )}

      {showConfigModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-surface border border-border-strong/40 rounded-2xl max-w-lg w-full p-6 flex flex-col gap-5 shadow-2xl animate-fade-in">
            <div className="flex items-center justify-between border-b border-border-strong/20 pb-4">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center text-accent">
                  <Settings className="w-4 h-4" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-text-1 font-mono">Configuration Plex</h2>
                  <p className="text-[11px] text-text-3 font-mono">Authentification et sélection du serveur</p>
                </div>
              </div>
              <button
                onClick={() => setShowConfigModal(false)}
                className="p-1.5 rounded-lg hover:bg-surface-hover text-text-3 hover:text-text-1 transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-bold uppercase text-accent flex items-center gap-1.5">
                  <Globe className="w-4 h-4" /> 1. Authentification Plex.tv
                </span>
                {isConfigured && (
                  <span className="text-[10px] font-mono font-bold bg-emerald-500/15 text-emerald-400 px-2 py-0.5 rounded-full border border-emerald-500/20">
                    Connecté
                  </span>
                )}
              </div>

              <ExternalAuthPopup
                context={{
                  params: {},
                  node_id: activeNodeId,
                  navigate: () => {},
                  navigateGlobal: () => {},
                  config: {},
                  toast: api.toast,
                  t: (key: string, params?: Record<string, string | number>) => api.t(key, params as Record<string, string> | undefined),
                  roles: isAdmin ? ['admin'] : ['viewer'],
                  api: {
                    fetch: api.fetch,
                    navigate: () => {},
                    navigateGlobal: () => {},
                    config: {},
                    t: (key: string, params?: Record<string, string | number>) => api.t(key, params as Record<string, string> | undefined),
                    toast: api.toast,
                  },
                }}
                config={{
                  start_command: 'plex.auth.start',
                  cancel_command: 'plex.auth.cancel',
                  status_channel: 'plex.auth.status',
                  popup_size: { w: 600, h: 700 },
                }}
                title="Connexion au compte Plex"
              />
            </div>

            <hr className="border-border-strong/15" />

            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-bold uppercase text-accent flex items-center gap-1.5">
                  <Server className="w-4 h-4" /> 2. Choix du Serveur
                </span>
                {loadingServers && <RefreshCw className="w-3.5 h-3.5 text-accent animate-spin" />}
              </div>

              {servers.length > 0 && !customUrlMode && (
                <div className="flex flex-col gap-2 max-h-40 overflow-y-auto pr-1">
                  {servers.map((srv) => (
                    <div key={srv.clientIdentifier} className="p-2.5 rounded-lg bg-surface-2/60 border border-border-strong/20 flex flex-col gap-1 text-xs">
                      <div className="font-bold text-text-1 flex items-center justify-between">
                        <span>{srv.name}</span>
                        {srv.owned && <span className="text-[10px] text-text-3 font-mono">Propriétaire</span>}
                      </div>
                      <GroupedRadio
                        name={`server_${srv.clientIdentifier}`}
                        options={srv.connections.map((conn) => ({
                          value: conn.uri,
                          label: conn.uri,
                        }))}
                        value={selectedServerUrl}
                        onChange={(uri) => {
                          setSelectedServerUrl(uri);
                          setSelectedServerName(srv.name);
                        }}
                      />
                    </div>
                  ))}
                </div>
              )}

              <ToggleField
                name="custom-url"
                label={customUrlMode ? '← Choisir parmi les serveurs détectés' : 'Saisir une adresse IP / URL sur mesure'}
                checked={customUrlMode}
                onChange={setCustomUrlMode}
                variant="link"
              />

              {customUrlMode && (
                <input
                  type="text"
                  value={customServerUrl}
                  onChange={(e) => setCustomServerUrl(e.target.value)}
                  placeholder="http://192.168.1.50:32400"
                  className="w-full px-3 py-1.5 text-xs rounded-lg border border-border bg-surface-2 text-text-1 font-mono focus:outline-none focus:border-accent"
                />
              )}
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setShowConfigModal(false)}
                className="px-4 py-1.5 text-xs font-mono font-semibold text-text-3 hover:text-text-1 transition-colors cursor-pointer"
              >
                Annuler
              </button>
              <button
                onClick={handleSaveServerConfig}
                disabled={savingServer || (!selectedServerUrl && !customServerUrl)}
                className="px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wider bg-accent hover:bg-accent/80 text-white rounded-lg transition-colors cursor-pointer disabled:opacity-50"
              >
                {savingServer ? 'Enregistrement...' : 'Enregistrer'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PlexAdmin;
