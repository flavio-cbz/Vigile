import React, { useEffect, useId, useRef, useState } from 'react';

export interface HelpTooltipThresholds {
  warning: number;
  critical: number;
  resolve: number;
  unit: string;
}

export interface HelpTooltipProps {
  title: string;
  description: string;
  thresholds: HelpTooltipThresholds;
  consequence: string;
}

/**
 * HelpTooltip — catalogue primitive (help-tooltip).
 *
 * Trigger "?" button opens a contextual popover explaining what the gauge
 * measures, the real alert thresholds (from BUILTIN_THRESHOLDS) and their
 * consequences. Accessibility: focusable trigger, aria-describedby, click
 * outside + Escape to close, keyboard operable (Enter/Space), role=tooltip.
 */
export const HelpTooltip: React.FC<HelpTooltipProps> = ({
  title,
  description,
  thresholds,
  consequence,
}) => {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const tooltipId = useId();
  const panelId = `${tooltipId}-panel`;

  const toggle = () => setOpen((v) => !v);
  const close = () => setOpen(false);

  // Close on click/tap outside + focusout
  useEffect(() => {
    if (!open) return;
    const onDown = (e: Event) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        close();
      }
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('touchstart', onDown, { passive: true } as AddEventListenerOptions);
    const el = containerRef.current;
    const onFocusOut = (e: FocusEvent) => {
      if (el && !el.contains(e.relatedTarget as Node | null)) {
        setTimeout(() => {
          if (el && !el.contains(document.activeElement)) {
            close();
          }
        }, 0);
      }
    };
    el?.addEventListener('focusout', onFocusOut);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('touchstart', onDown);
      el?.removeEventListener('focusout', onFocusOut as EventListener);
    };
  }, [open]);

  // Close on Escape (also restore focus to trigger)
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        close();
        buttonRef.current?.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  const onTriggerKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      e.stopPropagation();
      toggle();
    }
    if (e.key === 'Escape') {
      e.stopPropagation();
      close();
      buttonRef.current?.focus();
    }
  };

  return (
    <div ref={containerRef} className="relative inline-flex">
      <button
        ref={buttonRef}
        type="button"
        aria-label={`Aide — ${title}`}
        aria-expanded={open}
        aria-describedby={open ? panelId : undefined}
        aria-haspopup="dialog"
        onClick={(e) => {
          e.stopPropagation();
          toggle();
        }}
        onKeyDown={onTriggerKeyDown}
        className="inline-flex items-center justify-center min-w-8 min-h-8 w-8 h-8 rounded-full bg-transparent border border-transparent text-text-3 hover:text-text-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-0 touch-manipulation cursor-pointer"
        style={{ WebkitTapHighlightColor: 'transparent' }}
      >
        <span className="inline-flex items-center justify-center w-4 h-4 rounded-full border border-border bg-surface-2 text-[10px] font-mono font-bold leading-none group-hover:border-border-strong/50 transition-colors">?</span>
      </button>

      {open && (
        <div
          id={panelId}
          role="dialog"
          aria-label={`Aide — ${title}`}
          onClick={(e) => e.stopPropagation()}
          className="absolute z-30 left-1/2 -translate-x-1/2 top-[calc(100%+8px)] w-[300px] sm:w-[340px] max-w-[calc(100vw-32px)] rounded-xl border border-border bg-surface shadow-xl shadow-black/20 p-3.5 text-left animate-fade-in sm:left-1/2 sm:-translate-x-1/2"
        >
          {/* Arrow */}
          <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-surface border-l border-t border-border rotate-45" aria-hidden="true" />
          <div className="space-y-2.5">
            <h4 className="font-interface font-extrabold text-xs uppercase tracking-wider text-text-1">{title}</h4>
            <p className="text-xs leading-relaxed text-text-2">{description}</p>

            <div className="rounded-lg border border-border/60 bg-surface-2/60 p-2.5 space-y-1.5">
              <div className="flex items-center justify-between text-[11px] font-mono">
                <span className="text-text-3 font-semibold uppercase tracking-wider">Warning</span>
                <span className="font-bold text-amber-500">&gt; {thresholds.warning}{thresholds.unit}</span>
              </div>
              <div className="flex items-center justify-between text-[11px] font-mono">
                <span className="text-text-3 font-semibold uppercase tracking-wider">Critical</span>
                <span className="font-bold text-red-500">&gt; {thresholds.critical}{thresholds.unit}</span>
              </div>
              <div className="flex items-center justify-between text-[11px] font-mono">
                <span className="text-text-3 font-semibold uppercase tracking-wider">Résolu</span>
                <span className="font-bold text-emerald-500">≤ {thresholds.resolve}{thresholds.unit}</span>
              </div>
            </div>

            <p className="text-[11px] leading-relaxed text-text-3 italic border-l-2 border-accent/30 pl-2.5">
              {consequence}
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

export default HelpTooltip;
