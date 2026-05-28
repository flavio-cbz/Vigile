import React, { useState, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { useToastStore } from '../store/useToastStore';
import { useLocale } from '../i18n';
import { api } from '../hooks/useApi';
import { 
  User, 
  Settings as SettingsIcon, 
  Key, 
  Cpu, 
  Lock, 
  RefreshCw, 
  Activity, 
  Database,
  Network,
  ShieldCheck,
  AlertTriangle,
  Eye,
  EyeOff,
  Globe
} from 'lucide-react';

interface SystemSettingsResponse {
  master_url: string;
  host: string;
  port: number;
  debug: boolean;
  database_path: string;
  server_secret_key: string;
  jwt_secret_key: string;
  jwt_algorithm: string;
  jwt_access_token_ttl: number;
  jwt_refresh_token_ttl: number;
  join_token_ttl: number;
  worker_token_ttl: number;
  worker_token_rotation: number;
  heartbeat_interval: number;
  heartbeat_lost_threshold: number;
  heartbeat_stale_threshold: number;
  master_key_path: string;
  cors_origins: string[];
  trusted_proxies: string[];
  enforce_https: boolean;
  llm_base_url: string;
  llm_api_key: string;
  llm_model: string;
  plugins_dir: string;
}

export const Settings: React.FC = () => {
  const { accessToken, user, logout } = useAuthStore();
  const { addToast } = useToastStore();
  const { locale, setLocale, t } = useLocale();
  
  const [activeTab, setActiveTab] = useState<'profile' | 'system'>('profile');
  const isAdmin = user?.role === 'admin';

  // Profile / Password change states
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);

  // System settings states
  const [systemSettings, setSystemSettings] = useState<SystemSettingsResponse | null>(null);
  const [systemLoading, setSystemLoading] = useState(false);
  const [systemError, setSystemError] = useState<string | null>(null);

  // LLM config states
  const [llmModel, setLlmModel] = useState('');
  const [llmBaseUrl, setLlmBaseUrl] = useState('');
  const [llmApiKey, setLlmApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmTesting, setLlmTesting] = useState(false);

  // Sync LLM states when systemSettings changes
  useEffect(() => {
    if (systemSettings) {
      setLlmModel(systemSettings.llm_model || '');
      setLlmBaseUrl(systemSettings.llm_base_url || '');
      setLlmApiKey(systemSettings.llm_api_key || '');
    }
  }, [systemSettings]);

  const handleTestLlmConnection = async () => {
    if (user?.username === 'demo') {
      addToast('error', 'Action non autorisée', 'Le compte de démonstration ne peut pas tester la configuration LLM.');
      return;
    }
    setLlmTesting(true);
    try {
      const data = await api<{ message: string }>('/api/admin/settings/llm/test', {
        method: 'POST',
        body: JSON.stringify({
          llm_base_url: llmBaseUrl,
          llm_api_key: llmApiKey,
          llm_model: llmModel
        })
      });
      if (data) {
        addToast('success', 'Connexion LLM réussie', data.message || 'La configuration LLM est valide.');
      }
    } catch (err: any) {
      addToast('error', 'Échec de connexion LLM', err.message || 'Une erreur est survenue.');
    } finally {
      setLlmTesting(false);
    }
  };

  const handleSaveLlmSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    if (user?.username === 'demo') {
      addToast('error', 'Action non autorisée', 'Le compte de démonstration ne peut pas modifier la configuration LLM.');
      return;
    }
    setLlmSaving(true);
    try {
      const data = await api<SystemSettingsResponse>('/api/admin/settings/llm', {
        method: 'POST',
        body: JSON.stringify({
          llm_base_url: llmBaseUrl,
          llm_api_key: llmApiKey,
          llm_model: llmModel
        })
      });
      if (data) {
        setSystemSettings(data);
        addToast('success', 'Configuration enregistrée', 'Les paramètres LLM ont été enregistrés avec succès et appliqués.');
      }
    } catch (err: any) {
      addToast('error', 'Erreur d\'enregistrement', err.message || 'Une erreur est survenue lors de l\'enregistrement.');
    } finally {
      setLlmSaving(false);
    }
  };

  // Fetch system settings
  const fetchSystemSettings = async () => {
    if (!isAdmin) return;
    setSystemLoading(true);
    setSystemError(null);
    try {
      const data = await api<SystemSettingsResponse>('/api/admin/settings');
      if (data) {
        setSystemSettings(data);
      }
    } catch (err: any) {
      setSystemError(err.message || "Impossible de charger les paramètres système.");
    } finally {
      setSystemLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'system' && isAdmin && !systemSettings) {
      fetchSystemSettings();
    }
  }, [activeTab, isAdmin]);

  // Handle password change
  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!oldPassword || !newPassword || !confirmPassword) {
      addToast('error', 'Champs manquants', 'Veuillez remplir tous les champs du formulaire.');
      return;
    }

    if (newPassword.length < 8) {
      addToast('error', 'Mot de passe trop court', 'Le nouveau mot de passe doit faire au moins 8 caractères.');
      return;
    }

    if (newPassword !== confirmPassword) {
      addToast('error', 'Mots de passe différents', 'La confirmation du mot de passe ne correspond pas.');
      return;
    }

    setPasswordLoading(true);
    try {
      const res = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`
        },
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword
        })
      });

      if (res.ok) {
        addToast('success', 'Mot de passe modifié', 'Votre mot de passe a été mis à jour. Veuillez vous reconnecter.');
        setOldPassword('');
        setNewPassword('');
        setConfirmPassword('');
        setTimeout(() => {
          logout();
        }, 1500);
      } else {
        const errData = await res.json().catch(() => ({}));
        addToast('error', 'Erreur de modification', errData.detail || 'Une erreur est survenue lors de la modification.');
      }
    } catch (err) {
      addToast('error', 'Erreur réseau', 'Impossible de se connecter au serveur.');
    } finally {
      setPasswordLoading(false);
    }
  };

  // Render Time duration helper
  const formatDuration = (seconds: number) => {
    if (seconds >= 86400) {
      const days = Math.round(seconds / 86400);
      return `${days} jour${days > 1 ? 's' : ''} (${seconds}s)`;
    }
    if (seconds >= 3600) {
      const hours = Math.round(seconds / 3600);
      return `${hours} heure${hours > 1 ? 's' : ''} (${seconds}s)`;
    }
    if (seconds >= 60) {
      const mins = Math.round(seconds / 60);
      return `${mins} minute${mins > 1 ? 's' : ''} (${seconds}s)`;
    }
    return `${seconds} secondes`;
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border pb-6">
        <div>
          <h1 className="text-lg font-bold text-ink-primary tracking-tight flex items-center gap-2">
            <SettingsIcon className="w-5 h-5 text-accent-primary" />
            <span>{t('settings.title')}</span>
          </h1>
          <p className="text-xs text-ink-muted mt-1">
            Gérez vos identifiants d'accès personnels et supervisez la configuration générale du Master Vigile.
          </p>
        </div>
      </div>

      {/* Tabs list */}
      <div className="flex items-center gap-2 border-b border-border pb-px shrink-0">
        <button
          onClick={() => setActiveTab('profile')}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold border-b-2 transition-all cursor-pointer ${
            activeTab === 'profile'
              ? 'border-accent-primary text-accent-primary bg-accent-subtle'
              : 'border-transparent text-ink-muted hover:text-ink-primary hover:bg-surface-1'
          }`}
        >
          <User className="w-4 h-4" />
          <span>Mon Profil & Langue</span>
        </button>
        {isAdmin && (
          <button
            onClick={() => setActiveTab('system')}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold border-b-2 transition-all cursor-pointer ${
              activeTab === 'system'
                ? 'border-accent-primary text-accent-primary bg-accent-subtle'
                : 'border-transparent text-ink-muted hover:text-ink-primary hover:bg-surface-1'
            }`}
          >
            <SettingsIcon className="w-4 h-4" />
            <span>{t('nav.settings') || 'Configuration Système'}</span>
          </button>
        )}
      </div>

      {/* Tab Panels */}
      <div className="space-y-6">
        {/* Profile Tab Panel */}
        {activeTab === 'profile' && (
          <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
            {/* User Metadata & Language Picker */}
            <div className="xl:col-span-5 space-y-6">
              {/* Account Details */}
              <div className="card p-5">
                <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider mb-4 flex items-center gap-2">
                  <User className="w-4 h-4 text-accent-primary" />
                  <span>Détails du compte</span>
                </h3>
                <div className="space-y-4">
                  <div className="flex items-center gap-3 p-3 bg-surface-1 rounded border border-border">
                    <div className="w-10 h-10 rounded-full border border-accent-primary bg-accent-subtle flex items-center justify-center text-accent-primary shrink-0 font-bold uppercase">
                      {user?.username?.substring(0, 2) || 'US'}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-bold text-ink-primary truncate">{user?.username}</div>
                      <div className="text-[10px] font-bold text-ink-muted uppercase tracking-wider mt-0.5">{user?.role}</div>
                    </div>
                  </div>

                  <div className="space-y-3 pt-2">
                    <div className="flex justify-between items-center text-xs py-1.5 border-b border-border/40">
                      <span className="text-ink-secondary">Identifiant unique</span>
                      <span className="font-mono text-ink-primary font-medium select-all">{user?.user_id}</span>
                    </div>
                    <div className="flex justify-between items-center text-xs py-1.5 border-b border-border/40">
                      <span className="text-ink-secondary">Rôle système</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-accent-subtle border border-accent-primary/20 text-accent-primary">
                        {user?.role}
                      </span>
                    </div>
                    <div className="flex justify-between items-center text-xs py-1.5">
                      <span className="text-ink-secondary">Mode démonstration</span>
                      <span className="font-semibold text-ink-primary">
                        {user?.username === 'demo' ? (
                          <span className="text-warning flex items-center gap-1">
                            <AlertTriangle className="w-3.5 h-3.5" />
                            Actif
                          </span>
                        ) : 'Inactif'}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Language Selector Card */}
              <div className="card p-5 space-y-4">
                <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider flex items-center gap-2">
                  <Globe className="w-4 h-4 text-accent-primary" />
                  <span>{t('settings.language')}</span>
                </h3>
                <div className="space-y-2">
                  <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider">Language / Langue</label>
                  <select
                    value={locale}
                    onChange={(e) => setLocale(e.target.value as any)}
                    className="select text-xs"
                  >
                    <option value="fr">{t('settings.lang_fr')}</option>
                    <option value="en">{t('settings.lang_en')}</option>
                  </select>
                </div>
              </div>

              {/* Security Advisory */}
              <div className="p-4 rounded border border-border bg-surface-1/35 space-y-2">
                <h4 className="text-xs font-bold text-ink-primary uppercase tracking-wider flex items-center gap-1.5">
                  <ShieldCheck className="w-4 h-4 text-success" />
                  <span>Politique de Sécurité Vigile</span>
                </h4>
                <p className="text-[10px] text-ink-muted leading-relaxed">
                  Vigile fonctionne selon un principe de moindre privilège et applique un chiffrement robuste de bout en bout. 
                  En modifiant votre mot de passe, l'ensemble des jetons de rafraîchissement (`refresh_tokens`) rattachés à votre profil seront révoqués sur-le-champ pour prévenir toute tentative d'usurpation de session active.
                </p>
              </div>
            </div>

            {/* Change Password Form */}
            <div className="xl:col-span-7">
              <div className="card p-5 space-y-4">
                <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider flex items-center gap-2">
                  <Key className="w-4 h-4 text-accent-primary" />
                  <span>Modifier mon mot de passe</span>
                </h3>
                
                {user?.username === 'demo' ? (
                  <div className="p-3.5 rounded border border-warning/20 bg-warning-subtle text-xs text-warning leading-relaxed flex items-start gap-2.5">
                    <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                    <span>
                      La modification du mot de passe est désactivée pour le compte de démonstration (`demo`).
                    </span>
                  </div>
                ) : (
                  <form onSubmit={handlePasswordChange} className="space-y-4 pt-1">
                    <div className="space-y-1.5">
                      <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider">
                        Mot de passe actuel
                      </label>
                      <input
                        type="password"
                        value={oldPassword}
                        onChange={(e) => setOldPassword(e.target.value)}
                        placeholder="Saisissez votre mot de passe actuel..."
                        disabled={passwordLoading}
                        className="input"
                        required
                      />
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-1.5">
                        <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider">
                          Nouveau mot de passe
                        </label>
                        <input
                          type="password"
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          placeholder="8 caractères min..."
                          disabled={passwordLoading}
                          className="input"
                          required
                        />
                      </div>
                      <div className="space-y-1.5">
                        <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider">
                          Confirmer le mot de passe
                        </label>
                        <input
                          type="password"
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          placeholder="Répétez le mot de passe..."
                          disabled={passwordLoading}
                          className="input"
                          required
                        />
                      </div>
                    </div>

                    <button
                      type="submit"
                      disabled={passwordLoading}
                      className="btn btn-primary py-2 px-5 flex items-center justify-center gap-2"
                    >
                      {passwordLoading ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Lock className="w-3.5 h-3.5" />
                      )}
                      <span>Enregistrer le mot de passe</span>
                    </button>
                  </form>
                )}
              </div>
            </div>
          </div>
        )}

        {/* System Settings Tab Panel */}
        {activeTab === 'system' && isAdmin && (
          <div className="space-y-6">
            {systemLoading && (
              <div className="flex flex-col items-center justify-center py-12 space-y-3">
                <RefreshCw className="w-8 h-8 text-accent-primary animate-spin" />
                <span className="text-xs text-ink-muted">Récupération des variables de configuration...</span>
              </div>
            )}

            {systemError && (
              <div className="p-4 rounded border border-danger/20 bg-danger-subtle text-xs text-danger flex items-start gap-2.5">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <div className="space-y-1.5">
                  <p className="font-bold font-sans">Erreur de chargement</p>
                  <p className="text-ink-secondary">{systemError}</p>
                  <button 
                    onClick={fetchSystemSettings}
                    className="btn btn-secondary py-1 px-3 text-[10px]"
                  >
                    Réessayer
                  </button>
                </div>
              </div>
            )}

            {systemSettings && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                
                {/* 1. Copilot IA Config */}
                <div className="card p-5 space-y-4">
                  <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider flex items-center gap-2 border-b border-border pb-2">
                    <Cpu className="w-4 h-4 text-accent-primary" />
                    <span>Copilot IA</span>
                  </h3>
                  
                  {user?.username === 'demo' ? (
                    <div className="p-3.5 rounded border border-warning/20 bg-warning-subtle text-xs text-warning leading-relaxed flex items-start gap-2.5">
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                      <span>
                        La modification et le test de la configuration LLM sont désactivés pour le compte de démonstration (`demo`).
                      </span>
                    </div>
                  ) : null}

                  <form onSubmit={handleSaveLlmSettings} className="space-y-4 text-xs">
                    <div className="space-y-1.5">
                      <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider">
                        Modèle LLM
                      </label>
                      <input
                        type="text"
                        value={llmModel}
                        onChange={(e) => setLlmModel(e.target.value)}
                        placeholder="Ex: gpt-4o-mini, llama3..."
                        disabled={llmSaving || llmTesting || user?.username === 'demo'}
                        className="input font-mono"
                        required
                      />
                    </div>

                    <div className="space-y-1.5">
                      <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider">
                        Base URL
                      </label>
                      <input
                        type="text"
                        value={llmBaseUrl}
                        onChange={(e) => setLlmBaseUrl(e.target.value)}
                        placeholder="Ex: https://api.openai.com/v1"
                        disabled={llmSaving || llmTesting || user?.username === 'demo'}
                        className="input font-mono"
                        required
                      />
                    </div>

                    <div className="space-y-1.5">
                      <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider">
                        Clé API
                      </label>
                      <div className="relative">
                        <input
                          type={showApiKey ? "text" : "password"}
                          value={llmApiKey}
                          onChange={(e) => setLlmApiKey(e.target.value)}
                          placeholder="Clé API de votre fournisseur LLM..."
                          disabled={llmSaving || llmTesting || user?.username === 'demo'}
                          className="input font-mono pr-10"
                        />
                        <button
                          type="button"
                          onClick={() => setShowApiKey(!showApiKey)}
                          disabled={user?.username === 'demo'}
                          className="absolute right-3.5 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink-primary cursor-pointer border-0 bg-transparent"
                        >
                          {showApiKey ? (
                            <EyeOff className="w-4 h-4" />
                          ) : (
                            <Eye className="w-4 h-4" />
                          )}
                        </button>
                      </div>
                    </div>

                    <div className="flex flex-col sm:flex-row gap-3 pt-2">
                      <button
                        type="button"
                        onClick={handleTestLlmConnection}
                        disabled={llmSaving || llmTesting || !llmBaseUrl || user?.username === 'demo'}
                        className="btn btn-secondary py-2 flex-1 flex items-center justify-center gap-2"
                      >
                        {llmTesting ? (
                          <RefreshCw className="w-3.5 h-3.5 animate-spin text-accent-primary" />
                        ) : (
                          <RefreshCw className="w-3.5 h-3.5" />
                        )}
                        <span>Tester la connexion</span>
                      </button>

                      <button
                        type="submit"
                        disabled={llmSaving || llmTesting || user?.username === 'demo'}
                        className="btn btn-primary py-2 flex-1 flex items-center justify-center gap-2"
                      >
                        {llmSaving ? (
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Lock className="w-3.5 h-3.5" />
                        )}
                        <span>Enregistrer</span>
                      </button>
                    </div>
                  </form>
                </div>

                {/* 2. Security & JWT Config */}
                <div className="card p-5 space-y-4">
                  <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider flex items-center gap-2 border-b border-border pb-2">
                    <ShieldCheck className="w-4 h-4 text-accent-primary" />
                    <span>Sécurité & Sessions</span>
                  </h3>
                  <div className="space-y-3 text-xs font-sans">
                    <div className="flex justify-between items-start py-1 border-b border-border/40">
                      <span className="text-ink-secondary">Forcer le HTTPS</span>
                      <span className={`font-semibold ${systemSettings.enforce_https ? 'text-success' : 'text-warning'}`}>
                        {systemSettings.enforce_https ? 'Actif' : 'Inactif'}
                      </span>
                    </div>
                    <div className="flex justify-between items-start py-1 border-b border-border/40">
                      <span className="text-ink-secondary">Algorithme de Signature</span>
                      <span className="font-mono text-ink-primary text-right">{systemSettings.jwt_algorithm}</span>
                    </div>
                    <div className="flex justify-between items-start py-1 border-b border-border/40">
                      <span className="text-ink-secondary">TTL Access Token</span>
                      <span className="font-mono text-ink-primary text-right">{formatDuration(systemSettings.jwt_access_token_ttl)}</span>
                    </div>
                    <div className="flex justify-between items-start py-1">
                      <span className="text-ink-secondary">TTL Refresh Token</span>
                      <span className="font-mono text-ink-primary text-right">{formatDuration(systemSettings.jwt_refresh_token_ttl)}</span>
                    </div>
                  </div>
                </div>

                {/* 3. Enrollment Config */}
                <div className="card p-5 space-y-4">
                  <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider flex items-center gap-2 border-b border-border pb-2">
                    <Network className="w-4 h-4 text-accent-primary" />
                    <span>Enrôlement des serveurs (Zero-Trust)</span>
                  </h3>
                  <div className="space-y-3 text-xs font-sans">
                    <div className="flex justify-between items-start py-1 border-b border-border/40">
                      <span className="text-ink-secondary">TTL Token d'enrôlement</span>
                      <span className="font-mono text-ink-primary text-right">{formatDuration(systemSettings.join_token_ttl)}</span>
                    </div>
                    <div className="flex justify-between items-start py-1 border-b border-border/40">
                      <span className="text-ink-secondary">TTL Token d'opération</span>
                      <span className="font-mono text-ink-primary text-right">{formatDuration(systemSettings.worker_token_ttl)}</span>
                    </div>
                    <div className="flex justify-between items-start py-1">
                      <span className="text-ink-secondary">Rotation Token d'opération</span>
                      <span className="font-mono text-ink-primary text-right">{formatDuration(systemSettings.worker_token_rotation)}</span>
                    </div>
                  </div>
                </div>

                {/* 4. Heartbeat Config */}
                <div className="card p-5 space-y-4">
                  <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider flex items-center gap-2 border-b border-border pb-2">
                    <Activity className="w-4 h-4 text-accent-primary" />
                    <span>Surveillance & Heartbeats</span>
                  </h3>
                  <div className="space-y-3 text-xs font-sans">
                    <div className="flex justify-between items-start py-1 border-b border-border/40">
                      <span className="text-ink-secondary">Intervalle Heartbeat</span>
                      <span className="font-mono text-ink-primary text-right">{systemSettings.heartbeat_interval}s</span>
                    </div>
                    <div className="flex justify-between items-start py-1 border-b border-border/40">
                      <span className="text-ink-secondary">Seuil Perdu (Lost)</span>
                      <span className="font-mono text-ink-primary text-right">{formatDuration(systemSettings.heartbeat_lost_threshold)}</span>
                    </div>
                    <div className="flex justify-between items-start py-1">
                      <span className="text-ink-secondary">Seuil Obsolète (Stale)</span>
                      <span className="font-mono text-ink-primary text-right">{formatDuration(systemSettings.heartbeat_stale_threshold)}</span>
                    </div>
                  </div>
                </div>

                {/* 5. Database & System Config (Span 2 cols on desktop) */}
                <div className="card p-5 space-y-4 md:col-span-2">
                  <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider flex items-center gap-2 border-b border-border pb-2">
                    <Database className="w-4 h-4 text-accent-primary" />
                    <span>Hôte & Système</span>
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 text-xs font-sans">
                    <div className="flex justify-between items-center py-1 border-b border-border/40">
                      <span className="text-ink-secondary">Adresse d'Écoute (Host)</span>
                      <span className="font-mono text-ink-primary font-semibold">{systemSettings.host}</span>
                    </div>
                    <div className="flex justify-between items-center py-1 border-b border-border/40">
                      <span className="text-ink-secondary">Port du Master</span>
                      <span className="font-mono text-ink-primary font-semibold">{systemSettings.port}</span>
                    </div>
                    <div className="flex justify-between items-center py-1 border-b border-border/40">
                      <span className="text-ink-secondary">Mode Débogage (Debug)</span>
                      <span className={`font-semibold ${systemSettings.debug ? 'text-warning' : 'text-success'}`}>
                        {systemSettings.debug ? 'Activé' : 'Désactivé'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center py-1 border-b border-border/40">
                      <span className="text-ink-secondary">URL d'accès externe</span>
                      <span className="font-mono text-ink-primary break-all font-semibold">{systemSettings.master_url}</span>
                    </div>
                    <div className="flex justify-between items-start py-1 border-b border-border/40 md:col-span-2">
                      <span className="text-ink-secondary shrink-0 mr-4 font-sans">Base de données</span>
                      <span className="font-mono text-ink-primary break-all text-right font-medium">{systemSettings.database_path}</span>
                    </div>
                    <div className="flex justify-between items-start py-1 border-b border-border/40 md:col-span-2">
                      <span className="text-ink-secondary shrink-0 mr-4 font-sans">Clé privée Ed25519</span>
                      <span className="font-mono text-ink-primary break-all text-right font-medium">{systemSettings.master_key_path}</span>
                    </div>
                    <div className="flex justify-between items-start py-1 border-b border-border/40 md:col-span-2">
                      <span className="text-ink-secondary shrink-0 mr-4 font-sans">Répertoire Plugins</span>
                      <span className="font-mono text-ink-primary break-all text-right font-medium">{systemSettings.plugins_dir}</span>
                    </div>
                    <div className="flex justify-between items-start py-1 border-b border-border/40 md:col-span-2">
                      <span className="text-ink-secondary shrink-0 mr-4 font-sans">Origines CORS autorisées</span>
                      <span className="font-mono text-ink-primary break-all text-right font-medium">
                        {systemSettings.cors_origins.join(', ') || 'Aucune (sécurité renforcée)'}
                      </span>
                    </div>
                    <div className="flex justify-between items-start py-1 md:col-span-2">
                      <span className="text-ink-secondary shrink-0 mr-4 font-sans">Proxies de confiance</span>
                      <span className="font-mono text-ink-primary break-all text-right font-medium">
                        {systemSettings.trusted_proxies.join(', ') || 'Aucun'}
                      </span>
                    </div>
                  </div>
                </div>

              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
