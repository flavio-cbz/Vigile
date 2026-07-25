import React, { useState } from 'react';
import { useLocale } from '../../i18n';
import { Check, Copy } from 'lucide-react';

interface CopyableIdProps {
  /**
   * The full identifier (UUID, hash, etc.) to display and copy.
   * If `null`/`undefined`/empty, the component renders nothing.
   */
  value: string | null | undefined;
  /**
   * Optional label rendered before the identifier (e.g. "ID:").
   */
  label?: string;
  /**
   * Optional className passed to the root element.
   */
  className?: string;
  /**
   * Title attribute for the tooltip showing the full value.
   * Defaults to the value itself.
   */
  title?: string;
  /**
   * Show the full identifier inline (no truncation). Defaults to true.
   * When true, the full value is rendered and may wrap.
   */
  full?: boolean;
}

/**
 * Displays a full identifier (UUID, etc.) with a copy-to-clipboard button
 * and a tooltip containing the complete value. Renders a Check icon
 * for 2s after a successful copy.
 */
const CopyableId: React.FC<CopyableIdProps> = ({
  value,
  label,
  className = '',
  title,
  full = true,
}) => {
  const { t } = useLocale();
  const [copied, setCopied] = useState(false);

  if (!value) return null;

  const displayValue = full ? value : value;

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {
      // Clipboard write can fail in non-secure contexts; silent fallback.
    });
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono text-[10.5px] text-text-2 break-all ${className}`}
      title={title ?? value}
    >
      {label && <span className="text-text-3 font-sans">{label}</span>}
      <span className="break-all">{displayValue}</span>
      <button
        type="button"
        onClick={handleCopy}
        className="inline-flex items-center justify-center p-1 rounded border border-border bg-surface-3 hover:border-accent/40 hover:text-text-1 text-text-2 transition-colors cursor-pointer shrink-0"
        title={t("ui.copy_id_title")}
        aria-label={t("ui.copy_id_aria")}
      >
        {copied ? (
          <Check className="w-3 h-3 text-severity-ok" />
        ) : (
          <Copy className="w-3 h-3 opacity-70 hover:opacity-100" />
        )}
      </button>
    </span>
  );
};

export default CopyableId;
export { CopyableId };
