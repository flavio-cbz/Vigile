import React from 'react';

export interface ListItem {
  primary: string;
  secondary?: string;
  icon?: React.ReactNode;
  badge?: React.ReactNode;
}

interface ListCardProps {
  title: string;
  items: ListItem[];
  emptyMessage?: string;
}

export const ListCard: React.FC<ListCardProps> = ({
  title,
  items,
  emptyMessage = 'Aucun élément trouvé',
}) => {
  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-text-2">
        {title} ({items.length})
      </h3>
      {items.length === 0 ? (
        <p className="text-xs text-text-3 font-mono py-4 text-center">{emptyMessage}</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {items.map((item, idx) => (
            <div
              key={idx}
              className="flex items-center gap-3 p-2.5 rounded-lg bg-surface-2/60 border border-border-strong/20 text-xs"
            >
              {item.icon && (
                <span className="shrink-0 text-text-3">{item.icon}</span>
              )}
              <div className="flex-1 min-w-0">
                <span className="font-bold text-text-1 truncate block">{item.primary}</span>
                {item.secondary && (
                  <span className="text-[11px] text-text-3 font-mono truncate block mt-0.5">
                    {item.secondary}
                  </span>
                )}
              </div>
              {item.badge && <span className="shrink-0">{item.badge}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
