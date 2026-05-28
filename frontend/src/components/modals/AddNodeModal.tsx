import React, { useState, useEffect } from 'react';
import { X, Plus, Copy, Check, RefreshCw } from 'lucide-react';
import { useNodeStore } from '../../store/nodeStore';
import { useToastStore } from '../../store/useToastStore';
import { api } from '../../hooks/useApi';
import { useLocale } from '../../i18n';

interface AddNodeModalProps {
  onClose: () => void;
}

export const AddNodeModal = ({ onClose }: AddNodeModalProps) => {
  const { t } = useLocale();
  const [nodeName, setNodeName] = useState('');
  const [ipPrefix, setIpPrefix] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [joinData, setJoinData] = useState<{ node_id: string; token: string; curl_command: string } | null>(null);
  const [enrollError, setEnrollError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [isEnrolled, setIsEnrolled] = useState(false);

  const addToast = useToastStore((s) => s.addToast);

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(key);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleGenerateJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!nodeName.trim()) return;

    setIsGenerating(true);
    setEnrollError(null);
    setJoinData(null);

    try {
      const data = await api<any>('/api/nodes/generate-join', {
        method: 'POST',
        body: JSON.stringify({
          name: nodeName,
          ip_prefix: ipPrefix || null,
        }),
      });

      if (data) {
        setJoinData(data);
        setNodeName('');
        setIpPrefix('');
        useNodeStore.getState().fetchNodes(); // Refresh list to see the PENDING node
      }
    } catch (err: any) {
      setEnrollError(err.message);
    } finally {
      setIsGenerating(false);
    }
  };

  // Polling for connection
  useEffect(() => {
    if (!joinData || !joinData.node_id || isEnrolled) return;

    const intervalId = setInterval(async () => {
      try {
        const nodes = await api<any[]>('/api/nodes', { skipToast: true });
        if (nodes) {
          const enrolledNode = nodes.find((n) => n.id === joinData.node_id);
          if (enrolledNode && enrolledNode.online) {
            setIsEnrolled(true);
            clearInterval(intervalId);
            addToast('success', t('add_node.success'), t('add_node.success'));
            useNodeStore.getState().fetchNodes();
            setTimeout(() => {
              onClose();
            }, 2500);
          }
        }
      } catch (err) {
        console.error('Error polling node enrollment:', err);
      }
    }, 5000);

    return () => {
      clearInterval(intervalId);
    };
  }, [joinData, addToast, onClose, isEnrolled, t]);

  return (
    <div className="fixed inset-0 bg-black/85 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-fade-in">
      <div className="w-full max-w-md bg-surface-0 border border-border p-6 rounded-xl shadow-2xl space-y-5 animate-fade-up relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-ink-muted hover:text-ink cursor-pointer"
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

        {isEnrolled && (
          <div className="p-3 rounded-lg bg-success-subtle border border-success/20 text-success text-xs font-semibold text-center animate-pulse">
            🎉 {t('add_node.success')}
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
              />
            </div>

            <div className="space-y-1">
              <label className="block text-[0.5625rem] font-bold text-ink-secondary uppercase tracking-wider">
                Restriction préfixe IP (Optionnel)
              </label>
              <input
                type="text"
                value={ipPrefix}
                onChange={(e) => setIpPrefix(e.target.value)}
                placeholder="ex. 192.168.1."
                className="input"
              />
            </div>

            <button
              type="submit"
              disabled={isGenerating}
              className="btn btn-primary w-full py-2"
            >
              {isGenerating ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <>
                  <Plus className="w-3.5 h-3.5" />
                  <span>{t('add_node.generate_token')}</span>
                </>
              )}
            </button>
          </form>
        ) : (
          <div className="space-y-4 animate-fade-in">
            {/* Waiting indicator */}
            {!isEnrolled && (
              <div className="flex items-center justify-center gap-2 p-2.5 bg-accent-subtle border border-accent-primary/20 rounded-lg text-accent-primary text-[0.625rem] font-medium leading-relaxed animate-pulse">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>{t('add_node.waiting')}</span>
              </div>
            )}

            <div className="space-y-1">
              <div className="flex justify-between items-center">
                <span className="text-[0.5rem] font-bold text-accent-primary uppercase tracking-wider">Jeton généré</span>
                <button
                  onClick={() => handleCopy(joinData.token, 'token')}
                  className="text-ink-secondary hover:text-accent-primary flex items-center gap-0.5 text-[0.625rem] font-bold cursor-pointer"
                >
                  {copiedId === 'token' ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
                  <span>{copiedId === 'token' ? 'Copié' : 'Copier'}</span>
                </button>
              </div>
              <div className="p-2 rounded-lg bg-surface-1 border border-border font-mono text-[0.5625rem] text-ink-primary break-all select-all">
                {joinData.token}
              </div>
            </div>

            <div className="space-y-1">
              <div className="flex justify-between items-center">
                <span className="text-[0.5rem] font-bold text-accent-primary uppercase tracking-wider">Commande Kickstart (SSH)</span>
                <button
                  onClick={() => handleCopy(joinData.curl_command, 'curl')}
                  className="text-ink-secondary hover:text-accent-primary flex items-center gap-0.5 text-[0.625rem] font-bold cursor-pointer"
                >
                  {copiedId === 'curl' ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
                  <span>{copiedId === 'curl' ? 'Copié' : 'Copier'}</span>
                </button>
              </div>
              <div className="p-2 rounded-lg bg-surface-1 border border-border font-mono text-[0.5625rem] text-ink-primary whitespace-pre-wrap break-all select-all">
                {joinData.curl_command}
              </div>
            </div>

            <div className="p-2 bg-warning-subtle border border-warning/20 rounded-lg text-[0.5625rem] text-warning leading-normal">
              Ce jeton de connexion est à usage unique et expirera dans 30 minutes. Exécutez la commande curl sur le serveur cible avec les privilèges root.
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
