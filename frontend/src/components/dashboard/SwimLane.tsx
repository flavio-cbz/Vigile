import React, { useRef, useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
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
  seeAllLabel = "Voir tout",
  children,
  isLoading = false,
  skeletonCount = 4,
  skeletonComponent,
  className = '',
  layout = 'carousel',
  gridClassName = '',
}) => {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const checkScroll = () => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const hasOverflow = el.scrollWidth > el.clientWidth;
    setCanScrollLeft(hasOverflow && el.scrollLeft > 25);
    setCanScrollRight(hasOverflow && el.scrollLeft < el.scrollWidth - el.clientWidth - 25);
  };

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    checkScroll();

    const resizeObserver = new ResizeObserver(() => {
      checkScroll();
    });
    resizeObserver.observe(el);

    const mutationObserver = new MutationObserver(() => {
      checkScroll();
    });
    mutationObserver.observe(el, { childList: true, subtree: true });

    el.addEventListener('scroll', checkScroll);
    window.addEventListener('resize', checkScroll);

    return () => {
      resizeObserver.disconnect();
      mutationObserver.disconnect();
      el.removeEventListener('scroll', checkScroll);
      window.removeEventListener('resize', checkScroll);
    };
  }, [children, isLoading]);

  const handleScroll = (direction: 'left' | 'right') => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const amount = el.clientWidth * 0.75;
    el.scrollBy({
      left: direction === 'left' ? -amount : amount,
      behavior: 'smooth',
    });
  };

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
            {seeAllLabel} →
          </button>
        )}
      </div>

      {layout === 'grid' ? (
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
      ) : (
        <div className="relative">
          {canScrollLeft && (
            <button
              onClick={() => handleScroll('left')}
              className="hidden md:flex absolute left-2 top-1/2 -translate-y-1/2 z-20 w-8 h-8 rounded-full bg-surface-1/90 backdrop-blur-sm border border-border hover:bg-surface-2 hover:border-border-hover text-ink-primary items-center justify-center shadow-lg transition-all duration-200"
              aria-label="Scroll left"
            >
              <ChevronLeft size={18} />
            </button>
          )}

          <div
            ref={scrollContainerRef}
            className="flex gap-4 overflow-x-auto scroll-smooth scrollbar-none snap-x snap-mandatory pt-2 pb-4 scroll-px-4 md:scroll-px-12 relative w-full"
          >
            <div className="shrink-0 w-4 md:w-12" />

            {isLoading ? (
              <>
                {Array.from({ length: skeletonCount }).map((_, i) => (
                  <div key={i} className="snap-start shrink-0">
                    {skeletonComponent}
                  </div>
                ))}
              </>
            ) : (
              React.Children.map(children, (child) => (
                <div className="snap-start shrink-0">{child}</div>
              ))
            )}

            <div className="shrink-0 w-4 md:w-12" />
          </div>

          {canScrollRight && (
            <button
              onClick={() => handleScroll('right')}
              className="hidden md:flex absolute right-2 top-1/2 -translate-y-1/2 z-20 w-8 h-8 rounded-full bg-surface-1/90 backdrop-blur-sm border border-border hover:bg-surface-2 hover:border-border-hover text-ink-primary items-center justify-center shadow-lg transition-all duration-200"
              aria-label="Scroll right"
            >
              <ChevronRight size={18} />
            </button>
          )}
        </div>
      )}
    </div>
  );
};
