import React, { useEffect, useState } from 'react';
import { Cpu, Lock, RefreshCw, Eye, EyeOff, AlertTriangle } from 'lucide-react';
import { api } from '../../hooks/useApi';
import { useLocale } from '../../i18n';
import { useAuthStore } from '../../store/authStore';
import { usePermission } from '../../hooks/usePermission';
import { Spinner } from '../primitives/Spinner';
import type { SystemSettingsResponse } from './types';

interface LLMSettingsTabProps {
  systemSettings: SystemSettingsResponse | null;
  onSettingsUpdated: (next: SystemSettingsResponse) => void;
}

type Feedback = { type: 'success' | 'error'; msg: string };

export const LLMSettingsTab: React.FC<LLMSettingsTabProps> = ({
  systemSettings,
  onSettingsUpdated,
}) => {
  const { t } = useLocale();
  const { user } = useAuthStore();
  const { isAdmin } = usePermission();

  const [llmModel, setLlmModel] = useState('');
  const [llmBaseUrl, setLlmBaseUrl] = useState('');
  const [llmApiKey, setLlmApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmTesting, setLlmTesting] = useState(false);
  const [llmFeedback, setLlmFeedback] = useState<Feedback | null>(null);

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (systemSettings) {
      setLlmModel(systemSettings.llm_model || '');
      setLlmBaseUrl(systemSettings.llm_base_url || '');
      setLlmApiKey(systemSettings.llm_api_key || '');
    }
  }, [systemSettings]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const handleTestLlmConnection = async () => {
    if (user?.username === 'guest') return;
    setLlmTesting(true);
    setLlmFeedback(null);
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
        setLlmFeedback({ type: 'success', msg: data.message || t('settings.llm_valid') });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : t('settings.llm_test_error');
      setLlmFeedback({ type: 'error', msg: message });
    } finally {
      setLlmTesting(false);
    }
  };

  const handleSaveLlmSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    if (user?.username === 'guest') return;
    setLlmSaving(true);
    setLlmFeedback(null);
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
        onSettingsUpdated(data);
        setLlmFeedback({ type: 'success', msg: t('settings.llm_saved') });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : t('settings.llm_save_error');
      setLlmFeedback({ type: 'error', msg: message });
    } finally {
      setLlmSaving(false);
    }
  };

  return (
    <div className="p-5 border border-border rounded-xl bg-surface shadow space-y-4">
      <h3 className="text-xs font-bold text-text-1 uppercase tracking-wider flex items-center gap-2 border-b border-border pb-2 font-interface">
        <Cpu className="w-4 h-4 text-accent" />
        <span>{t('settings.copilot_config')}</span>
      </h3>

      {llmFeedback && (
        <div className={`p-3.5 rounded border text-xs leading-relaxed font-semibold ${
          llmFeedback.type === 'success'
            ? 'bg-severity-ok/10 border-severity-ok/20 text-severity-ok'
            : 'bg-severity-critical/10 border-severity-critical/20 text-severity-critical'
        }`}>
          {llmFeedback.msg}
        </div>
      )}

      {user?.username === 'guest' && (
        <div className="p-3.5 rounded border border-warning/20 bg-warning-subtle text-xs text-warning leading-relaxed flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>
            {t('settings.llm_locked')}
          </span>
        </div>
      )}

      <form onSubmit={handleSaveLlmSettings} className="space-y-4 text-xs">
        <div className="space-y-1.5">
          <label className="block text-[10px] font-extrabold text-text-3 uppercase tracking-wider font-interface">
            {t('settings.llm_model')}
          </label>
          <input
            type="text"
            required
            disabled={llmSaving || llmTesting || user?.username === 'guest' || !isAdmin}
            value={llmModel}
            onChange={(e) => setLlmModel(e.target.value)}
            placeholder={t('settings.llm_model_placeholder')}
            className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded px-3.5 py-2.5 text-text-1 font-mono focus:outline-none placeholder:text-text-3"
          />
        </div>

        <div className="space-y-1.5">
          <label className="block text-[10px] font-extrabold text-text-3 uppercase tracking-wider font-interface">
            {t('settings.llm_endpoint')}
          </label>
          <input
            type="text"
            required
            disabled={llmSaving || llmTesting || user?.username === 'guest' || !isAdmin}
            value={llmBaseUrl}
            onChange={(e) => setLlmBaseUrl(e.target.value)}
            placeholder={t('settings.llm_endpoint_placeholder')}
            className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded px-3.5 py-2.5 text-text-1 font-mono focus:outline-none placeholder:text-text-3"
          />
        </div>

        <div className="space-y-1.5">
          <label className="block text-[10px] font-extrabold text-text-3 uppercase tracking-wider font-interface">
            {t('settings.llm_api_key')}
          </label>
          <div className="relative">
            <input
              type={showApiKey ? "text" : "password"}
              required
              disabled={llmSaving || llmTesting || user?.username === 'guest' || !isAdmin}
              value={llmApiKey}
              onChange={(e) => setLlmApiKey(e.target.value)}
              placeholder={t('settings.llm_api_key_placeholder')}
              className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded px-3.5 py-2.5 pr-10 text-text-1 font-mono focus:outline-none placeholder:text-text-3"
            />
            <button
              type="button"
              onClick={() => setShowApiKey(!showApiKey)}
              disabled={user?.username === 'guest' || !isAdmin}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-text-3 hover:text-text-1 cursor-pointer border-0 bg-transparent"
            >
              {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-3 pt-2 font-interface">
          <button
            type="button"
            onClick={handleTestLlmConnection}
            disabled={llmSaving || llmTesting || !llmBaseUrl || user?.username === 'guest' || !isAdmin}
            className="btn border border-border hover:border-border-strong py-2 flex-1 flex items-center justify-center gap-1.5 text-text-2 hover:text-text-1 rounded cursor-pointer disabled:opacity-50"
          >
            {llmTesting ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
            <span>{t('settings.llm_test')}</span>
          </button>

          <button
            type="submit"
            disabled={llmSaving || llmTesting || user?.username === 'guest' || !isAdmin}
            className="btn bg-accent hover:bg-accent-hover text-text-1 py-2 flex-1 flex items-center justify-center gap-1.5 rounded cursor-pointer shadow disabled:opacity-50"
          >
            {llmSaving ? (
              <Spinner size="sm" />
            ) : (
              <Lock className="w-3.5 h-3.5" />
            )}
            <span>{t('settings.save_password')}</span>
          </button>
        </div>
      </form>
    </div>
  );
};
