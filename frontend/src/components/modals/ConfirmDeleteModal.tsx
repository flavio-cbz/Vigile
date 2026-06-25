import { useEffect, useState } from 'react';
import { useLocale } from '../../i18n';
import { X, Trash2, RefreshCw } from 'lucide-react';

interface ConfirmDeleteModalProps {
  title: string;
  message: string;
  confirmWord: string;
  onConfirm: () => Promise<void> | void;
  onClose: () => void;
  confirmLabel?: string;
}

export const ConfirmDeleteModal = ({
  title,
  message,
  confirmWord,
  onConfirm,
  onClose,
  confirmLabel = 'Supprimer définitivement',
}: ConfirmDeleteModalProps) => {
  const { t } = useLocale();
  const [value, setValue] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const matches = value === confirmWord;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!matches || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
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
          <h3 className="text-sm font-bold text-red-500 uppercase tracking-wider flex items-center gap-2">
            <Trash2 className="w-4 h-4" />
            <span>{title}</span>
          </h3>
          <p className="text-[0.625rem] text-ink-secondary mt-1 leading-relaxed">{message}</p>
        </div>

        {error && (
          <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-500 text-[0.625rem] font-medium leading-relaxed">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-1">
            <label className="block text-[0.5625rem] font-bold text-ink-secondary uppercase tracking-wider">
              {t('confirm_delete.label')}
            </label>
            <input
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              autoFocus
              placeholder={t('modal.type_to_confirm', { word: confirmWord })}
              className="input font-mono"
            />
            <p className="text-[0.5625rem] text-ink-muted leading-relaxed">
              {t('modal.type_exact_name')}
            </p>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="btn btn-secondary flex-1 py-2 text-[0.625rem]"
            >
              {t('modal.cancel')}
            </button>
            <button
              type="submit"
              disabled={!matches || submitting}
              className="btn btn-danger flex-1 py-2 text-[0.625rem]"
            >
              {submitting ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <>
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>{confirmLabel}</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
