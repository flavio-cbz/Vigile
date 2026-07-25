import { useEffect, useState } from 'react';
import { X, RefreshCw, Save } from 'lucide-react';
import { type Node } from '../../store/nodeStore';
import { useToastStore } from '../../store/useToastStore';
import { nodeMutations } from '../../store/nodeMutations';
import { useLocale } from '../../i18n';

interface RenameNodeModalProps {
  node: Node;
  onClose: () => void;
}

export const RenameNodeModal = ({ node, onClose }: RenameNodeModalProps) => {
  const { t } = useLocale();
  const [name, setName] = useState(node.name || '');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const addToast = useToastStore((s) => s.addToast);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (trimmed === '' || trimmed === node.name) {
      onClose();
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await nodeMutations.renameNode(node.id, trimmed);
      addToast('success', t('servers.toast.renamed'), trimmed);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/85 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-fade-in"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md bg-surface-0 border border-border p-6 rounded-xl shadow-2xl space-y-5 animate-fade-up relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-ink-muted hover:text-ink cursor-pointer"
        >
          <X className="w-4 h-4" />
        </button>
        <div>
          <h3 className="text-sm font-bold text-ink-primary uppercase tracking-wider">
            {t('rename.title')}
          </h3>
          <p className="text-[0.625rem] text-ink-secondary mt-1 leading-relaxed">
            {t('rename.subtitle')}
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
              {t('rename.name_label')}
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              required
              className="input"
            />
          </div>

          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="btn btn-secondary flex-1 py-2 text-[0.625rem]"
            >
              {t('settings.cancel')}
            </button>
            <button
              type="submit"
              disabled={submitting || name.trim() === ''}
              className="btn btn-primary flex-1 py-2 text-[0.625rem]"
            >
              {submitting ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <>
                  <Save className="w-3.5 h-3.5" />
                  <span>{t('rename.save')}</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
