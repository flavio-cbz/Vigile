import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DataTable } from '../DataTable';
import type { ColumnConfig } from '../types';

const columns: ColumnConfig[] = [
  { key: 'name', label: 'Nom' },
  { key: 'state', label: 'État' },
  { key: 'image', label: 'Image', align: 'right' },
];

const rows: Record<string, unknown>[] = [
  { id: '1', name: 'nginx', state: 'running', image: 'nginx:latest' },
  { id: '2', name: 'redis', state: 'stopped', image: 'redis:7' },
];

describe('DataTable', () => {
  describe('data variant', () => {
    it('renders column headers', () => {
      render(<DataTable columns={columns} data={rows} state="data" />);
      expect(screen.getByText('Nom')).toBeInTheDocument();
      expect(screen.getByText('État')).toBeInTheDocument();
      expect(screen.getByText('Image')).toBeInTheDocument();
    });

    it('renders row data for each column', () => {
      render(<DataTable columns={columns} data={rows} state="data" />);
      expect(screen.getByText('nginx')).toBeInTheDocument();
      expect(screen.getByText('running')).toBeInTheDocument();
      expect(screen.getByText('nginx:latest')).toBeInTheDocument();
      expect(screen.getByText('redis')).toBeInTheDocument();
      expect(screen.getByText('stopped')).toBeInTheDocument();
      expect(screen.getByText('redis:7')).toBeInTheDocument();
    });

    it('renders correct number of rows', () => {
      const { container } = render(<DataTable columns={columns} data={rows} state="data" />);
      const tbodyRows = container.querySelectorAll('tbody tr');
      expect(tbodyRows).toHaveLength(2);
    });

    it('renders actions column when actions provided', () => {
      render(
        <DataTable
          columns={columns}
          data={rows}
          state="data"
          actions={(row) => <button>Delete {String(row.name)}</button>}
        />
      );
      expect(screen.getByText('Delete nginx')).toBeInTheDocument();
      expect(screen.getByText('Delete redis')).toBeInTheDocument();
    });

    it('applies align class for right-aligned column', () => {
      const { container } = render(<DataTable columns={columns} data={rows} state="data" />);
      const headers = container.querySelectorAll('th');
      expect(headers[2]).toHaveClass('text-right');
    });

    it('uses custom render function when provided', () => {
      const renderColumns: ColumnConfig[] = [
        { key: 'name', label: 'Nom' },
        { key: 'state', label: 'Pill', render: (row) => <strong>{String(row.state)}!</strong> },
      ];
      render(<DataTable columns={renderColumns} data={rows} state="data" />);
      expect(screen.getByText('running!')).toBeInTheDocument();
      expect(screen.getByText('stopped!')).toBeInTheDocument();
    });
  });

  describe('empty variant', () => {
    it('shows default empty message in French', () => {
      render(<DataTable columns={columns} data={[]} state="empty" />);
      expect(screen.getByText('Aucun conteneur trouvé')).toBeInTheDocument();
    });

    it('shows custom empty message from config', () => {
      render(
        <DataTable
          columns={columns}
          data={[]}
          state="empty"
          emptyMessage="Aucun service trouvé"
        />
      );
      expect(screen.getByText('Aucun service trouvé')).toBeInTheDocument();
    });

    it('renders AlertCircle icon in empty state', () => {
      const { container } = render(<DataTable columns={columns} data={[]} state="empty" />);
      const svg = container.querySelector('svg');
      expect(svg).toBeInTheDocument();
    });
  });

  describe('busy variant', () => {
    it('renders orange spinner', () => {
      const { container } = render(<DataTable columns={columns} data={[]} state="busy" />);
      const spinner = container.querySelector('.animate-spin');
      expect(spinner).toBeInTheDocument();
      expect(spinner).toHaveClass('border-t-2', 'border-orange-500');
    });

    it('shows custom busy message from config', () => {
      render(
        <DataTable
          columns={columns}
          data={[]}
          state="busy"
          busyMessage="Chargement des conteneurs..."
        />
      );
      expect(screen.getByText('Chargement des conteneurs...')).toBeInTheDocument();
    });

    it('does not render table in busy state', () => {
      const { container } = render(<DataTable columns={columns} data={[]} state="busy" />);
      expect(container.querySelector('table')).not.toBeInTheDocument();
    });
  });

  describe('error variant', () => {
    it('shows error message', () => {
      render(
        <DataTable
          columns={columns}
          data={[]}
          state="error"
          error="Échec du chargement"
        />
      );
      expect(screen.getByText('Échec du chargement')).toBeInTheDocument();
    });

    it('renders retry button when onRetry provided', () => {
      let retried = false;
      render(
        <DataTable
          columns={columns}
          data={[]}
          state="error"
          error="Erreur"
          onRetry={() => { retried = true; }}
        />
      );
      const btn = screen.getByRole('button', { name: /réessayer/i });
      btn.click();
      expect(retried).toBe(true);
    });

    it('does not render retry button when onRetry absent', () => {
      render(
        <DataTable columns={columns} data={[]} state="error" error="Erreur" />
      );
      expect(screen.queryByRole('button', { name: /réessayer/i })).not.toBeInTheDocument();
    });
  });

  describe('idle variant', () => {
    it('renders nothing visible (placeholder)', () => {
      const { container } = render(<DataTable columns={columns} data={[]} state="idle" />);
      expect(container.querySelector('table')).not.toBeInTheDocument();
      expect(container.querySelector('.animate-spin')).not.toBeInTheDocument();
    });
  });
});
