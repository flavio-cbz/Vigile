import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusPill } from '../StatusPill';

describe('StatusPill', () => {
  it('renders the status text', () => {
    render(<StatusPill status="running" />);
    expect(screen.getByText('running')).toBeInTheDocument();
  });

  it('applies active (green) classes for "running"', () => {
    render(<StatusPill status="running" />);
    const pill = screen.getByText('running').closest('span');
    expect(pill).toHaveClass('bg-green-custom/10', 'text-green-custom');
  });

  it('applies active (green) classes for "active"', () => {
    render(<StatusPill status="active" />);
    const pill = screen.getByText('active').closest('span');
    expect(pill).toHaveClass('bg-green-custom/10', 'text-green-custom');
  });

  it('applies inactive (zinc) classes for "exited"', () => {
    render(<StatusPill status="exited" />);
    const pill = screen.getByText('exited').closest('span');
    expect(pill).toHaveClass('bg-zinc-800', 'text-zinc-400');
  });

  it('applies inactive (zinc) classes for "inactive"', () => {
    render(<StatusPill status="inactive" />);
    const pill = screen.getByText('inactive').closest('span');
    expect(pill).toHaveClass('bg-zinc-800', 'text-zinc-400');
  });

  it('applies inactive (zinc) classes for "failed"', () => {
    render(<StatusPill status="failed" />);
    const pill = screen.getByText('failed').closest('span');
    expect(pill).toHaveClass('bg-zinc-800', 'text-zinc-400');
  });

  it('renders green dot for active status', () => {
    const { container } = render(<StatusPill status="running" />);
    const dots = container.querySelectorAll('.rounded-full');
    const dot = dots[dots.length - 1];
    expect(dot).toHaveClass('bg-green-custom', 'animate-pulse');
  });

  it('renders zinc dot for inactive status', () => {
    const { container } = render(<StatusPill status="stopped" />);
    const dots = container.querySelectorAll('.rounded-full');
    const dot = dots[dots.length - 1];
    expect(dot).toHaveClass('bg-zinc-500');
  });

  it('respects custom activeStates override', () => {
    render(<StatusPill status="degraded" activeStates={['degraded']} />);
    const pill = screen.getByText('degraded').closest('span');
    expect(pill).toHaveClass('bg-green-custom/10', 'text-green-custom');
  });

  it('treats unknown status as inactive', () => {
    render(<StatusPill status="unknown-xyz" />);
    const pill = screen.getByText('unknown-xyz').closest('span');
    expect(pill).toHaveClass('bg-zinc-800', 'text-zinc-400');
  });
});
