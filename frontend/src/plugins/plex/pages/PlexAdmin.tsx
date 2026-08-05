import React, { useEffect, useState, useRef, useCallback } from 'react';
import type { PluginAPI } from '../../../types/plugins';
import { useNodeStore } from '../../../store/nodeStore';
import { useAuthStore } from '../../../store/authStore';
import { PlexSessionsTab } from '../components/PlexSessionsTab';
import type { PlexSession } from '../components/PlexSessionsTab';
import { PlexLibrariesTab } from '../components/PlexLibrariesTab';
import type { PlexLibrary } from '../components/PlexLibrariesTab';
import { PlexUsersTab } from '../components/PlexUsersTab';
import type { PlexUser } from '../components/PlexUsersTab';
import {
  Play,
  Film,
  Users,
  Settings,
  RefreshCw,
  AlertTriangle,
  Server,
  Activity,
  ShieldCheck,
  Globe,
  X,
  Zap,
  Check,
} from 'lucide-react';

interface PlexAdminProps {
  api: PluginAPI;
}

interface PlexDetection {
  detected: boolean;
  configured: boolean;
  port: number;
  type: string;
  status?: string;
  container_name?: string;
  service_name?: string;
}

interface PlexConnection {
  uri: string;
  address: string;
  port: number;
  local: boolean;
  protocol: string;
}

interface PlexServerResource {
  name: string;
  product: string;
  productVersion: string;
  clientIdentifier: string;
  owned: boolean;
  connections: PlexConnection[];
}

