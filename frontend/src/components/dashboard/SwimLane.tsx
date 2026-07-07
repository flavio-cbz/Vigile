import React from 'react';
import { useLocale } from '../../i18n';
import type { LucideIcon } from 'lucide-react';

interface SwimLaneProps {
  title: string;
  icon: LucideIcon;
  subtitle?: React.ReactNode;
  onSeeAll?: () => void;
  seeAllLabel?: string;
  children: React.ReactNode;
  isLoading?: boolean;
  skeletonCount?: number;
  skeletonComponent?: React.ReactNode;
  className?: string;
  layout?: 'carousel' | 'grid';
  gridClassName?: string;
}

export const SwimLane: React.FC<SwimLaneProps> = ({
  title,
  icon: Icon,
  subtitle,
  onSeeAll,
  seeAllLabel,
  children,
  isLoading = false,
  skeletonCount = 4,
  skeletonComponent,
  className = '',
  gridClassName = '',
}) => {
  const { t } = useLocale();
  const resolvedSeeAllLabel = seeAllLabel ?? t('dash.view_all');

  return (
    <div className={`space-y-3 relative w-full animate-fade-in ${className}`}>
      <div className="flex items-center justify-between px-4 md:px-12">
        <div className="flex items-center gap-2">
          <Icon className="text-accent-primary w-4.5 h-4.5" />
          <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2">
            <h3 className="text-sm font-bold text-ink-primary tracking-wide uppercase">
              {title}
            </h3>
            {subtitle && (
              <span className="text-xs text-ink-secondary font-normal font-interface">
                {subtitle}
              </span>
            )}
          </div>
        </div>
        {onSeeAll && (
          <button
            onClick={onSeeAll}
            className="text-xs font-semibold text-accent-primary hover:text-accent-hover transition-colors duration-150 cursor-pointer"
          >
            {resolvedSeeAllLabel} →
          </button>
        )}
      </div>

      <div className="px-4 md:px-12">
        <div className={`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 pt-2 ${gridClassName}`}>
          {isLoading ? (
            <>
              {Array.from({ length: skeletonCount }).map((_, i) => (
                <div key={i}>
                  {skeletonComponent}
                </div>
              ))}
            </>
          ) : (
            children
          )}
        </div>
      </div>
    </div>
  );
};
