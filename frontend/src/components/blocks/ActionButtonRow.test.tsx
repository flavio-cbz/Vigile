import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ActionButtonRow } from './ActionButtonRow';
import { DEFAULT_HOVER_TOKENS, SPINNER_TOKEN } from './types';
import type { BlockAction } from './types';

const ACTIONS: BlockAction[] = [
  { label: 'Arrêter', command: 'stop', variant: 'danger' },
  { label: 'Démarrer', command: 'start', variant: 'success' },
  { label: 'Redémarrer', command: 'restart', variant: 'warning' },
];

describe('ActionButtonRow', () => {
  // ── T10-1: Buttons render from config ──
  it('renders one button per config action with correct labels', () => {
    render(
      <ActionButtonRow
        actions={ACTIONS}
        busyCommands={new Set()}
        onAction={vi.fn()}
      />
    );

    expect(screen.getByRole('button', { name: 'Arrêter' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Démarrer' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Redémarrer' })).toBeInTheDocument();
  });

  // ── T10-2: Per-button busy replaces label with spinner ──
  it('replaces busy button label with spinner and disables it', () => {
    render(
      <ActionButtonRow
        actions={ACTIONS}
        busyCommands={new Set(['stop'])}
        onAction={vi.fn()}
      />
    );

    const stopBtn = screen.getByRole('button', { name: /Arrêter/ });
    // Busy button gets an aria-label with "(en cours…)"
    expect(stopBtn).toHaveAttribute('aria-label', 'Arrêter (en cours…)');
    expect(stopBtn).toBeDisabled();

    // Spinner is present inside the busy button
    const spinner = stopBtn.querySelector(`.${SPINNER_TOKEN.replace(/ /g, '.')}`);
    expect(spinner).toBeInTheDocument();

    // Non-busy buttons remain enabled
    expect(screen.getByRole('button', { name: 'Démarrer' })).toBeEnabled();
  });

  // ── T10-3: Hover token classes come from config with defaults ──
  it('applies default hover tokens based on variant', () => {
    const { container } = render(
      <ActionButtonRow
        actions={ACTIONS}
        busyCommands={new Set()}
        onAction={vi.fn()}
      />
    );

    const buttons = container.querySelectorAll('button');
    expect(buttons).toHaveLength(3);

    // danger → zinc-800
    expect(buttons[0].className).toContain(DEFAULT_HOVER_TOKENS.danger.replace('hover:', ''));
    // success → green-custom/10
    expect(buttons[1].className).toContain(DEFAULT_HOVER_TOKENS.success.replace('hover:', ''));
    // warning → orange-500/10
    expect(buttons[2].className).toContain(DEFAULT_HOVER_TOKENS.warning.replace('hover:', ''));
  });

  // ── T10-4: Hover tokens configurable via props ──
  it('applies custom hover tokens when provided via hoverTokens prop', () => {
    const customTokens = {
      danger: 'hover:bg-red-900',
      success: 'hover:bg-emerald-500/20',
      warning: 'hover:bg-amber-500/15',
    };

    const { container } = render(
      <ActionButtonRow
        actions={ACTIONS}
        busyCommands={new Set()}
        hoverTokens={customTokens}
        onAction={vi.fn()}
      />
    );

    const buttons = container.querySelectorAll('button');
    expect(buttons[0].className).toContain('bg-red-900');
    expect(buttons[1].className).toContain('bg-emerald-500/20');
    expect(buttons[2].className).toContain('bg-amber-500/15');
  });

  // ── T10-5: All buttons disabled when global busy ──
  it('disables all buttons when allCommandsBusy is true', () => {
    render(
      <ActionButtonRow
        actions={ACTIONS}
        busyCommands={new Set()}
        allCommandsBusy
        onAction={vi.fn()}
      />
    );

    expect(screen.getByRole('button', { name: /Arrêter/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Démarrer/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Redémarrer/ })).toBeDisabled();
  });

  // ── T10-6: Click dispatches onAction with command ──
  it('calls onAction with the command string when a button is clicked', () => {
    const onAction = vi.fn();
    render(
      <ActionButtonRow
        actions={ACTIONS}
        busyCommands={new Set()}
        onAction={onAction}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Démarrer' }));
    expect(onAction).toHaveBeenCalledWith('start');

    fireEvent.click(screen.getByRole('button', { name: 'Arrêter' }));
    expect(onAction).toHaveBeenCalledWith('stop');
  });

  // ── T10-7: Empty actions renders nothing ──
  it('renders nothing when actions array is empty', () => {
    const { container } = render(
      <ActionButtonRow
        actions={[]}
        busyCommands={new Set()}
        onAction={vi.fn()}
      />
    );

    expect(container.querySelectorAll('button')).toHaveLength(0);
  });
});
