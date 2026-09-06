import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { Mock } from 'vitest';
import type { PluginAPI } from '../../../types/plugins';

// Mock recharts ResponsiveContainer to avoid jsdom layout issues (mirror ChartCard.test.tsx)
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container">{children}</div>
    ),
  };
});

// Réseau mocké : le hook useBlockData réel POSTe sur /api/plugins/batch.
vi.mock('../../../hooks/useApi', () => ({
  api: vi.fn(),
}));

const HISTORY = [
  { node_id: 'n1', collected_at: 1700000000, cpu_percent: 45, mem_percent: 60, disk_percent: 30 },
  { node_id: 'n1', collected_at: 1700000600, cpu_percent: 50, mem_percent: 62, disk_percent: 31 },
];

const BATCH_OK = {
  results: [{ command: 'metrics.get_metrics_history', status: 200, data: { history: HISTORY, count: 1 } }],
};

let MetricsHistory: React.ComponentType<{ api: PluginAPI }>;
let apiMock: Mock;

beforeEach(async () => {
  // Le cache SWR module-level persiste entre tests : resetModules isole chaque
  // test (clé de cache = commande + params). Le mock useApi, lui, survit au
  // resetModules → mockReset pour ne pas cumuler les appels entre tests.
  vi.resetModules();
  const useApi = await import('../../../hooks/useApi');
  apiMock = vi.mocked(useApi.api);
  apiMock.mockReset();
  const mod = await import('./MetricsHistory');
  MetricsHistory = mod.default;
});

const renderPage = () => render(<MetricsHistory api={{} as PluginAPI} />);

describe('MetricsHistory — états de la page', () => {
  it('renders the loading panel while fetching', () => {
    apiMock.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText("Chargement de l'historique...")).toBeInTheDocument();
  });

  it('renders the empty panel with the exact French strings', async () => {
    apiMock.mockResolvedValue({
      results: [{ command: 'metrics.get_metrics_history', status: 200, data: { history: [], count: 0 } }],
    });
    renderPage();
    expect(await screen.findByText('Aucune métrique enregistrée')).toBeInTheDocument();
    expect(
      screen.getByText(
        "Aucun point de métrique n'est encore enregistré pour la période et le serveur sélectionnés.",
      ),
    ).toBeInTheDocument();
  });

  it('renders both chart titles from the batch response', async () => {
    apiMock.mockResolvedValue(BATCH_OK);
    renderPage();
    expect(await screen.findByText('Utilisation du Processeur (CPU)')).toBeInTheDocument();
    expect(screen.getByText('Utilisation de la Mémoire RAM')).toBeInTheDocument();
  });

  it('renders the error panel and retries via mutate', async () => {
    apiMock.mockRejectedValue(new Error('boom'));
    renderPage();
    const retry = await screen.findByRole('button', { name: /réessayer/i });
    expect(screen.getByText('boom')).toBeInTheDocument();

    apiMock.mockResolvedValue(BATCH_OK);
    fireEvent.click(retry);
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Utilisation du Processeur (CPU)')).toBeInTheDocument();
  });

  it('changing the period select refetches with the new period param', async () => {
    apiMock.mockResolvedValue(BATCH_OK);
    renderPage();
    await screen.findByText('Utilisation du Processeur (CPU)');
    expect(apiMock).toHaveBeenCalledTimes(1);

    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[1], { target: { value: '7d' } });

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    const lastCall = apiMock.mock.calls[1];
    const body = JSON.parse(String(lastCall[1]?.body));
    expect(body.requests[0].command).toBe('metrics.get_metrics_history');
    expect(body.requests[0].params).toEqual({ period: '7d' });
  });
});