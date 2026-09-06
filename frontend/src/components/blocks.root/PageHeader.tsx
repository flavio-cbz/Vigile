import React from 'react';
import { ArrowLeft } from 'lucide-react';

interface PageHeaderProps {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  badge?: React.ReactNode;
  back?: { label?: string; onClick: () => void };
  className?: string;
}

/**
 * En-tête de page canonique — utilisé par toutes les pages (principales et plugins).
 * L'identité visuelle repose exclusivement sur les tokens du thème (accent, text-*,
 * border-*) afin de rester cohérente quel que soit le thème actif (warm-dark,
 * cool-dark, gray-dark, light).
 */
export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  subtitle,
  icon,
  actions,
  badge,
  back,
  className = '',
}) => {
  return (
    <div className={`flex flex-col gap-3 ${className}`}>
      {back && (
        <button
          onClick={back.onClick}
          className="self-start inline-flex items-center gap-2 px-3 py-1.5 bg-surface hover:bg-surface-2 border border-border text-[10px] rounded font-interface font-bold uppercase tracking-widest text-text-2 hover:text-text-1 cursor-pointer transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>{back.label ?? 'Retour'}</span>
        </button>
      )}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border-strong/20 pb-5">
        <div className="flex items-center gap-3 min-w-0">
          {icon && (
            <div className="w-10 h-10 rounded-xl bg-accent/10 border border-accent/20 text-accent flex items-center justify-center shadow-sm shrink-0">
              {icon}
            </div>
          )}
          <div className="min-w-0">
            <h1 className="font-interface text-xl font-extrabold tracking-wider uppercase text-text-1 flex items-center gap-2">
              <span className="truncate">{title}</span>
              {badge}
            </h1>
            {subtitle && (
              <p className="text-[10px] text-text-3 font-semibold uppercase tracking-wider mt-0.5">
                {subtitle}
              </p>
            )}
          </div>
        </div>
        {actions && <div className="flex items-center gap-2.5 shrink-0">{actions}</div>}
      </div>
    </div>
  );
};
