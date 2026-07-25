import React, { useState, useCallback } from 'react';
import {
  X,
  Plus,
  RefreshCw,
  Terminal,
} from 'lucide-react';
import { useNodeStore } from '../../store/nodeStore';
import { useToastStore } from '../../store/useToastStore';
import { api } from '../../hooks/useApi';
import { useLocale } from '../../i18n';
import { EnrollmentMonitor } from './EnrollmentMonitor';
import { JoinTokenDisplay } from './JoinTokenDisplay';

interface AddNodeModalProps {
  onClose: () => void;
}

export interface JoinResponse {
  node_id: string;
  token: string;
  curl_command: string;
  expires_in: number;
}

export const AddNodeModal = ({ onClose }: AddNodeModalProps) => {
  const { t } = useLocale();
  const [nodeName, setNodeName] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [joinData, setJoinData] = useState<JoinResponse | null>(null);
  const [enrollError, setEnrollError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [pendingName, setPendingName] = useState<string | null>(null);

  const addToast = useToastStore((s) => s.addToast);

  // ---- Token generation ----
  const generate = useCallback(async () => {
    if (!nodeName.trim() || isGenerating) return;
    setIsGenerating(true);
    setEnrollError(null);
    try {
      const data = await api<JoinResponse>('/api/nodes/generate-join', {
        method: 'POST',
        body: JSON.stringify({ name: nodeName }),
      });
      if (data) {
        setJoinData(data);
        setPendingName(nodeName);
        setNodeName('');
        useNodeStore.getState().fetchNodes();
      }
    } catch (err) {
      setEnrollError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsGenerating(false);
    }
  }, [nodeName, isGenerating]);

  const handleGenerateJoin = (e: React.FormEvent) => {
    e.preventDefault();
    void generate();
  };

  // ---- Manual refresh: re-issue token with the same name ----
  const handleRefresh = useCallback(async () => {
    if (!joinData || refreshing) return;
    setRefreshing(true);
    setEnrollError(null);
    try {
      const refreshName = pendingName || `${t('add_node.title')}-${Date.now()}`;
      const data = await api<JoinResponse>('/api/nodes/generate-join', {
        method: 'POST',
        body: JSON.stringify({ name: refreshName }),
      });
      if (data) {
        setJoinData(data);
      }
    } catch (err) {
      setEnrollError(err instanceof Error ? err.message : String(err));
    } finally {
      setRefreshing(false);
    }
  }, [joinData, pendingName, refreshing, t]);

  // ---- Enrollment success callback ----
  const handleEnrolled = useCallback(() => {
    addToast('success', t('add_node.success'), t('add_node.success'));
    useNodeStore.getState().fetchNodes();
  }, [addToast, t]);

  return (
    <div
      className="fixed inset-0 bg-black/85 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-fade-in"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl bg-surface-0 border border-border p-6 rounded-xl shadow-2xl space-y-5 animate-fade-up relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-ink-muted hover:text-ink cursor-pointer"
          aria-label={t('common.close')}
        >
          <X className="w-4 h-4" />
        </button>

        <div>
          <h3 className="text-sm font-bold text-ink-primary uppercase tracking-wider flex items-center gap-2">
            <Plus className="w-4 h-4 text-accent-primary" />
            <span>{t('add_node.title')}</span>
          </h3>
          <p className="text-[0.625rem] text-ink-secondary mt-1 leading-relaxed">
            Créez une clé d'accès unique pour connecter un nouveau serveur à la console Vigile.
          </p>
        </div>

        {enrollError && (
          <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-500 text-[0.625rem] font-medium leading-relaxed">
            {enrollError}
          </div>
        )}

        {!joinData ? (
          <form onSubmit={handleGenerateJoin} className="space-y-3">
            <div className="space-y-1">
              <label className="block text-[0.5625rem] font-bold text-ink-secondary uppercase tracking-wider">
                {t('add_node.name_label')}
              </label>
              <input
                type="text"
                required
                value={nodeName}
                onChange={(e) => setNodeName(e.target.value)}
                placeholder={t('add_node.name_placeholder')}
                className="input"
                autoFocus
              />
            </div>

            <button
              type="submit"
              disabled={isGenerating || !nodeName.trim()}
              className="btn btn-primary w-full py-2.5"
            >
              {isGenerating ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <>
                  <Terminal className="w-3.5 h-3.5" />
                  <span>{t('add_node.generate_token')}</span>
                </>
              )}
            </button>
          </form>
        ) : (
          <EnrollmentMonitor
            key={joinData.node_id}
            nodeId={joinData.node_id}
            onEnrolled={handleEnrolled}
            onClose={onClose}
          >
            {(isEnrolled) => (
              <>
                {isEnrolled && (
                  <div className="p-3 rounded-lg bg-success-subtle border border-success/20 text-success text-xs font-semibold text-center animate-pulse">
                    🎉 {t('add_node.success')}
                  </div>
                )}
                <JoinTokenDisplay
                  joinData={joinData}
                  isEnrolled={isEnrolled}
                  onRefresh={handleRefresh}
                  refreshing={refreshing}
                />
              </>
            )}
          </EnrollmentMonitor>
        )}
      </div>
    </div>
  );
};
