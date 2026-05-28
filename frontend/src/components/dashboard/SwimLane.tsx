import React, { useRef, useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface SwimLaneProps {
  title: string;
  icon: LucideIcon;
  onSeeAll?: () => void;
  seeAllLabel?: string;
  children: React.ReactNode;
  isLoading?: boolean;
  skeletonCount?: number;
  skeletonComponent?: React.ReactNode;
}

export const SwimLane: React.FC<SwimLaneProps> = ({
  title,
  icon: Icon,
  onSeeAll,
  seeAllLabel = "Voir tout",
  children,
  isLoading = false,
  skeletonCount = 4,
  skeletonComponent,
}) => {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const checkScroll = () => {
    const el = scrollContainerRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 10);
    setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 10);
  };

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    checkScroll();

    el.addEventListener('scroll', checkScroll);
    window.addEventListener('resize', checkScroll);

    return () => {
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
    <div className="space-y-3 relative w-full select-none animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          <Icon className="text-accent-primary w-4.5 h-4.5" />
          <h3 className="text-sm font-bold text-ink-primary tracking-wide uppercase">
            {title}
          </h3>
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

      {/* Carousel Wrapper */}
      <div className="relative group">
        {/* Left Navigation Arrow */}
        {canScrollLeft && (
          <button
            onClick={() => handleScroll('left')}
            className="absolute left-2 top-1/2 -translate-y-1/2 z-20 w-8 h-8 rounded-full bg-surface-1/90 border border-border hover:bg-surface-2 hover:border-border-hover text-ink-primary flex items-center justify-center shadow-lg transition-all duration-200"
            aria-label="Scroll left"
          >
            <ChevronLeft size={18} />
          </button>
        )}

        {/* Scrollable Container with Fade Mask */}
        <div
          ref={scrollContainerRef}
          className="flex gap-4 overflow-x-auto scroll-smooth scrollbar-none snap-x snap-mandatory py-1 px-1 relative"
          style={{
            maskImage: 'linear-gradient(to right, transparent, black 4%, black 96%, transparent)',
            WebkitMaskImage: 'linear-gradient(to right, transparent, black 4%, black 96%, transparent)',
          }}
        >
          {isLoading ? (
            <>
              {Array.from({ length: skeletonCount }).map((_, i) => (
                <div key={i} className="snap-start shrink-0">
                  {skeletonComponent}
                </div>
              ))}
            </>
          ) : (
            React.Children.map(children, (child) => {
              if (!child) return null;
              return <div className="snap-start shrink-0">{child}</div>;
            })
          )}
        </div>

        {/* Right Navigation Arrow */}
        {canScrollRight && (
          <button
            onClick={() => handleScroll('right')}
            className="absolute right-2 top-1/2 -translate-y-1/2 z-20 w-8 h-8 rounded-full bg-surface-1/90 border border-border hover:bg-surface-2 hover:border-border-hover text-ink-primary flex items-center justify-center shadow-lg transition-all duration-200"
            aria-label="Scroll right"
          >
            <ChevronRight size={18} />
          </button>
        )}
      </div>
    </div>
  );
};
