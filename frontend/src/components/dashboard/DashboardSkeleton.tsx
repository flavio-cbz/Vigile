import React from 'react';
import { Server as ServerIcon, Plus } from 'lucide-react';
import { useLocale } from '../../i18n';
import { useLayoutStore } from '../../store/layoutStore';
import { Spinner } from '../primitives/Spinner';

interface DashboardSkeletonProps {
  loading: boolean;
  hasNodes: boolean;
}

export const DashboardSkeleton: React.FC<DashboardSkeletonProps> = ({ loading, hasNodes }) => {
  const { t } = useLocale();

  if (loading) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-text-3 font-interface text-xs select-none">
        <Spinner size="md" />
        <span>{t('dash.loading_hud')}</span>
      </div>
    );
  }

  if (!hasNodes) {
    return (
      <div className="h-full flex flex-col items-center justify-center select-none animate-fade-in">
        <div className="card max-w-md w-full py-12 px-8 text-center flex flex-col items-center gap-5">
          <div className="w-14 h-14 rounded-xl bg-accent-muted/15 border border-accent/30 flex items-center justify-center shadow-[0_0_18px_var(--color-accent-glow)]">
            <ServerIcon className="w-7 h-7 text-accent" />
          </div>
          <div className="space-y-1.5">
            <h2 className="text-base font-bold font-interface text-text-1 uppercase tracking-wider">
              {t('dash.empty_title')}
            </h2>
            <p className="text-xs text-text-2 leading-relaxed max-w-sm mx-auto">
              {t('dash.empty_description')}
            </p>
          </div>
          <button
            type="button"
            onClick={() => useLayoutStore.getState().setAddNodeModalOpen(true)}
            className="btn btn-primary inline-flex items-center gap-2 px-5 py-2.5 text-xs font-interface font-semibold cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            {t('dash.empty_action')}
          </button>
        </div>
      </div>
    );
  }

  return null;
};
