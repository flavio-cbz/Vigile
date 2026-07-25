import React from 'react';

interface ChartAxisProps {
  period: '24h' | '7d';
  t: (key: string) => string;
}

export const ChartAxis: React.FC<ChartAxisProps> = ({ period, t }) => {
  return (
    <div className="flex items-center justify-between text-[9px] text-text-3 font-semibold uppercase tracking-wider">
      <span>
        {period === '24h' ? t('trend.timeline_24h') : t('trend.timeline_7d')}
      </span>
      <span className="w-12 h-[1px] bg-border-strong/40 flex-1 mx-2" />
      <span>{t('trend.timeline_now')}</span>
    </div>
  );
};
