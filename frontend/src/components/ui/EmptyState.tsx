import React from 'react';

interface EmptyStateProps {
  icon: React.ReactElement;
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
  compact?: boolean;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  className = '',
  compact = false,
}) => {
  return (
    <div className={`card ${compact ? 'py-6 px-4' : 'py-16 px-8'} ${className}`}>
      <div className="flex flex-col items-center justify-center text-center">
        <div className={`text-ink-muted opacity-45 ${compact ? 'mb-2.5' : 'mb-5'}`}>
          {(() => {
            if (!React.isValidElement(icon)) return icon;
            const el = icon as React.ReactElement<{ className?: string }>;
            const existing = (el.props.className ?? '') as string;
            return React.cloneElement(el, {
              className: `${existing} ${compact ? 'w-7 h-7' : 'w-12 h-12'}`,
            });
          })()}
        </div>
        <h3 className={`text-ink-primary font-bold ${compact ? 'text-xs mb-1' : 'text-sm mb-2'}`}>
          {title}
        </h3>
        <p className={`text-ink-secondary leading-relaxed ${compact ? 'text-[10px] max-w-xs' : 'text-xs max-w-md'}`}>
          {description}
        </p>
        {action && (
          <button
            onClick={action.onClick}
            className={`btn btn-secondary ${
              compact ? 'mt-4 px-3 py-1 text-[10px]' : 'mt-6 px-4 py-2 text-xs'
            }`}
          >
            {action.label}
          </button>
        )}
      </div>
    </div>
  );
};
