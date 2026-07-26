import React, { useEffect, useState, useRef, useCallback } from 'react';
import type { PluginAPI } from '../../../types/plugins';
import { useNodeStore } from '../../../store/nodeStore';
import { useAuthStore } from '../../../store/authStore';
import { api as globalApi } from '../../../hooks/useApi';
import { PlexSessionsTab } from '../components/PlexSessionsTab';
import type { PlexSession } from '../components/PlexSessionsTab';
import { PlexLibrariesTab } from '../components/PlexLibrariesTab';
import type { PlexLibrary } from '../components/PlexLibrariesTab';
import { PlexUsersTab } from '../components/PlexUsersTab';
import type { PlexUser } from '../components/PlexUsersTab';
import {
  Package,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
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
}

export const PlexAdmin: React.FC<PlexAdminProps> = ({ api }) => {
  const { nodes } = useNodeStore();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';

  const [selectedNodeId, setSelectedNodeId] = useState<string>('');
  const [plexConnecting, setPlexConnecting] = useState(false);
  const [plexPinCode, setPlexPinCode] = useState('');
  const [plexLoadingData, setPlexLoadingData] = useState(false);
  const [plexDetection, setPlexDetection] = useState<PlexDetection | null>(null);
  const [plexActiveTab, setPlexActiveTab] = useState<'sessions' | 'libraries' | 'users'>('sessions');
  
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

  // Pre-select first node if available
  useEffect(() => {
    if (nodes.length > 0 && !selectedNodeId) {
      setSelectedNodeId(nodes[0].id);
    }
  }, [nodes, selectedNodeId]);

  const fetchPlexData = useCallback(async (nodeId: string) => {
    if (!nodeId) return;
    setPlexLoadingData(true);
    setPlexDetection(null);
    try {
      // Fetch Plex status detection using plugin-scoped route: GET /api/plugins/plex/{node_id}/detect
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

  const handleConnectPlex = async () => {
    setPlexConnecting(true);
    clearPlexTimers();

    let clientId = localStorage.getItem('plex_client_id');
    if (!clientId) {
      clientId = 'vigile-client-' + Math.random().toString(36).substring(2, 15);
      localStorage.setItem('plex_client_id', clientId);
    }

    try {
      const res = await fetch('https://plex.tv/api/v2/pins?strong=true', {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'X-Plex-Product': 'Vigile',
          'X-Plex-Client-Identifier': clientId,
        },
      });
      if (!res.ok) throw new Error('Failed to fetch PIN');
      const data = await res.json();
      
      setPlexPinCode(data.code);

      const authUrl = `https://app.plex.tv/auth#?clientID=${clientId}&code=${data.code}&context%5Bdevice%5D%5Bproduct%5D=Vigile`;
      window.open(authUrl, 'Plex Auth', 'width=600,height=700');

      // Poll every 2 seconds for Plex authorization response
      plexPollIntervalRef.current = window.setInterval(async () => {
        try {
          const pollRes = await fetch(`https://plex.tv/api/v2/pins/${data.id}`, {
            headers: {
              'Accept': 'application/json',
              'X-Plex-Client-Identifier': clientId!,
            },
          });
          const pollData = await pollRes.json();
          if (pollData.authToken) {
            clearPlexTimers();
            // Save Plex auth token to plugin configuration
            await globalApi('/api/admin/plugins/plex/config', {
              method: 'POST',
              body: JSON.stringify({ plex_token: pollData.authToken }),
            });
            api.toast('Connexion réussie avec Plex !', 'success');
            setPlexConnecting(false);
            setPlexPinCode('');
            if (selectedNodeId) {
              fetchPlexData(selectedNodeId);
            }
          }
        } catch (err) {
          console.error('Plex polling error:', err);
        }
      }, 2000);

      // Set timeout of 2 mins
      plexPollTimeoutRef.current = window.setTimeout(() => {
        clearPlexTimers();
        setPlexConnecting(false);
        setPlexPinCode('');
        api.toast('La connexion avec Plex a expiré.', 'error');
      }, 120000);

    } catch (err) {
      console.error(err);
      api.toast('Impossible de démarrer la connexion avec Plex.', 'error');
      setPlexConnecting(false);
    }
  };

  return (
    <div className="p-6 max-w-5xl mx-auto flex flex-col gap-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-1 flex items-center gap-2">
            🎬 Plex Media Server
          </h1>
          <p className="text-sm text-text-3 mt-1">
            Supervisez l'activité et configurez le serveur Plex de votre flotte.
          </p>
        </div>

        {selectedNodeId && (
          <button
            onClick={() => fetchPlexData(selectedNodeId)}
            disabled={plexLoadingData}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border-strong/50 bg-surface-2 hover:bg-surface-hover/80 text-text-1 font-mono text-xs font-semibold uppercase tracking-wider cursor-pointer transition-colors duration-150 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${plexLoadingData ? 'animate-spin' : ''}`} />
            Rafraîchir
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 flex flex-col gap-6">
          {/* Node Selector */}
          <div className="p-5 rounded-xl border border-border-strong/30 bg-surface-2/40 backdrop-blur-xs flex flex-col gap-3">
            <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-text-3">
              Serveur Cible (Node)
            </h3>
            <select
              value={selectedNodeId}
              onChange={(e) => setSelectedNodeId(e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent transition-all duration-150"
            >
              <option value="">-- Choisir un nœud --</option>
              {nodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.name}
                </option>
              ))}
            </select>
          </div>

          {/* Authentication Panel */}
          {isAdmin && (
            <div className="p-5 rounded-xl border border-border-strong/30 bg-accent/5 flex flex-col gap-4">
              <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-accent">
                Authentification Plex
              </h3>
              <p className="text-xs text-text-2 leading-relaxed">
                Connectez Vigile à votre compte Plex pour activer la détection et les diagnostics automatiques de charge.
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={handleConnectPlex}
                  disabled={plexConnecting}
                  className="flex items-center gap-1.5 px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wider bg-orange-500 hover:bg-orange-600 text-white rounded-lg transition-colors cursor-pointer disabled:opacity-50"
                >
                  {plexConnecting ? (
                    <div className="animate-spin rounded-full h-3.5 w-3.5 border-t-2 border-white border-zinc-800" />
                  ) : (
                    <Package className="w-4 h-4" />
                  )}
                  Lier Plex
                </button>
                {plexPinCode && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-text-3 font-mono">CODE:</span>
                    <code className="text-sm font-mono font-bold bg-surface-3 px-2 py-0.5 rounded text-accent tracking-wider animate-pulse border border-accent/25">
                      {plexPinCode}
                    </code>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="lg:col-span-2">
          {plexLoadingData && (
            <div className="flex flex-col items-center justify-center py-20 bg-zinc-900/10 rounded-xl border border-zinc-800/40">
              <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-orange-500 border-zinc-800 mb-4" />
              <span className="text-zinc-500 text-sm font-mono">Analyse de Plex en cours...</span>
            </div>
          )}

          {!plexLoadingData && !selectedNodeId && (
            <div className="flex flex-col items-center justify-center py-16 bg-zinc-900/10 rounded-xl border border-zinc-800/40 text-center px-6">
              <AlertTriangle className="w-10 h-10 text-zinc-500 mb-3" />
              <p className="text-zinc-400 text-sm font-mono">Veuillez sélectionner un serveur pour inspecter Plex.</p>
            </div>
          )}

          {!plexLoadingData && selectedNodeId && plexDetection && (
            <div className="space-y-6">
              {!plexDetection.detected ? (
                <div className="flex items-center gap-3 p-4 bg-severity-warning/10 border border-severity-warning/20 rounded-xl text-severity-warning">
                  <AlertTriangle className="w-5 h-5 shrink-0" />
                  <span className="text-sm font-semibold">
                    Plex Media Server n'a pas été détecté sur ce nœud (aucun processus ni conteneur docker trouvé).
                  </span>
                </div>
              ) : (
                <div className="flex items-center justify-between p-4 bg-severity-ok/10 border border-severity-ok/20 rounded-xl text-severity-ok">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-5 h-5 shrink-0" />
                    <span className="text-sm font-semibold">
                      Plex détecté sur le port <span className="font-bold">{plexDetection.port}</span> ({plexDetection.type})
                    </span>
                  </div>
                  {plexDetection.status && (
                    <span className="text-[10px] font-bold font-mono bg-severity-ok/25 text-severity-ok px-2.5 py-0.5 rounded-full uppercase">
                      {plexDetection.status}
                    </span>
                  )}
                </div>
              )}

              {plexDetection.detected && !plexDetection.configured && (
                <div className="p-4 bg-severity-warning/5 border border-severity-warning/15 rounded-xl text-text-2 text-xs leading-relaxed">
                  ⚠️ Le token d'authentification Plex n'est pas configuré. Veuillez utiliser le bouton de connexion ci-contre pour lier Vigile.
                </div>
              )}

              {plexDetection.detected && plexDetection.configured && (
                <div className="p-5 rounded-xl border border-border-strong/30 bg-surface-2/10 backdrop-blur-xs flex flex-col gap-4">
                  <div className="flex border-b border-border-strong/10 gap-4">
                    {(['sessions', 'libraries', 'users'] as const).map((tab) => (
                      <button
                        key={tab}
                        onClick={() => setPlexActiveTab(tab)}
                        className={`pb-2.5 text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer border-b-2 ${
                          plexActiveTab === tab
                            ? 'text-orange-500 border-orange-500'
                            : 'text-text-3 border-transparent hover:text-text-2'
                        }`}
                      >
                        {tab === 'sessions' && 'Lectures en cours'}
                        {tab === 'libraries' && 'Bibliothèques'}
                        {tab === 'users' && 'Utilisateurs'}
                      </button>
                    ))}
                  </div>

                  {/* Sessions Tab */}
                  {plexActiveTab === 'sessions' && (
                    <PlexSessionsTab sessions={plexSessions} />
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
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PlexAdmin;
