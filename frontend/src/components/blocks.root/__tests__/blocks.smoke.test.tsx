import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { Tabs } from '../Tabs';
import { ListCard } from '../ListCard';
import { Banner } from '../Banner';
import { MetricCardsGrid } from '../MetricCardsGrid';
import { NodeSelector, NodePills } from '../NodeSelector';
import { FilterPanel } from '../FilterPanel';
import { PageHeader } from '../PageHeader';
import { GroupedRadio, ToggleField } from '../form-fields';

// ── Tabs ──

describe('Tabs', () => {
  const tabs = [
    { id: 'sessions', label: 'Lectures', badge: 3 },
    { id: 'users', label: 'Utilisateurs' },
  ];

  it('renders all tab labels', () => {
    render(<Tabs tabs={tabs} activeTab="sessions" onChange={vi.fn()} />);
    expect(screen.getByText('Lectures')).toBeInTheDocument();
    expect(screen.getByText('Utilisateurs')).toBeInTheDocument();
  });

  it('applies active class to selected tab', () => {
    render(<Tabs tabs={tabs} activeTab="sessions" onChange={vi.fn()} />);
    const activeBtn = screen.getByText('Lectures').closest('button');
    expect(activeBtn).toHaveClass('text-orange-500');
    expect(activeBtn).toHaveClass('border-orange-500');
  });

  it('renders badge count', () => {
    render(<Tabs tabs={tabs} activeTab="sessions" onChange={vi.fn()} />);
    expect(screen.getByText('(3)')).toBeInTheDocument();
  });
});

// ── ListCard ──

describe('ListCard', () => {
  it('renders title and items', () => {
    render(
      <ListCard
        title="Sessions actives"
        items={[
          { primary: 'user@example.com', secondary: '192.168.1.10' },
          { primary: 'admin@example.com' },
        ]}
      />
    );
    expect(screen.getByText('Sessions actives (2)')).toBeInTheDocument();
    expect(screen.getByText('user@example.com')).toBeInTheDocument();
    expect(screen.getByText('192.168.1.10')).toBeInTheDocument();
    expect(screen.getByText('admin@example.com')).toBeInTheDocument();
  });

  it('renders empty message when items is empty', () => {
    render(<ListCard title="Sessions" items={[]} />);
    expect(screen.getByText('Aucun élément trouvé')).toBeInTheDocument();
  });

  it('renders custom empty message', () => {
    render(<ListCard title="Sessions" items={[]} emptyMessage="Rien ici" />);
    expect(screen.getByText('Rien ici')).toBeInTheDocument();
  });
});

// ── Banner ──

describe('Banner', () => {
  it('renders info banner with title', () => {
    render(<Banner variant="info" title="Information" />);
    expect(screen.getByText('Information')).toBeInTheDocument();
  });

  it('renders warning banner with message', () => {
    render(<Banner variant="warning" title="Attention" message="Serveur non détecté" />);
    expect(screen.getByText('Attention')).toBeInTheDocument();
    expect(screen.getByText('Serveur non détecté')).toBeInTheDocument();
  });

  it('renders error banner', () => {
    render(<Banner variant="error" title="Erreur" />);
    expect(screen.getByText('Erreur')).toBeInTheDocument();
  });

  it('renders success banner', () => {
    render(<Banner variant="success" title="Connecté" />);
    expect(screen.getByText('Connecté')).toBeInTheDocument();
  });

  it('renders action button', () => {
    const onClick = vi.fn();
    render(<Banner variant="info" title="Titre" action={{ label: 'Cliquer', onClick }} />);
    const btn = screen.getByText('Cliquer');
    expect(btn).toBeInTheDocument();
    btn.click();
    expect(onClick).toHaveBeenCalled();
  });
});

// ── MetricCardsGrid ──

describe('MetricCardsGrid', () => {
  it('renders metric cards with labels and values', () => {
    render(
      <MetricCardsGrid
        cards={[
          { label: 'Lectures actives', value: 5 },
          { label: 'Transcodes', value: 2, delta: '(1 active)', deltaColor: 'positive' },
          { label: 'Bibliothèques', value: 3 },
          { label: 'Utilisateurs', value: 8 },
        ]}
      />
    );
    expect(screen.getByText('Lectures actives')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('Transcodes')).toBeInTheDocument();
    expect(screen.getByText('(1 active)')).toBeInTheDocument();
    expect(screen.getByText('Bibliothèques')).toBeInTheDocument();
    expect(screen.getByText('Utilisateurs')).toBeInTheDocument();
  });

  it('applies correct delta color class', () => {
    render(
      <MetricCardsGrid
        cards={[{ label: 'Test', value: 10, delta: '+5', deltaColor: 'positive' }]}
      />
    );
    const delta = screen.getByText('+5');
    expect(delta).toHaveClass('text-emerald-400');
  });
});

