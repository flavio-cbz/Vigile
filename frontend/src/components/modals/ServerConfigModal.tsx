import { useEffect, useState } from 'react';
import { Server, X } from 'lucide-react';
import { useNodeStore } from '../../store/nodeStore';
import { useToastStore } from '../../store/useToastStore';
import { useLocale } from '../../i18n';

export const ServerConfigModal = () => {
  const { t } = useLocale();
  const pending = useNodeStore((s) => s.pendingConfiguration);
  const closeServerConfig = useNodeStore((s) => s.closeServerConfig);
  const configureNode = useNodeStore((s) => s.configureNode);
  const addToast = useToastStore((s) => s.addToast);

  const [name, setName] = useState('');
  const [group, setGroup] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset form when pending node changes
  useEffect(() => {
    if (pending) {
      setName(pending.hostname || pending.name || '');
      setGroup(pending.group || '');
    } else {
      setName('');
      setGroup('');
    }
    setError(null);
    setSubmitting(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending?.id]);

  useEffect(() => {
    if (!pending) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeServerConfig();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [pending, closeServerConfig]);

  if (!pending) return null;

  const hostLabel = pending.hostname || pending.name;
  const titleTemplate = t('server_config.title');
  const title = titleTemplate.includes('X')
    ? titleTemplate.replace('X', hostLabel)
    : `${titleTemplate} ${hostLabel}`;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await configureNode(pending.id, name.trim(), group.trim());
      addToast('success', t('server_config.success'), t('server_config.success_detail').replace('X', name.trim()));
      closeServerConfig();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/85 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-fade-in">
      <div className="w-full max-w-md bg-surface-0 border border-border p-6 rounded-xl shadow-2xl space-y-5 animate-fade-up relative">
        <button
          onClick={closeServerConfig}
          className="absolute top-4 right-4 text-ink-muted hover:text-ink cursor-pointer"
          aria-label={t("modal.close_aria")}
        >
          <X className="w-4 h-4" />
        </button>

        <div>
          <h3 className="text-sm font-bold text-ink-primary uppercase tracking-wider flex items-center gap-2">
            <Server className="w-4 h-4 text-accent-primary" />
            <span>{title}</span>
          </h3>
          <p className="text-[0.625rem] text-ink-secondary mt-1 leading-relaxed">
            {t('server_config.subtitle')}
          </p>
        </div>

        {error && (
          <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-500 text-[0.625rem] font-medium leading-relaxed">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-1">
            <label className="block text-[0.5625rem] font-bold text-ink-secondary uppercase tracking-wider">
              {t('server_config.name_label')}
            </label>
            <input
              type="text"
              required
              minLength={1}
              maxLength={128}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input"
            />
          </div>

          <div className="space-y-1">
            <label className="block text-[0.5625rem] font-bold text-ink-secondary uppercase tracking-wider">
              {t('server_config.group_label')}
            </label>
            <input
              type="text"
              maxLength={128}
              value={group}
              onChange={(e) => setGroup(e.target.value)}
              className="input"
            />
          </div>

          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={closeServerConfig}
              disabled={submitting}
              className="btn btn-secondary flex-1 py-2"
            >
              {t('server_config.later')}
            </button>
            <button
              type="submit"
              disabled={submitting || !name.trim()}
              className="btn btn-primary flex-1 py-2"
            >
              {t('server_config.save')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
