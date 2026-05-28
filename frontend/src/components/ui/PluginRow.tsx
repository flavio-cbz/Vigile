import React, { useRef, useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { ErrorBoundary } from './ErrorBoundary';

export interface PluginRowProps {
  title: string;
  subtitle?: string;
  onSeeAll?: () => void;
  isEmpty?: boolean;
  emptyState?: React.ReactNode;
  children: React.ReactNode;
}

export const PluginRow: React.FC<PluginRowProps> = ({
  title,
  subtitle,
  onSeeAll,
  isEmpty = false,
  emptyState,
  children,
}) => {
  const rowRef = useRef<HTMLDivElement>(null);
  const [showLeftArrow, setShowLeftArrow] = useState(false);
  const [showRightArrow, setShowRightArrow] = useState(false);

  // Check scroll position to dynamically show/hide navigation chevrons
  const checkScroll = () => {
    if (rowRef.current) {
      const { scrollLeft, scrollWidth, clientWidth } = rowRef.current;
      setShowLeftArrow(scrollLeft > 5);
      setShowRightArrow(scrollWidth > clientWidth && scrollLeft + clientWidth < scrollWidth - 5);
    }
  };

  useEffect(() => {
    const el = rowRef.current;
    if (el) {
      checkScroll();
      // Use ResizeObserver for accurate sizing updates
      const resizeObserver = new ResizeObserver(() => checkScroll());
      resizeObserver.observe(el);
      el.addEventListener('scroll', checkScroll);

      return () => {
        resizeObserver.disconnect();
        el.removeEventListener('scroll', checkScroll);
      };
    }
  }, [children, isEmpty]);

  const handleScroll = (direction: 'left' | 'right') => {
    if (rowRef.current) {
      const offset = direction === 'left' ? -400 : 400;
      rowRef.current.scrollBy({ left: offset, behavior: 'smooth' });
    }
  };

  return (
    <div className="relative group/row space-y-2 py-2">
      {/* Row header with title and action */}
      <div className="flex items-baseline justify-between px-1">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-ink flex items-center gap-2">
            {title}
          </h2>
          {subtitle && (
            <p className="text-[0.625rem] text-ink-muted mt-0.5">{subtitle}</p>
          )}
        </div>
        {onSeeAll && !isEmpty && (
          <button
            onClick={onSeeAll}
            className="px-2.5 py-0.5 rounded-md border border-accent-border bg-accent-soft text-accent-custom hover:bg-accent-custom hover:text-bg text-[0.625rem] font-extrabold transition-all duration-150 cursor-pointer shadow-xs select-none"
          >
            Voir tout
          </button>
        )}
      </div>

      <div className="relative">
        {/* Left Scroll Button */}
        {showLeftArrow && !isEmpty && (
          <button
            onClick={() => handleScroll('left')}
            className="absolute left-0 top-1/2 -translate-y-1/2 -ml-3 z-30 w-8 h-8 rounded-full border border-border-strong bg-surface/90 backdrop-blur-md flex items-center justify-center text-ink-muted hover:text-ink hover:border-accent-border opacity-0 group-hover/row:opacity-100 transition-all duration-200 cursor-pointer shadow-lg"
            aria-label="Faire défiler vers la gauche"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        )}

        {/* Scrollable container with ErrorBoundary */}
        <div className="relative overflow-hidden rounded-xl">
          <div
            ref={rowRef}
            className="flex gap-4 overflow-x-auto scrollbar-none scroll-smooth pb-3 pt-1 px-1"
            style={{ scrollSnapType: 'x mandatory' }}
          >
            <ErrorBoundary>
              {isEmpty ? (
                <div className="w-full shrink-0">
                  {emptyState}
                </div>
              ) : (
                children
              )}
            </ErrorBoundary>
          </div>
          
          {/* Horizontal fade effect on the right */}
          {showRightArrow && !isEmpty && (
            <div className="absolute right-0 top-0 bottom-3 w-16 bg-gradient-to-l from-[#050505] to-transparent pointer-events-none z-10" />
          )}
        </div>

        {/* Right Scroll Button */}
        {showRightArrow && !isEmpty && (
          <button
            onClick={() => handleScroll('right')}
            className="absolute right-0 top-1/2 -translate-y-1/2 -mr-3 z-30 w-8 h-8 rounded-full border border-border-strong bg-surface/90 backdrop-blur-md flex items-center justify-center text-ink-muted hover:text-ink hover:border-accent-border opacity-0 group-hover/row:opacity-100 transition-all duration-200 cursor-pointer shadow-lg"
            aria-label="Faire défiler vers la droite"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
};
