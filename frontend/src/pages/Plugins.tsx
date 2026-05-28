import React, { useState, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { useLocale } from '../i18n';
import { api } from '../hooks/useApi';
import { 
  Puzzle, 
  Terminal, 
  Cpu, 
  Box, 
  Activity, 
  ShieldAlert, 
  RefreshCw, 
  ChevronRight, 
  Code,
  Network,
  Upload,
  Plus,
  Trash2,
  Check,
  AlertCircle,
  ToggleLeft,
  ToggleRight,
  Sparkles,
  BookOpen
} from 'lucide-react';

interface PluginData {
  id: string;
  name: string;
  description: string;
  category: string;
  schema: {
    [key: string]: {
      type: string;
      title?: string;
      default?: any;
      description?: string;
    };
  };
  enabled: boolean;
  config: { [key: string]: any };
  loaded: boolean;
  hooks: string[];
}

const CATEGORY_ICONS: { [key: string]: React.ReactNode } = {
  'Monitoring': <Cpu className="w-5 h-5 text-accent-primary" />,
  'System': <Activity className="w-5 h-5 text-warning" />,
  'Virtualization': <Box className="w-5 h-5 text-success" />,
  'Alerts': <ShieldAlert className="w-5 h-5 text-danger" />,
  'Custom': <Code className="w-5 h-5 text-indigo-400" />
};

const CATEGORY_COLORS: { [key: string]: string } = {
  'Monitoring': 'text-accent-primary border-accent-primary/20 bg-accent-subtle',
  'System': 'text-warning border-warning/20 bg-warning-subtle',
  'Virtualization': 'text-success border-success/20 bg-success-subtle',
  'Alerts': 'text-danger border-danger/20 bg-danger-subtle',
  'Custom': 'text-indigo-400 border-indigo-500/20 bg-indigo-500/10'
};

const TEMPLATE_PLUGINS = [
  {
    id: 'discord_logger',
    name: 'Discord Webhook Logger',
    category: 'Alerts',
    description: 'Envoie les alertes critiques et les mutations système directement dans un canal Discord via les Webhooks.',
    code: `"""
Vigile — Discord Webhook Logger
Sends critical system events to a Discord channel.
"""
import logging
import json
import httpx

logger = logging.getLogger(__name__)

def register(pm) -> None:
    pm.register("on_status_report", on_status_report, plugin_name="discord_logger")

def get_config_schema() -> dict:
    return {
        "name": "Discord Webhook Logger",
        "category": "Alerts",
        "description": "Sends critical events to a Discord channel.",
        "schema": {
            "webhook_url": {
                "type": "string",
                "title": "Webhook URL",
                "default": "",
                "description": "The Discord channel Webhook URL."
            },
            "notify_on_warning": {
                "type": "boolean",
                "title": "Notify on Warnings",
                "default": True,
                "description": "Send alerts for warnings besides critical issues."
            }
        }
    }

async def on_status_report(node_id: str, snapshot: dict, db=None) -> None:
    # Retrieve configuration parameters
    from master.core.plugin_manager import plugin_manager
    config = await plugin_manager.get_plugin_config("discord_logger")
    url = config.get("webhook_url")
    if not url:
        return

    cpu = snapshot.get("cpu_percent", 0)
    mem = snapshot.get("mem_percent", 0)
    
    if cpu > 90 or mem > 90:
        msg = f"⚠️ **Alerte Vigile** | Nœud \\\`{node_id}\\\` en surcharge : CPU {cpu}%, RAM {mem}%"
        try:
            async with httpx.AsyncClient() as client:
                await client.post(url, json={"content": msg})
        except Exception as e:
            logger.error("Failed to send discord alert: %s", e)
`
  },
  {
    id: 'ntfy_alerter',
    name: 'ntfy.sh Alerter',
    category: 'Alerts',
    description: 'Envoie des notifications push instantanées sur votre téléphone/ordinateur via le service gratuit ntfy.sh.',
    code: `"""
Vigile — ntfy.sh Alerter
Sends push notifications to ntfy.sh topics.
"""
import logging
import httpx

logger = logging.getLogger(__name__)

def register(pm) -> None:
    pm.register("on_status_report", on_status_report, plugin_name="ntfy_alerter")

def get_config_schema() -> dict:
    return {
        "name": "ntfy.sh Alerter",
        "category": "Alerts",
        "description": "Sends push notifications to an ntfy topic on status changes.",
        "schema": {
            "topic": {
                "type": "string",
                "title": "ntfy.sh Topic Name",
                "default": "vigile-alerts",
                "description": "Unique topic name you subscribe to in the ntfy app."
            }
        }
    }

async def on_status_report(node_id: str, snapshot: dict, db=None) -> None:
    from master.core.plugin_manager import plugin_manager
    config = await plugin_manager.get_plugin_config("ntfy_alerter")
    topic = config.get("topic", "vigile-alerts")
    
    cpu = snapshot.get("cpu_percent", 0)
    if cpu > 95:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://ntfy.sh/{topic}",
                    content=f"Surcharge critique sur le nœud {node_id} (CPU: {cpu}%)",
                    headers={"Title": "Alerte Vigile", "Priority": "high", "Tags": "warning,computer"}
                )
        except Exception as e:
            logger.error("ntfy notification failed: %s", e)
`
  }
];

export const Plugins: React.FC = () => {
  const { accessToken, user } = useAuthStore();
  const { t } = useLocale();
  const [plugins, setPlugins] = useState<PluginData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  
  // Selection & Forms
  const [selectedId, setSelectedId] = useState<string>('metrics');
  const [configForm, setConfigForm] = useState<{ [key: string]: any }>({});
  const [isToggling, setIsToggling] = useState<string | null>(null);
  const [isSavingConfig, setIsSavingConfig] = useState(false);
  const [isUninstalling, setIsUninstalling] = useState(false);

  // Custom Delete Modal state
  const [pluginToDelete, setPluginToDelete] = useState<string | null>(null);

  // Install Modal states
  const [showInstallModal, setShowInstallModal] = useState(false);
  const [installTab, setInstallTab] = useState<'upload' | 'paste' | 'templates'>('upload');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [pastedCode, setPastedCode] = useState('');
  const [customFilename, setCustomFilename] = useState('custom_plugin.py');
  const [isUploading, setIsUploading] = useState(false);

  // Hook simulator logs
  const [simulatedLogs, setSimulatedLogs] = useState<string[]>([
    "[SYSTEM] Moteur d'extensions initialisé.",
    "[SYSTEM] Table 'plugin_configs' connectée."
  ]);

  const isAdmin = user?.role === 'admin';

  const fetchPlugins = async () => {
    if (!isAdmin) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api<{ plugins: PluginData[] }>('/api/admin/plugins');
      if (data) {
        const list = data.plugins || [];
        setPlugins(list);
        
        // Sync config form with selected plugin
        const active = list.find(p => p.id === selectedId) || list[0];
        if (active) {
          setSelectedId(active.id);
          setConfigForm(active.config || {});
        }
      }
    } catch (err: any) {
      setError(err.message || "Impossible de charger la liste des extensions.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPlugins();
  }, [accessToken, isAdmin]);

  const handleSelectPlugin = (p: PluginData) => {
    setSelectedId(p.id);
    setConfigForm(p.config || {});
  };

  const addLog = (msg: string, type: 'info' | 'trigger' | 'warn' | 'success' = 'info') => {
    const time = new Date().toLocaleTimeString('fr-FR');
    let prefix = '[SYSTEM]';
    if (type === 'trigger') prefix = '[TRIGGER]';
    else if (type === 'warn') prefix = '[WARN]';
    else if (type === 'success') prefix = '[SUCCESS]';
    
    setSimulatedLogs(prev => [`[${time}] ${prefix} ${msg}`, ...prev.slice(0, 19)]);
  };

  const handleToggleState = async (plugin: PluginData) => {
    if (isToggling) return;
    setIsToggling(plugin.id);
    setError(null);
    setSuccessMsg(null);
    addLog(`Changement d'état demandé pour '${plugin.id}'...`, 'info');

    try {
      const data = await api<any>(`/api/admin/plugins/${plugin.id}/toggle`, {
        method: 'POST'
      });

      if (data) {
        addLog(`Plugin '${plugin.id}' basculé avec succès.`, 'success');
        setSuccessMsg(data.message);
        await fetchPlugins();
      }
    } catch (err: any) {
      setError(err.message || "Échec du basculement de l'extension.");
      addLog(`Erreur lors du basculement de '${plugin.id}': ${err.message || 'Erreur API'}`, 'warn');
    } finally {
      setIsToggling(null);
    }
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSavingConfig) return;
    setIsSavingConfig(true);
    setError(null);
    setSuccessMsg(null);
    addLog(`Sauvegarde de la configuration pour '${selectedId}'...`, 'info');

    try {
      const data = await api<any>(`/api/admin/plugins/${selectedId}/config`, {
        method: 'POST',
        body: JSON.stringify(configForm)
      });

      if (data) {
        addLog(`Configuration enregistrée pour '${selectedId}'.`, 'success');
        setSuccessMsg("Configuration enregistrée avec succès.");
        await fetchPlugins();
      }
    } catch (err: any) {
      setError(err.message || "Échec de l'enregistrement de la configuration.");
      addLog(`Erreur configuration '${selectedId}': ${err.message || 'Erreur API'}`, 'warn');
    } finally {
      setIsSavingConfig(false);
    }
  };

  const handleDeletePluginConfirm = async () => {
    if (!pluginToDelete) return;
    setIsUninstalling(true);
    setError(null);
    setSuccessMsg(null);
    addLog(`Désinstallation de '${pluginToDelete}' initiée (draining en cours)...`, 'info');

    try {
      const data = await api<any>(`/api/admin/plugins/${pluginToDelete}`, {
        method: 'DELETE'
      });

      if (data) {
        addLog(`Plugin '${pluginToDelete}' désinstallé et supprimé du disque.`, 'success');
        setSuccessMsg("Extension désinstallée avec succès.");
        setSelectedId('metrics');
        setPluginToDelete(null);
        await fetchPlugins();
      }
    } catch (err: any) {
      setError(err.message || "Échec de la désinstallation.");
      addLog(`Échec désinstallation '${pluginToDelete}': ${err.message || 'Erreur API'}`, 'warn');
    } finally {
      setIsUninstalling(false);
    }
  };

  // Uploader/Installer
  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isUploading) return;

    let fileToSend: Blob | null = null;
    let filename = '';

    if (installTab === 'upload') {
      if (!uploadFile) {
        setError("Veuillez sélectionner un fichier.");
        return;
      }
      fileToSend = uploadFile;
      filename = uploadFile.name;
    } else if (installTab === 'paste') {
      if (!pastedCode.trim()) {
        setError("Le code de l'extension ne peut pas être vide.");
        return;
      }
      fileToSend = new Blob([pastedCode], { type: 'text/plain' });
      filename = customFilename.endsWith('.py') ? customFilename : `${customFilename}.py`;
    }

    if (!fileToSend || !filename) return;

    setIsUploading(true);
    setError(null);
    setSuccessMsg(null);
    addLog(`Téléversement de l'extension '${filename}'...`, 'info');

    const formData = new FormData();
    formData.append('file', fileToSend, filename);

    try {
      // Use raw fetch for FormData because it requires boundary and custom Headers
      const res = await fetch('/api/admin/plugins/upload', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${accessToken}`
        },
        body: formData
      });

      if (res.ok) {
        addLog(`Extension '${filename}' téléversée et chargée.`, 'success');
        setSuccessMsg(`Extension '${filename}' installée et chargée avec succès.`);
        setShowInstallModal(false);
        setUploadFile(null);
        setPastedCode('');
        
        // Auto-select newly uploaded plugin
        const newId = filename.replace('.py', '');
        setSelectedId(newId);
        
        await fetchPlugins();
      } else {
        const err = await res.json().catch(() => ({}));
        setError(err.detail || "Échec du téléversement de l'extension.");
        addLog(`Échec chargement '${filename}': ${err.detail || 'Erreur API'}`, 'warn');
      }
    } catch (err) {
      setError("Erreur réseau lors de l'envoi.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleLoadTemplate = (template: typeof TEMPLATE_PLUGINS[0]) => {
    setPastedCode(template.code);
    setCustomFilename(`${template.id}.py`);
    setInstallTab('paste');
    addLog(`Modèle '${template.name}' copié dans l'éditeur.`, 'info');
  };

  const selectedPlugin = plugins.find(p => p.id === selectedId);

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6 select-none">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border pb-6">
        <div>
          <h1 className="text-lg font-bold text-ink-primary tracking-tight flex items-center gap-2">
            <Puzzle className="w-5 h-5 text-accent-primary animate-pulse" />
            <span>{t('plugins.title')}</span>
          </h1>
          <p className="text-xs text-ink-muted mt-1">
            Installez, configurez et inspectez à chaud les extensions dynamiques du serveur Master.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {isAdmin && (
            <>
              <button
                onClick={fetchPlugins}
                disabled={loading}
                className="btn btn-secondary text-xs"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-accent-primary' : ''}`} />
                <span>Actualiser</span>
              </button>
              <button
                onClick={() => {
                  setError(null);
                  setSuccessMsg(null);
                  setShowInstallModal(true);
                }}
                className="btn btn-primary text-xs"
              >
                <Plus className="w-4 h-4" />
                <span>Installer une extension</span>
              </button>
            </>
          )}
        </div>
      </div>

      {/* Messages */}
      {error && (
        <div className="p-4 rounded border border-danger/20 bg-danger-subtle flex items-start gap-3 text-danger">
          <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
          <div className="text-xs font-semibold">{error}</div>
        </div>
      )}
      {successMsg && (
        <div className="p-4 rounded border border-success/20 bg-success-subtle flex items-start gap-3 text-success">
          <Check className="w-5 h-5 shrink-0 mt-0.5" />
          <div className="text-xs font-semibold">{successMsg}</div>
        </div>
      )}

      {/* Access limit details */}
      {!isAdmin && (
        <div className="p-4 rounded border border-warning/20 bg-warning-subtle flex items-start gap-3">
          <ShieldAlert className="w-5 h-5 text-warning shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h4 className="text-xs font-bold text-warning uppercase tracking-wide">Accès Limité (Mode Lecture Seule)</h4>
            <p className="text-[11px] text-ink-secondary leading-relaxed">
              La gestion physique des scripts Python et le paramétrage des extensions en base de données requièrent des privilèges Administrateur.
            </p>
          </div>
        </div>
      )}

      {/* Main Grid Layout */}
      {isAdmin && (
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
          {/* Left: Extension List (Col 7) */}
          <div className="xl:col-span-7 space-y-6">
            <div className="space-y-3">
              <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider">
                Extensions Installées ({plugins.length})
              </h3>
              
              {loading && plugins.length === 0 ? (
                <div className="card p-8 text-center flex items-center justify-center gap-2">
                  <RefreshCw className="w-5 h-5 animate-spin text-accent-primary" />
                  <span className="text-xs text-ink-muted">Chargement du registre...</span>
                </div>
              ) : plugins.length === 0 ? (
                <div className="card p-12 text-center space-y-3">
                  <Puzzle className="w-10 h-10 text-ink-muted mx-auto" />
                  <p className="text-xs text-ink-muted">Aucune extension installée dans le dossier plugins.</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {plugins.map((plugin) => {
                    const isSelected = selectedId === plugin.id;
                    const catColor = CATEGORY_COLORS[plugin.category] || CATEGORY_COLORS['Custom'];
                    const catIcon = CATEGORY_ICONS[plugin.category] || CATEGORY_ICONS['Custom'];
                    
                    return (
                      <div
                        key={plugin.id}
                        onClick={() => handleSelectPlugin(plugin)}
                        className={`text-left w-full card p-4 cursor-pointer flex flex-col justify-between min-h-[160px] relative overflow-hidden group ${
                          isSelected ? 'border-accent-primary shadow-[0_0_12px_rgba(99,102,241,0.05)]' : 'border-border'
                        }`}
                      >
                        <div className="w-full space-y-2.5">
                          <div className="flex items-start justify-between">
                            <div className={`p-2 rounded border ${catColor} shadow-sm shrink-0`}>
                              {catIcon}
                            </div>
                            <div className="flex items-center gap-1.5">
                              {plugin.enabled ? (
                                <span className="text-[10px] font-bold text-success bg-success-subtle border border-success/20 px-2 py-0.5 rounded-full flex items-center gap-1">
                                  <span className="w-1 h-1 rounded-full bg-success animate-ping" />
                                  {t('plugins.status.active')}
                                </span>
                              ) : (
                                <span className="text-[10px] font-bold text-ink-muted bg-surface-1 border border-border px-2 py-0.5 rounded-full">
                                  {t('plugins.status.inactive')}
                                </span>
                              )}
                              {!plugin.loaded && plugin.enabled && (
                                <span className="text-[10px] font-bold text-warning bg-warning-subtle border border-warning/20 px-1.5 py-0.5 rounded-full">
                                  {t('plugins.status.stale')}
                                </span>
                              )}
                            </div>
                          </div>

                          <div>
                            <h4 className="text-xs font-bold text-ink-primary group-hover:text-accent-primary transition-colors flex items-center gap-1.5">
                              {plugin.name}
                            </h4>
                            <p className="text-[10px] text-ink-secondary mt-1 leading-relaxed line-clamp-2">
                              {plugin.description}
                            </p>
                          </div>
                        </div>

                        <div className="mt-4 pt-2.5 border-t border-border/40 flex justify-between items-center text-[10px] font-mono text-ink-muted w-full">
                          <span>Hooks: {plugin.hooks.length}</span>
                          <span className="flex items-center gap-0.5 text-accent-primary font-bold">
                            <span>Inspecter & Paramétrer</span>
                            <ChevronRight className="w-3.5 h-3.5" />
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Hook Flow Cartography Map */}
            <div className="card p-5 relative overflow-hidden">
              <div className="absolute right-3 top-3 flex items-center gap-1.5 text-[9px] text-ink-muted font-bold uppercase">
                <Network className="w-3.5 h-3.5 text-accent-primary" />
                <span>Graphe système</span>
              </div>
              <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider mb-1">
                Cartographie des Événements
              </h3>
              <p className="text-[10px] text-ink-secondary leading-relaxed mb-4">
                Visualisez comment les extensions interceptent les flux d'informations et les intentions.
              </p>
              
              <div className="bg-[#06060a] border border-border rounded-lg p-5 flex flex-col md:flex-row items-center justify-between gap-6 relative min-h-[160px]">
                <div className="flex flex-col gap-3 items-center">
                  <span className="text-[9px] font-bold text-ink-muted uppercase tracking-widest">Signaux Entrants</span>
                  <div className="px-3 py-2 rounded bg-surface-1 border border-border text-center min-w-[120px]">
                    <div className="text-xs font-bold text-ink-primary">STATUS_REPORT</div>
                    <div className="text-[9px] font-mono text-ink-muted mt-0.5">WebSocket Agent</div>
                  </div>
                </div>

                <div className="text-accent-primary font-bold text-xs select-none">🡪 Hooks dispatch 🡪</div>

                <div className="flex flex-wrap gap-2 justify-center max-w-[280px]">
                  {plugins.filter(p => p.enabled && p.loaded).flatMap(p => p.hooks).filter((v, i, a) => a.indexOf(v) === i).map(h => (
                    <span key={h} className="px-2 py-1 font-mono text-[9px] font-bold rounded bg-accent-subtle border border-accent-primary/20 text-accent-primary">
                      {h}
                    </span>
                  ))}
                  {plugins.filter(p => p.enabled && p.loaded).length === 0 && (
                    <span className="text-[10px] text-ink-muted">Aucun point d'ancrage actif.</span>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Right: Inspector & Configuration Panel (Col 5) */}
          <div className="xl:col-span-5 space-y-6">
            {selectedPlugin ? (
              <div className="card p-5 space-y-5 relative">
                {/* Glow Backdrop */}
                <div className="absolute top-0 right-0 w-32 h-32 bg-accent-primary/5 blur-2xl rounded-full pointer-events-none" />

                <div className="flex items-center justify-between border-b border-border pb-4 relative z-10">
                  <div className="flex items-center gap-2.5">
                    <div className={`p-2 rounded border ${CATEGORY_COLORS[selectedPlugin.category] || CATEGORY_COLORS['Custom']}`}>
                      {CATEGORY_ICONS[selectedPlugin.category] || CATEGORY_ICONS['Custom']}
                    </div>
                    <div>
                      <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider">{selectedPlugin.name}</h3>
                      <span className="text-[10px] text-ink-muted font-mono">{selectedPlugin.id}.py</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={!!isToggling}
                      onClick={() => handleToggleState(selectedPlugin)}
                      className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded border text-[10px] font-bold cursor-pointer transition-colors ${
                        selectedPlugin.enabled 
                          ? 'border-green-500/30 bg-green-500/10 text-green-400 hover:bg-green-500/25'
                          : 'border-border bg-surface-1 hover:bg-surface-2 text-ink-secondary'
                      }`}
                    >
                      {isToggling === selectedPlugin.id ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      ) : selectedPlugin.enabled ? (
                        <>
                          <ToggleRight className="w-4 h-4 text-success" />
                          <span>Désactiver</span>
                        </>
                      ) : (
                        <>
                          <ToggleLeft className="w-4 h-4 text-ink-muted" />
                          <span>Activer</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>

                <div className="space-y-4 relative z-10">
                  <div>
                    <div className="text-[9px] font-bold text-ink-muted uppercase tracking-wider mb-1">Description</div>
                    <p className="text-xs text-ink-secondary leading-relaxed font-normal">
                      {selectedPlugin.description}
                    </p>
                  </div>

                  {/* Config Form */}
                  <form onSubmit={handleSaveConfig} className="space-y-4 pt-2 border-t border-border">
                    <div className="text-[9px] font-bold text-ink-muted uppercase tracking-wider mb-2">Paramètres de l'extension</div>
                    
                    {Object.keys(selectedPlugin.schema).length === 0 ? (
                      <div className="p-3 rounded border border-border bg-surface-1 text-[10px] text-ink-muted italic">
                        Aucun paramètre configurable pour cette extension.
                      </div>
                    ) : (
                      <div className="space-y-3.5">
                        {Object.entries(selectedPlugin.schema).map(([key, field]) => {
                          const inputId = `config-${selectedPlugin.id}-${key}`;
                          const val = configForm[key] !== undefined ? configForm[key] : field.default;

                          return (
                            <div key={key} className="space-y-1.5">
                              <label htmlFor={inputId} className="flex justify-between items-baseline text-xs font-bold text-ink-primary">
                                <span>{field.title || key}</span>
                                <span className="text-[10px] text-ink-muted font-mono font-normal">({field.type})</span>
                              </label>

                              {field.type === 'boolean' ? (
                                <div className="flex items-center gap-2">
                                  <input
                                    id={inputId}
                                    type="checkbox"
                                    checked={!!val}
                                    onChange={(e) => setConfigForm(prev => ({ ...prev, [key]: e.target.checked }))}
                                    className="w-3.5 h-3.5 rounded border-border bg-[#06060a] text-accent-primary focus:ring-accent-primary"
                                  />
                                  <span className="text-[10px] text-ink-muted">{field.description}</span>
                                </div>
                              ) : field.type === 'integer' || field.type === 'number' ? (
                                <input
                                  id={inputId}
                                  type="number"
                                  value={val === undefined ? '' : val}
                                  onChange={(e) => setConfigForm(prev => ({ ...prev, [key]: parseInt(e.target.value) || 0 }))}
                                  placeholder={String(field.default || '')}
                                  className="input font-mono"
                                />
                              ) : (
                                <input
                                  id={inputId}
                                  type="text"
                                  value={val || ''}
                                  onChange={(e) => setConfigForm(prev => ({ ...prev, [key]: e.target.value }))}
                                  placeholder={String(field.default || '')}
                                  className="input"
                                />
                              )}

                              {field.type !== 'boolean' && field.description && (
                                <p className="text-[9px] text-ink-muted leading-normal mt-0.5">{field.description}</p>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {Object.keys(selectedPlugin.schema).length > 0 && (
                      <button
                        type="submit"
                        disabled={isSavingConfig}
                        className="btn btn-secondary w-full py-2 flex items-center justify-center gap-1.5"
                      >
                        {isSavingConfig ? (
                          <>
                            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            <span>Enregistrement...</span>
                          </>
                        ) : (
                          <>
                            <Check className="w-3.5 h-3.5 text-accent-primary" />
                            <span>Enregistrer la configuration</span>
                          </>
                        )}
                      </button>
                    )}
                  </form>

                  {/* Registered Hooks & Introspection */}
                  <div className="space-y-1.5 pt-3 border-t border-border">
                    <div className="text-[9px] font-bold text-ink-muted uppercase tracking-wider font-sans">Points de Hooks enregistrés</div>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedPlugin.hooks.length === 0 ? (
                        <span className="text-[10px] text-ink-muted italic">Aucun hook enregistré (plugin inactif)</span>
                      ) : (
                        selectedPlugin.hooks.map(h => (
                          <span key={h} className="px-2 py-0.5 font-mono text-[9px] font-bold rounded bg-surface-1 border border-border text-ink-primary">
                            {h}
                          </span>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Danger Zone (built-in plugins are protected) */}
                  {!['metrics', 'systemd', 'docker'].includes(selectedPlugin.id) && (
                    <div className="pt-4 border-t border-danger/20 space-y-2">
                      <div className="text-[9px] font-bold text-danger uppercase tracking-wider">Zone de danger</div>
                      <button
                        type="button"
                        disabled={isUninstalling}
                        onClick={() => setPluginToDelete(selectedPlugin.id)}
                        className="btn btn-danger w-full py-2 flex items-center justify-center gap-1.5"
                      >
                        {isUninstalling ? (
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="w-3.5 h-3.5" />
                        )}
                        <span>Désinstaller et supprimer l'extension</span>
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="card p-6 text-center italic text-xs text-ink-muted border border-border">
                Sélectionnez une extension pour afficher ses détails.
              </div>
            )}

            {/* Live Hook simulator console */}
            <div className="card p-5 space-y-4">
              <div className="flex justify-between items-center border-b border-border pb-3">
                <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider flex items-center gap-1.5">
                  <Terminal className="w-4 h-4 text-accent-primary" />
                  <span>Console des Extensions</span>
                </h3>
                <button 
                  onClick={() => setSimulatedLogs([`[SYSTEM] Logs effacés.`])}
                  className="text-[9px] font-bold text-accent-primary hover:underline cursor-pointer"
                >
                  Vider
                </button>
              </div>
              <div className="p-3.5 rounded bg-[#06060a] border border-border font-mono text-[10px] text-success/90 overflow-y-auto h-40 space-y-1 select-text scrollbar-thin">
                {simulatedLogs.map((log, idx) => {
                  let color = "text-success/80";
                  if (log.includes("[SUCCESS]")) color = "text-accent-primary font-bold";
                  else if (log.includes("[WARN]")) color = "text-warning";
                  else if (log.includes("[SYSTEM]")) color = "text-ink-muted";
                  return (
                    <div key={idx} className={`${color} leading-relaxed break-all`}>
                      {log}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Installation Modal */}
      {showInstallModal && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-md flex items-center justify-center z-50 p-4 animate-fade-in">
          <div className="card w-full max-w-2xl border border-border rounded-xl overflow-hidden shadow-2xl relative animate-fade-up">
            
            {/* Header */}
            <div className="p-5 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-bold text-ink-primary flex items-center gap-2">
                <Sparkles className="w-4.5 h-4.5 text-accent-primary animate-pulse" />
                <span>Installer une nouvelle extension</span>
              </h3>
              <button
                onClick={() => {
                  setError(null);
                  setShowInstallModal(false);
                }}
                className="text-xs text-ink-muted hover:text-ink-primary cursor-pointer font-bold"
              >
                Fermer
              </button>
            </div>

            {/* Tabs Selector */}
            <div className="flex border-b border-border bg-surface-1/30">
              <button
                onClick={() => setInstallTab('upload')}
                className={`flex-1 py-3 text-xs font-bold text-center border-b-2 cursor-pointer transition-colors ${
                  installTab === 'upload' ? 'border-accent-primary text-accent-primary bg-accent-subtle/5' : 'border-transparent text-ink-muted hover:text-ink-primary'
                }`}
              >
                Téléverser (.py)
              </button>
              <button
                onClick={() => setInstallTab('paste')}
                className={`flex-1 py-3 text-xs font-bold text-center border-b-2 cursor-pointer transition-colors ${
                  installTab === 'paste' ? 'border-accent-primary text-accent-primary bg-accent-subtle/5' : 'border-transparent text-ink-muted hover:text-ink-primary'
                }`}
              >
                Coller du code
              </button>
              <button
                onClick={() => setInstallTab('templates')}
                className={`flex-1 py-3 text-xs font-bold text-center border-b-2 cursor-pointer transition-colors ${
                  installTab === 'templates' ? 'border-accent-primary text-accent-primary bg-accent-subtle/5' : 'border-transparent text-ink-muted hover:text-ink-primary'
                }`}
              >
                Modèles pré-définis
              </button>
            </div>

            {/* Modal Body / Forms */}
            <form onSubmit={handleUploadSubmit} className="p-5 space-y-4">
              {installTab === 'upload' && (
                <div className="space-y-4">
                  <p className="text-[11px] text-ink-muted leading-relaxed">
                    Déposez ou sélectionnez un script Python (`.py`) contenant la fonction contractuelle `register(pm: PluginManager)`.
                  </p>
                  
                  <div className="border border-dashed border-border hover:border-accent-primary/50 rounded-xl p-8 text-center bg-surface-1/20 transition-colors relative cursor-pointer group">
                    <input
                      type="file"
                      accept=".py"
                      onChange={(e) => setUploadFile(e.target.files ? e.target.files[0] : null)}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    />
                    <Upload className="w-8 h-8 text-ink-muted group-hover:text-accent-primary mx-auto mb-2 transition-colors" />
                    <span className="block text-xs font-bold text-ink-primary">
                      {uploadFile ? uploadFile.name : "Sélectionner un script Python"}
                    </span>
                    <span className="block text-[10px] text-ink-muted mt-1">
                      {uploadFile ? `${(uploadFile.size / 1024).toFixed(1)} KB` : "Extension autorisée : .py uniquement"}
                    </span>
                  </div>
                </div>
              )}

              {installTab === 'paste' && (
                <div className="space-y-3">
                  <div className="space-y-1">
                    <label htmlFor="filename" className="text-[10px] font-bold text-ink-muted uppercase">Nom du fichier cible</label>
                    <input
                      id="filename"
                      type="text"
                      value={customFilename}
                      onChange={(e) => setCustomFilename(e.target.value)}
                      placeholder="mon_plugin.py"
                      className="input font-mono"
                    />
                  </div>
                  <div className="space-y-1">
                    <label htmlFor="code-area" className="text-[10px] font-bold text-ink-muted uppercase">Code source Python</label>
                    <textarea
                      id="code-area"
                      value={pastedCode}
                      onChange={(e) => setPastedCode(e.target.value)}
                      placeholder='def register(pm):&#10;    pm.register("on_status_report", my_handler)'
                      rows={10}
                      className="w-full p-3 rounded border border-border bg-[#06060a] text-xs text-success/90 font-mono focus:outline-none focus:border-accent-primary leading-relaxed"
                    />
                  </div>
                </div>
              )}

              {installTab === 'templates' && (
                <div className="space-y-3">
                  <p className="text-[11px] text-ink-muted leading-relaxed">
                    Sélectionnez un modèle pour charger et configurer une intégration pré-définie.
                  </p>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-h-[300px] overflow-y-auto pb-1 scrollbar-thin">
                    {TEMPLATE_PLUGINS.map(tpl => (
                      <div
                        key={tpl.id}
                        onClick={() => handleLoadTemplate(tpl)}
                        className="card p-4 hover:border-accent-primary bg-surface-1/30 cursor-pointer transition-all hover:scale-[1.01] flex flex-col justify-between"
                      >
                        <div className="space-y-1.5">
                          <h4 className="text-xs font-bold text-ink-primary flex items-center gap-1.5">
                            <BookOpen className="w-3.5 h-3.5 text-accent-primary" />
                            {tpl.name}
                          </h4>
                          <p className="text-[10px] text-ink-muted leading-relaxed">{tpl.description}</p>
                        </div>
                        <span className="text-[10px] font-bold uppercase text-accent-primary hover:underline mt-3 block text-right">Charger dans l'éditeur</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Form Actions */}
              {installTab !== 'templates' && (
                <div className="flex justify-end gap-3 pt-3 border-t border-border">
                  <button
                    type="button"
                    onClick={() => setShowInstallModal(false)}
                    className="btn btn-secondary text-xs"
                  >
                    Annuler
                  </button>
                  <button
                    type="submit"
                    disabled={isUploading}
                    className="btn btn-primary text-xs flex items-center gap-1.5"
                  >
                    {isUploading ? (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Upload className="w-3.5 h-3.5" />
                    )}
                    <span>Installer l'extension</span>
                  </button>
                </div>
              )}
            </form>

          </div>
        </div>
      )}

      {/* CONFIRMATION DELETE MODAL */}
      {pluginToDelete && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-md flex items-center justify-center p-4 z-50 animate-fade-in select-none">
          <div className="w-full max-w-md card p-6 shadow-2xl space-y-5 animate-fade-up">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-danger-subtle border border-danger/25 flex items-center justify-center text-danger">
                <ShieldAlert className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-ink-primary uppercase tracking-wider">{t('plugins.confirm_uninstall')}</h3>
                <p className="text-[9px] text-danger font-semibold uppercase">Action irréversible</p>
              </div>
            </div>

            <p className="text-xs text-ink-secondary leading-relaxed">
              Êtes-vous sûr de vouloir désinstaller et supprimer définitivement l'extension <strong className="text-ink-primary font-semibold">{pluginToDelete}</strong> ? Cette action est irréversible et supprimera le script Python du serveur.
            </p>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setPluginToDelete(null)}
                disabled={isUninstalling}
                className="btn btn-secondary text-xs"
              >
                Annuler
              </button>
              <button
                type="button"
                onClick={handleDeletePluginConfirm}
                disabled={isUninstalling}
                className="btn btn-danger text-xs flex items-center gap-1.5"
              >
                {isUninstalling ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                <span>Confirmer</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
