import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { KillSwitchBadge } from './KillSwitchBadge';
import type { PluginKillSwitch } from '../../hooks/usePluginsData';

const mockT = (key: string) => key;

describe('KillSwitchBadge', () => {
  it('renders nothing when killSwitch is null', () => {
    const { container } = render(<KillSwitchBadge killSwitch={null} t={mockT} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when killSwitch is undefined', () => {
    const { container } = render(<KillSwitchBadge killSwitch={undefined} t={mockT} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders maintenance badge when hard=false', () => {
    const ks: PluginKillSwitch = { hard: false, reason: 'maintenance' };
    render(<KillSwitchBadge killSwitch={ks} t={mockT} />);
    expect(screen.getByText('plugins.kill_switch.maintenance')).toBeInTheDocument();
  });

  it('renders hard badge when hard=true', () => {
    const ks: PluginKillSwitch = { hard: true, reason: 'security breach' };
    render(<KillSwitchBadge killSwitch={ks} t={mockT} />);
    expect(screen.getByText('plugins.kill_switch.hard')).toBeInTheDocument();
  });
});
