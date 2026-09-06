import React, { useMemo } from 'react';
import clsx from 'clsx';
import type { BlockAction, HoverTokenMap } from './types';
import { DEFAULT_HOVER_TOKENS, SPINNER_TOKEN } from './types';

export interface ActionButtonRowProps {
  /** Action definitions from block config. */
  actions: BlockAction[];
  /** Set of command strings currently in busy state (per-button busy). */
  busyCommands: Set<string>;
  /** Callback fired with the command string when a button is clicked. */
  onAction: (command: string) => void;
  /** Optional hover token overrides keyed by variant. Merged with defaults. */
  hoverTokens?: HoverTokenMap;
  /** When true, all buttons are disabled regardless of per-button busy state. */
  allCommandsBusy?: boolean;
}

/**
 * ActionButtonRow — configurable row of action buttons for the declarative
 * block catalog V2.
 *
 * Per contract §4.3, hover tokens flow from block config and are NEVER
 * hardcoded inside the component body. The three built-in defaults
 * (zinc-800 / green-custom/10 / orange-500/10) are provided by
 * DEFAULT_HOVER_TOKENS and merged with any caller overrides.
 *
 * Per contract §2.3, the busy-state spinner uses the exact token:
 * `border-t-2 border-orange-500`
 */
export const ActionButtonRow: React.FC<ActionButtonRowProps> = ({
  actions,
  busyCommands,
  onAction,
  hoverTokens: hoverTokenOverrides,
  allCommandsBusy = false,
}) => {
  // Merge caller overrides onto built-in defaults once per render.
  const mergedTokens: HoverTokenMap = useMemo(
    () => ({ ...DEFAULT_HOVER_TOKENS, ...hoverTokenOverrides }),
    [hoverTokenOverrides],
  );

  if (actions.length === 0) return null;

  return (
    <div className="flex justify-end gap-2">
      {actions.map((action) => {
        const isBusy = allCommandsBusy || busyCommands.has(action.command);
        const hoverClass = mergedTokens[action.variant] ?? '';

        return (
          <button
            key={action.command}
            type="button"
            disabled={isBusy}
            aria-label={isBusy ? `${action.label} (en cours…)` : action.label}
            title={action.label}
            onClick={() => onAction(action.command)}
            className={clsx(
              // Base styles matching DockerContainers.tsx action button pattern
              'p-1.5 rounded transition-colors border border-transparent cursor-pointer',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              // Hover token sourced from config (contract §4.3)
              hoverClass,
              // Text color derived from variant
              action.variant === 'success' && 'text-green-custom hover:text-green-custom',
              action.variant === 'danger' && 'text-zinc-400 hover:text-zinc-200',
              action.variant === 'warning' && 'text-orange-500 hover:text-orange-400',
              // Hover border color
              action.variant === 'success' && 'hover:border-green-custom/20',
              action.variant === 'danger' && 'hover:border-zinc-700/50',
              action.variant === 'warning' && 'hover:border-orange-500/20',
            )}
          >
            {isBusy ? (
              <span
                className={clsx(
                  'block w-4 h-4 rounded-full animate-spin',
                  SPINNER_TOKEN,
                  'border-zinc-800',
                )}
                aria-hidden="true"
              />
            ) : (
              <span className="block w-4 h-4" aria-hidden="true">
                {(action.icon === 'trash' || action.command === 'delete') ? (
                  <TrashIcon />
                ) : action.icon === 'play' || action.variant === 'success' ? (
                  <PlayIcon />
                ) : action.icon === 'rotate' || action.variant === 'warning' ? (
                  <RotateIcon />
                ) : (
                  <SquareIcon />
                )}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
};

// ── Inline SVG icons (match lucide-react w-4 h-4 paths) ──

function SquareIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect width="18" height="18" x="3" y="3" rx="2" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polygon points="6 3 20 12 6 21 6 3" />
    </svg>
  );
}

function RotateIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
      <path d="M21 3v5h-5" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M3 6h18" />
      <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
      <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
    </svg>
  );
}

export default ActionButtonRow;