// ── NodeSelector ──

describe('NodeSelector', () => {
  const nodes = [
    { id: 'n1', name: 'Server 1', online: true },
    { id: 'n2', name: 'Server 2', online: false },
  ];

  it('renders node options in select', () => {
    render(<NodeSelector nodes={nodes} selected="all" onChange={vi.fn()} />);
    expect(screen.getByText('Tous les serveurs')).toBeInTheDocument();
    expect(screen.getByText('Server 1')).toBeInTheDocument();
    expect(screen.getByText('Server 2')).toBeInTheDocument();
  });

  it('renders loading state', () => {
    render(<NodeSelector nodes={[]} selected="all" onChange={vi.fn()} isLoading />);
    expect(screen.getByText(/Chargement/)).toBeInTheDocument();
  });

  it('renders empty state', () => {
    render(<NodeSelector nodes={[]} selected="all" onChange={vi.fn()} />);
    expect(screen.getByText(/Aucun n/)).toBeInTheDocument();
  });
});

// ── NodePills ──

describe('NodePills', () => {
  const nodes = [
    { id: 'n1', name: 'Server 1', online: true },
    { id: 'n2', name: 'Server 2', online: false },
  ];

  it('renders pill buttons', () => {
    render(<NodePills nodes={nodes} selected="n1" onChange={vi.fn()} />);
    expect(screen.getByText('Server 1')).toBeInTheDocument();
    expect(screen.getByText('Server 2')).toBeInTheDocument();
  });

  it('highlights selected node', () => {
    render(<NodePills nodes={nodes} selected="n1" onChange={vi.fn()} />);
    const btn = screen.getByText('Server 1').closest('button');
    expect(btn).toHaveClass('text-orange-400');
  });
});

// ── FilterPanel ──

describe('FilterPanel', () => {
  it('renders search and select fields', () => {
    render(
      <FilterPanel
        fields={[
          { name: 'search', label: 'Rechercher', type: 'search', value: '', onChange: vi.fn() },
          {
            name: 'period',
            label: 'Période',
            type: 'select',
            value: '24h',
            onChange: vi.fn(),
            options: [
              { value: '1h', label: 'Dernière heure' },
              { value: '24h', label: 'Dernières 24 heures' },
            ],
          },
        ]}
      />
    );
    expect(screen.getByPlaceholderText('Rechercher')).toBeInTheDocument();
    const select = screen.getAllByRole('combobox')[0];
    expect(select).toHaveValue('24h');
  });
});

// ── PageHeader ──

describe('PageHeader', () => {
  it('renders title and subtitle', () => {
    render(<PageHeader title="Plex Media Server" subtitle="Supervision du streaming" />);
    expect(screen.getByText('Plex Media Server')).toBeInTheDocument();
    expect(screen.getByText('Supervision du streaming')).toBeInTheDocument();
  });

  it('renders without subtitle', () => {
    render(<PageHeader title="Titre" />);
    expect(screen.getByText('Titre')).toBeInTheDocument();
  });
});

// ── GroupedRadio (additional coverage) ──

describe('GroupedRadio', () => {
  it('renders radio group with aria-label', () => {
    render(
      <GroupedRadio
        name="mode"
        options={[{ value: 'a', label: 'Option A' }, { value: 'b', label: 'Option B' }]}
        value="a"
        onChange={vi.fn()}
      />
    );
    expect(screen.getByRole('radiogroup')).toHaveAttribute('aria-label', 'mode');
  });
});

// ── ToggleField (additional coverage) ──

describe('ToggleField', () => {
  it('renders switch with aria role', () => {
    render(<ToggleField name="x" label="Toggle" checked={false} onChange={vi.fn()} />);
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
  });

  it('renders switch checked state', () => {
    render(<ToggleField name="x" label="Toggle" checked={true} onChange={vi.fn()} />);
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
  });
});
