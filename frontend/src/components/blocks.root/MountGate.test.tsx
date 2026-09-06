import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MountGate } from './MountGate';

describe('MountGate', () => {
  it('revision null : passage direct, onReset jamais appelé', () => {
    const onReset = vi.fn();
    const onRefresh = vi.fn();
    render(
      <MountGate
        revision={null}
        mountedRevision={{ boot_id: 'A', counter: 1 }}
        onReset={onReset}
        onRefresh={onRefresh}
      >
        <div>contenu</div>
      </MountGate>
    );
    expect(screen.getByText('contenu')).toBeInTheDocument();
    expect(screen.queryByTestId('mount-gate-reloading')).not.toBeInTheDocument();
    expect(onReset).not.toHaveBeenCalled();
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('premier montage : mountedRevision null → enfants rendus, aucun reset', () => {
    const onReset = vi.fn();
    render(
      <MountGate revision={{ boot_id: 'A', counter: 1 }} mountedRevision={null} onReset={onReset}>
        <div>contenu</div>
      </MountGate>
    );
    expect(screen.getByText('contenu')).toBeInTheDocument();
    expect(onReset).not.toHaveBeenCalled();
  });

  it('mismatch de boot_id : load barrier + onReset appelé une seule fois', () => {
    const onReset = vi.fn();
    const props = {
      revision: { boot_id: 'B', counter: 1 },
      mountedRevision: { boot_id: 'A', counter: 1 },
      onReset,
    };
    const { rerender } = render(
      <MountGate {...props}>
        <div>contenu</div>
      </MountGate>
    );
    expect(screen.queryByText('contenu')).not.toBeInTheDocument();
    expect(screen.getByTestId('mount-gate-reloading')).toBeInTheDocument();
    expect(onReset).toHaveBeenCalledTimes(1);

    // Mêmes props re-rendues : l'effet ne se re-déclenche pas (une fois).
    rerender(
      <MountGate {...props}>
        <div>contenu</div>
      </MountGate>
    );
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it('changement de counter seul : enfants maintenus montés + onRefresh', () => {
    const onRefresh = vi.fn();
    render(
      <MountGate
        revision={{ boot_id: 'A', counter: 2 }}
        mountedRevision={{ boot_id: 'A', counter: 1 }}
        onRefresh={onRefresh}
      >
        <div>contenu</div>
      </MountGate>
    );
    expect(screen.getByText('contenu')).toBeInTheDocument();
    expect(screen.queryByTestId('mount-gate-reloading')).not.toBeInTheDocument();
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('les enfants se mettent à jour quand les props changent (cas counter)', () => {
    const onRefresh = vi.fn();
    const { rerender } = render(
      <MountGate
        revision={{ boot_id: 'A', counter: 1 }}
        mountedRevision={{ boot_id: 'A', counter: 1 }}
        onRefresh={onRefresh}
      >
        <div>version 1</div>
      </MountGate>
    );
    expect(screen.getByText('version 1')).toBeInTheDocument();
    expect(onRefresh).not.toHaveBeenCalled();

    // Counter passe à 2 : les enfants restent montés et se mettent à jour.
    rerender(
      <MountGate
        revision={{ boot_id: 'A', counter: 2 }}
        mountedRevision={{ boot_id: 'A', counter: 1 }}
        onRefresh={onRefresh}
      >
        <div>version 2</div>
      </MountGate>
    );
    expect(screen.getByText('version 2')).toBeInTheDocument();
    expect(screen.queryByText('version 1')).not.toBeInTheDocument();
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});
