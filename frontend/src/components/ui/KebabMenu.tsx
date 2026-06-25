import { useEffect, useRef, useState } from 'react';
import { useLocale } from '../../i18n';
import { MoreVertical } from 'lucide-react';

export interface KebabMenuItem {
  label: string;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
  hidden?: boolean;
}

interface KebabMenuProps {
  items: KebabMenuItem[];
}

export const KebabMenu = ({ items }: KebabMenuProps) => {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  const visibleItems = items.filter((i) => !i.hidden);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        aria-label={t("ui.more_actions_aria")}
        className="p-1 rounded-md text-text-3 hover:text-text-1 hover:bg-surface-1 transition-colors cursor-pointer"
      >
        <MoreVertical className="w-4 h-4" />
      </button>

      {open && visibleItems.length > 0 && (
        <div
          className="absolute right-0 top-6 z-10 bg-surface-0 border border-border rounded-lg shadow-xl min-w-[160px] py-1"
          onClick={(e) => e.stopPropagation()}
        >
          {visibleItems.map((item, idx) => (
            <button
              key={`${item.label}-${idx}`}
              type="button"
              disabled={item.disabled}
              onClick={() => {
                if (item.disabled) return;
                setOpen(false);
                item.onClick();
              }}
              className={
                item.danger
                  ? 'w-full text-left px-3 py-1.5 text-xs text-red-500 hover:bg-surface-1 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed'
                  : 'w-full text-left px-3 py-1.5 text-xs text-text-1 hover:bg-surface-1 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed'
              }
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
