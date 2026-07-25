import React from 'react';

interface PeriodSelectorProps {
  period: '24h' | '7d';
  onPeriodChange: (p: '24h' | '7d') => void;
}

export const PeriodSelector: React.FC<PeriodSelectorProps> = ({ period, onPeriodChange }) => {
  return (
    <div className="flex bg-surface-2 border border-border rounded-lg p-0.5 select-none">
      <button
        onClick={() => onPeriodChange('24h')}
        className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded-md transition-colors cursor-pointer ${
          period === '24h' ? 'bg-accent text-white' : 'text-text-3 hover:text-text-2'
        }`}
      >
        24h
      </button>
      <button
        onClick={() => onPeriodChange('7d')}
        className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded-md transition-colors cursor-pointer ${
          period === '7d' ? 'bg-accent text-white' : 'text-text-3 hover:text-text-2'
        }`}
      >
        7j
      </button>
    </div>
  );
};