export const PlexAdmin: React.FC<PlexAdminProps> = ({ api }) => {
  const { nodes, isLoading: isLoadingNodes, fetchNodes } = useNodeStore();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';

  const [selectedNodeId, setSelectedNodeId] = useState<string>('');
  const [showConfigModal, setShowConfigModal] = useState<boolean>(false);

  // Fetch nodes on mount
  useEffect(() => {
    fetchNodes();
  }, [fetchNodes]);

  // Auth & Connection States
  const [plexConnecting, setPlexConnecting] = useState(false);
  const [plexPinCode, setPlexPinCode] = useState('');
  const [plexUsername, setPlexUsername] = useState<string | null>(null);
  const [plexLoadingData, setPlexLoadingData] = useState(false);
  const [plexDetection, setPlexDetection] = useState<PlexDetection | null>(null);
  const [plexActiveTab, setPlexActiveTab] = useState<'sessions' | 'libraries' | 'users'>('sessions');

  // Step 2 Server Selection States
  const [loadingServers, setLoadingServers] = useState(false);
  const [servers, setServers] = useState<PlexServerResource[]>([]);
  const [selectedServerUrl, setSelectedServerUrl] = useState<string>('');
  const [selectedServerName, setSelectedServerName] = useState<string>('');
  const [customUrlMode, setCustomUrlMode] = useState<boolean>(false);
  const [customServerUrl, setCustomServerUrl] = useState<string>('');
  const [savingServer, setSavingServer] = useState(false);

  // Telemetry Data
  const [plexSessions, setPlexSessions] = useState<PlexSession[]>([]);
  const [plexLibraries, setPlexLibraries] = useState<PlexLibrary[]>([]);
  const [plexUsers, setPlexUsers] = useState<PlexUser[]>([]);

  const plexPollIntervalRef = useRef<number | null>(null);
  const plexPollTimeoutRef = useRef<number | null>(null);

  const clearPlexTimers = () => {
    if (plexPollIntervalRef.current) {
      window.clearInterval(plexPollIntervalRef.current);
      plexPollIntervalRef.current = null;
    }
    if (plexPollTimeoutRef.current) {
      window.clearTimeout(plexPollTimeoutRef.current);
      plexPollTimeoutRef.current = null;
    }
  };

  useEffect(() => {
    return () => clearPlexTimers();
  }, []);

  // Auto select first node
  useEffect(() => {
    if (nodes.length > 0 && !selectedNodeId) {
      setSelectedNodeId(nodes[0].id);
    }
  }, [nodes, selectedNodeId]);

  const fetchPlexServers = useCallback(async () => {
    setLoadingServers(true);
    try {
      const res = await api.fetch<{ servers: PlexServerResource[] }>('/servers');
      setServers(res?.servers || []);
    } catch (err) {
      console.error('Failed to fetch Plex servers:', err);
    } finally {
      setLoadingServers(false);
    }
  }, [api]);

  const fetchPlexData = useCallback(async (nodeId: string) => {
    if (!nodeId) return;
    setPlexLoadingData(true);
    try {
      const detect = await api.fetch<PlexDetection>(`/${nodeId}/detect`);
      if (detect) {
        setPlexDetection(detect);
        if (detect.detected && detect.configured) {
          const [sessionsData, libraryData, usersData] = await Promise.all([
            api.fetch<{ sessions: PlexSession[] }>(`/${nodeId}/sessions`).catch(() => ({ sessions: [] })),
            api.fetch<{ libraries: PlexLibrary[] }>(`/${nodeId}/library`).catch(() => ({ libraries: [] })),
            api.fetch<{ users: PlexUser[] }>(`/${nodeId}/users`).catch(() => ({ users: [] })),
          ]);
          setPlexSessions(sessionsData?.sessions || []);
          setPlexLibraries(libraryData?.libraries || []);
          setPlexUsers(usersData?.users || []);
        }
      }
    } catch (err) {
      console.error('Failed to fetch Plex data:', err);
      api.toast('Impossible de récupérer les données du serveur Plex.', 'error');
    } finally {
      setPlexLoadingData(false);
    }
  }, [api]);

  useEffect(() => {
    if (selectedNodeId) {
      fetchPlexData(selectedNodeId);
    }
  }, [selectedNodeId, fetchPlexData]);

  useEffect(() => {
    if (plexDetection?.configured) {
      fetchPlexServers();
    }
  }, [plexDetection?.configured, fetchPlexServers]);

  // OAuth PIN Login
  const handleConnectPlex = async () => {
    setPlexConnecting(true);
    clearPlexTimers();

    try {
      const pinData = await api.fetch<{ id: number; code: string; auth_url: string }>('/auth/pin', {
        method: 'POST',
      });

      if (!pinData || !pinData.auth_url) {
        throw new Error('Pin payload invalid');
      }

      setPlexPinCode(pinData.code);
      window.open(pinData.auth_url, 'Plex Auth', 'width=600,height=700');

      plexPollIntervalRef.current = window.setInterval(async () => {
        try {
          const res = await api.fetch<{ authenticated: boolean; user?: string }>('/auth/verify', {
            method: 'POST',
            body: JSON.stringify({ pin_id: pinData.id }),
          });

          if (res && res.authenticated) {
            clearPlexTimers();
            setPlexConnecting(false);
            setPlexPinCode('');
            if (res.user) {
              setPlexUsername(res.user);
            }
            api.toast('Connexion réussie avec Plex.tv !', 'success');
            if (selectedNodeId) {
              fetchPlexData(selectedNodeId);
            }
            fetchPlexServers();
          }
        } catch (err) {
          console.error('Plex polling error:', err);
        }
      }, 2000);

      plexPollTimeoutRef.current = window.setTimeout(() => {
        clearPlexTimers();
        setPlexConnecting(false);
        setPlexPinCode('');
        api.toast('La connexion avec Plex a expiré.', 'error');
      }, 120000);

    } catch (err) {
      console.error(err);
      api.toast('Impossible d\'initier l\'authentification Plex.', 'error');
      setPlexConnecting(false);
    }
  };

  // Save Server Settings
  const handleSaveServerConfig = async () => {
    setSavingServer(true);
    try {
      const targetUrl = customUrlMode ? customServerUrl.trim() : selectedServerUrl.trim();
      await api.fetch('/config/server', {
        method: 'POST',
        body: JSON.stringify({
          server_url: targetUrl,
          server_name: selectedServerName,
        }),
      });
      api.toast('Configuration du serveur Plex enregistrée !', 'success');
      setShowConfigModal(false);
      if (selectedNodeId) {
        fetchPlexData(selectedNodeId);
      }
    } catch (err) {
      console.error('Failed to save server config:', err);
      api.toast('Erreur lors de la sauvegarde du serveur Plex.', 'error');
    } finally {
      setSavingServer(false);
    }
  };

  const selectedNode = nodes.find((n) => n.id === selectedNodeId);
  const activeTranscodes = plexSessions.filter((s) => s.transcode).length;

  return (
    <div className="p-6 max-w-6xl mx-auto flex flex-col gap-6 animate-fade-in">
      {/* Top Header & Bar */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-border-strong/20 pb-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-orange-500/10 border border-orange-500/20 flex items-center justify-center text-orange-500 shadow-sm">
            <Play className="w-5 h-5 fill-orange-500" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-text-1 tracking-tight flex items-center gap-2">
              Plex Media Server
            </h1>
            <p className="text-xs text-text-3 font-mono">
              Supervision des sessions de streaming et télémétrie des nœuds.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {isAdmin && (
            <button
              onClick={() => setShowConfigModal(true)}
              className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-border-strong/40 bg-surface-2 hover:bg-surface-hover text-text-1 text-xs font-semibold font-mono tracking-wide cursor-pointer transition-all"
            >
              <Settings className="w-3.5 h-3.5 text-accent" />
              Configurer Plex
            </button>
          )}

          {selectedNodeId && (
            <button
              onClick={() => {
                fetchPlexData(selectedNodeId);
                if (plexDetection?.configured) fetchPlexServers();
              }}
              disabled={plexLoadingData}
              className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-border-strong/40 bg-surface-2 hover:bg-surface-hover text-text-1 text-xs font-semibold font-mono tracking-wide cursor-pointer transition-all disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${plexLoadingData ? 'animate-spin text-accent' : ''}`} />
              Rafraîchir
            </button>
          )}
        </div>
      </div>

      {/* Node Selector Pills */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
        <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-text-3 mr-2 shrink-0">
          Nœuds :
        </span>
        {isLoadingNodes ? (
          <span className="text-xs text-text-3 font-mono flex items-center gap-2">
            <RefreshCw className="w-3.5 h-3.5 animate-spin text-accent" /> Chargement des nœuds...
          </span>
        ) : nodes.length === 0 ? (
          <span className="text-xs text-amber-400 font-mono flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> Aucun nœud connecté à votre flotte
          </span>
        ) : (
          nodes.map((node) => {
            const isSelected = node.id === selectedNodeId;
            return (
              <button
                key={node.id}
                onClick={() => setSelectedNodeId(node.id)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl border text-xs font-mono font-semibold transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-orange-500/10 border-orange-500/40 text-orange-400 shadow-[0_0_12px_rgba(249,115,22,0.15)]'
                    : 'bg-surface-2/40 border-border-strong/20 text-text-2 hover:bg-surface-hover/80 hover:text-text-1'
                }`}
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    node.online ? 'bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.4)]' : 'bg-zinc-600'
                  }`}
                />
                <span>{node.name}</span>
              </button>
            );
          })
        )}
      </div>

      {nodes.length === 0 && !isLoadingNodes && (
        <div className="flex flex-col items-center justify-center py-16 bg-surface-2/20 rounded-xl border border-border-strong/30 text-center px-6 gap-4">
          <div className="w-12 h-12 rounded-full bg-surface-3 flex items-center justify-center text-text-3">
            <Server className="w-6 h-6" />
          </div>
          <div className="max-w-md">
            <h3 className="text-base font-bold text-text-1 font-mono">Aucun nœud disponible</h3>
            <p className="text-xs text-text-3 mt-1 leading-relaxed">
              Aucun serveur ou agent (Worker) n'est actuellement connecté à votre instance Vigile. Rendez-vous dans la section <strong>Serveurs</strong> pour ajouter ou vérifier vos nœuds.
            </p>
          </div>
        </div>
      )}

      {/* Telemetry Detection Banner (Worker primitives) */}
      {selectedNode && plexDetection && (
        <div className="p-4 rounded-xl border border-border-strong/25 bg-surface-2/30 backdrop-blur-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className={`p-2.5 rounded-lg border ${
              plexDetection.detected
                ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-400'
                : 'bg-amber-500/10 border-amber-500/25 text-amber-400'
            }`}>
              <Server className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2 text-xs font-mono font-bold text-text-1">
                <span>{selectedNode.name}</span>
                <span className="text-text-3">•</span>
                <span className="text-text-2">
                  {plexDetection.detected
                    ? `Plex Détecté (${plexDetection.type === 'docker' ? `Conteneur: ${plexDetection.container_name || 'Docker'}` : `Service Native: ${plexDetection.service_name || 'Systemd'}`})`
                    : 'Plex Non Détecté sur ce nœud'}
                </span>
              </div>
              <div className="text-[11px] font-mono text-text-3 mt-0.5 flex items-center gap-2">
                <span>Port par défaut : <strong className="text-text-2">{plexDetection.port}</strong></span>
                {plexDetection.configured && (
                  <>
                    <span>•</span>
                    <span className="text-emerald-400 font-semibold flex items-center gap-1">
                      <Check className="w-3 h-3" /> Token Configuré
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          {!plexDetection.configured && isAdmin && (
            <button
              onClick={() => setShowConfigModal(true)}
              className="px-3.5 py-1.5 text-xs font-mono font-bold uppercase tracking-wider bg-orange-500 hover:bg-orange-600 text-white rounded-lg transition-colors cursor-pointer shrink-0"
            >
              Associer Plex.tv
            </button>
          )}
        </div>
      )}

      {/* Main Grid Content */}
      {selectedNodeId && plexDetection?.detected && plexDetection?.configured && (
        <div className="space-y-6">
          {/* Key Metric Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-4 rounded-xl border border-border-strong/20 bg-surface-2/40 flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-xs text-text-3 font-mono uppercase font-bold">
                <span>Lectures Actives</span>
                <Activity className="w-4 h-4 text-orange-500" />
              </div>
              <div className="text-2xl font-bold text-text-1 font-mono flex items-center gap-2">
                {plexSessions.length}
                {plexSessions.length > 0 && (
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                )}
              </div>
            </div>

            <div className="p-4 rounded-xl border border-border-strong/20 bg-surface-2/40 flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-xs text-text-3 font-mono uppercase font-bold">
                <span>Transcodages</span>
                <Zap className="w-4 h-4 text-amber-500" />
              </div>
              <div className="text-2xl font-bold text-text-1 font-mono">
                {activeTranscodes}
              </div>
            </div>

            <div className="p-4 rounded-xl border border-border-strong/20 bg-surface-2/40 flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-xs text-text-3 font-mono uppercase font-bold">
                <span>Bibliothèques</span>
                <Film className="w-4 h-4 text-accent" />
              </div>
              <div className="text-2xl font-bold text-text-1 font-mono">
                {plexLibraries.length}
              </div>
            </div>

            <div className="p-4 rounded-xl border border-border-strong/20 bg-surface-2/40 flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-xs text-text-3 font-mono uppercase font-bold">
                <span>Utilisateurs</span>
                <Users className="w-4 h-4 text-blue-400" />
              </div>
              <div className="text-2xl font-bold text-text-1 font-mono">
                {plexUsers.length}
              </div>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="p-5 rounded-xl border border-border-strong/30 bg-surface-2/10 backdrop-blur-xs flex flex-col gap-4">
            <div className="flex border-b border-border-strong/15 gap-6">
              {(['sessions', 'libraries', 'users'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setPlexActiveTab(tab)}
                  className={`pb-3 text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer border-b-2 font-mono flex items-center gap-2 ${
                    plexActiveTab === tab
                      ? 'text-orange-500 border-orange-500'
                      : 'text-text-3 border-transparent hover:text-text-2'
                  }`}
                >
                  {tab === 'sessions' && (
                    <>
                      <Play className="w-3.5 h-3.5" /> Lectures ({plexSessions.length})
                    </>
                  )}
                  {tab === 'libraries' && (
                    <>
                      <Film className="w-3.5 h-3.5" /> Bibliothèques ({plexLibraries.length})
                    </>
                  )}
                  {tab === 'users' && (
                    <>
                      <Users className="w-3.5 h-3.5" /> Utilisateurs ({plexUsers.length})
                    </>
                  )}
                </button>
              ))}
            </div>

            {/* Sessions Tab */}
            {plexActiveTab === 'sessions' && (
              <PlexSessionsTab
                sessions={plexSessions}
                nodeId={selectedNodeId}
                isAdmin={isAdmin}
                onKillSession={(sessionKey) => {
                  api.toast(`Interruption de la session ${sessionKey}...`, 'info');
                }}
              />
            )}

            {/* Libraries Tab */}
            {plexActiveTab === 'libraries' && (
              <PlexLibrariesTab libraries={plexLibraries} />
            )}

            {/* Users Tab */}
            {plexActiveTab === 'users' && (
              <PlexUsersTab users={plexUsers} />
            )}
          </div>
        </div>
      )}

      {/* Unconfigured State Banner */}
      {selectedNodeId && plexDetection?.detected && !plexDetection?.configured && (
        <div className="flex flex-col items-center justify-center py-16 bg-surface-2/20 rounded-xl border border-border-strong/30 text-center px-6 gap-4">
          <div className="w-12 h-12 rounded-full bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-500">
            <AlertTriangle className="w-6 h-6" />
          </div>
          <div className="max-w-md">
            <h3 className="text-base font-bold text-text-1 font-mono">Plex est détecté mais non authentifié</h3>
            <p className="text-xs text-text-3 mt-1 leading-relaxed">
              Liez Vigile à votre compte Plex.tv pour importer vos serveurs et consulter les flux en direct.
            </p>
          </div>
          {isAdmin && (
            <button
              onClick={() => setShowConfigModal(true)}
              className="px-5 py-2 text-xs font-mono font-bold uppercase tracking-wider bg-orange-500 hover:bg-orange-600 text-white rounded-lg transition-colors cursor-pointer shadow-lg"
            >
              Lier Plex.tv Maintenant
            </button>
          )}
        </div>
      )}

      {/* Plex Configuration Modal Drawer */}
      {showConfigModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-surface border border-border-strong/40 rounded-2xl max-w-lg w-full p-6 flex flex-col gap-5 shadow-2xl animate-fade-in">
            <div className="flex items-center justify-between border-b border-border-strong/20 pb-4">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-orange-500/10 border border-orange-500/20 flex items-center justify-center text-orange-500">
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

            {/* Step 1: OAuth Authentication */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-bold uppercase text-accent flex items-center gap-1.5">
                  <ShieldCheck className="w-4 h-4" /> 1. Authentification Plex.tv
                </span>
                {plexDetection?.configured && (
                  <span className="text-[10px] font-mono font-bold bg-emerald-500/15 text-emerald-400 px-2 py-0.5 rounded-full border border-emerald-500/20">
                    Connecté
                  </span>
                )}
              </div>

              {plexUsername && (
                <div className="text-xs font-mono text-text-2 bg-surface-2 px-3 py-1.5 rounded-lg border border-border-strong/20">
                  Compte : <strong className="text-text-1">{plexUsername}</strong>
                </div>
              )}

              <div className="flex items-center gap-3">
                <button
                  onClick={handleConnectPlex}
                  disabled={plexConnecting}
                  className="flex items-center gap-2 px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wider bg-orange-500 hover:bg-orange-600 text-white rounded-lg transition-colors cursor-pointer disabled:opacity-50"
                >
                  {plexConnecting ? (
                    <div className="animate-spin rounded-full h-3.5 w-3.5 border-t-2 border-white border-zinc-800" />
                  ) : (
                    <Globe className="w-4 h-4" />
                  )}
                  {plexDetection?.configured ? 'Re-connecter Plex' : 'Se connecter avec Plex'}
                </button>

                {plexPinCode && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-text-3 font-mono">CODE:</span>
                    <code className="text-sm font-mono font-bold bg-surface-3 px-2.5 py-0.5 rounded text-accent tracking-wider animate-pulse border border-accent/30">
                      {plexPinCode}
                    </code>
                  </div>
                )}
              </div>
            </div>

            <hr className="border-border-strong/15" />

            {/* Step 2: Server Selection */}
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
                      {srv.connections.map((conn, idx) => (
                        <label
                          key={idx}
                          className={`flex items-center justify-between p-1.5 rounded cursor-pointer transition-colors ${
                            selectedServerUrl === conn.uri ? 'bg-orange-500/15 border border-orange-500/40 text-orange-400 font-semibold' : 'hover:bg-surface-hover/50 text-text-2'
                          }`}
                        >
                          <div className="flex items-center gap-2 text-[11px] truncate">
                            <input
                              type="radio"
                              name="plex_server_choice"
                              checked={selectedServerUrl === conn.uri}
                              onChange={() => {
                                setSelectedServerUrl(conn.uri);
                                setSelectedServerName(srv.name);
                              }}
                              className="accent-orange-500"
                            />
                            <span className="truncate">{conn.uri}</span>
                          </div>
                          <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-surface-3 text-text-3">
                            {conn.local ? 'Local' : 'Distant'}
                          </span>
                        </label>
                      ))}
                    </div>
                  ))}
                </div>
              )}

              <button
                onClick={() => setCustomUrlMode(!customUrlMode)}
                className="text-accent underline font-mono text-[11px] cursor-pointer hover:text-accent-hover text-left"
              >
                {customUrlMode ? '← Choisir parmi les serveurs détectés' : 'Saisir une adresse IP / URL sur mesure'}
              </button>

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
                className="px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wider bg-orange-500 hover:bg-orange-600 text-white rounded-lg transition-colors cursor-pointer disabled:opacity-50"
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
