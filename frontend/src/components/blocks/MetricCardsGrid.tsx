import React from 'react';

export interface MetricCardData {
  label: string;
  value: string | number;
  delta?: string;
  deltaColor?: 'positive' | 'negative' | 'neutral';
  icon?: React.ReactNode;
}

interface MetricCardsGridProps {
  cards: MetricCardData[];
}

export const MetricCardsGrid: React.FC<MetricCardsGridProps> = ({ cards }) => {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card, idx) => (
        <div
          key={idx}
          className="p-4 rounded-xl border border-border-strong/20 bg-surface-2/40 flex flex-col gap-1.5"
        >
          <div className="flex items-center justify-between text-xs text-text-3 font-mono uppercase font-bold">
            <span>{card.label}</span>
            {card.icon}
          </div>
          <div className="text-2xl font-bold text-text-1 font-mono flex items-center gap-2">
            {card.value}
            {card.delta && (
              <span
                className={`text-xs font-normal font-mono ${
                  card.deltaColor === 'positive'
                    ? 'text-emerald-400'
                    : card.deltaColor === 'negative'
                    ? 'text-red-400'
                    : 'text-amber-400'
                }`}
              >
                {card.delta}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};
