import React, { useState } from 'react';
import { Check, Copy } from 'lucide-react';

interface HashChipProps {
  hash: string;
  className?: string;
}

export const HashChip: React.FC<HashChipProps> = ({ hash, className = '' }) => {
  const [copied, setCopied] = useState(false);

  if (!hash) return null;

  const displayHash = hash.length > 12 
    ? `${hash.substring(0, 6)}…${hash.substring(hash.length - 6)}`
    : hash;

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(hash).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <button
      onClick={handleCopy}
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-surface-3 border border-border hover:border-accent/40 text-[10px] font-mono text-text-2 hover:text-text-1 cursor-pointer transition-colors whitespace-nowrap ${className}`}
      title="Cliquer pour copier le hash"
    >
      <span>{displayHash}</span>
      {copied ? (
        <Check className="w-2.5 h-2.5 text-severity-ok" />
      ) : (
        <Copy className="w-2.5 h-2.5 opacity-60 hover:opacity-100" />
      )}
    </button>
  );
};
