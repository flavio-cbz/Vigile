import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { Mock } from 'vitest';
import type { PluginAPI } from '../../../types/plugins';

// Réseau mocké : le hook useBlockData réel POSTe sur /api/plugins/batch.
vi.mock('../../../hooks/useApi', () => ({
  api: vi.fn(),
}));

const SERVICES = [
  {
    node_id: 'n1',
    name: 'ssh.service',
    state: 'active',
    status: 'running',
  },
  {
    node_id: 'n1',
    name: 'nginx.service',
    state: 'inactive',
    status: 'dead',
  },
  {
    node_id: 'n1',
    name: 'redis.service',
    state: 'active',
    status: 'running',
  },
];

const BATCH_OK = {
  results: [{ command: 'systemd.list_services_route', status: 200, data: { services: SERVICES } }],
};

let SystemdServices: React.ComponentType<{ api: PluginAPI }>;
let apiMock: Mock;

beforeEach(async () => {
  localStorage.setItem(
    'vigile_user',
    JSON.stringify({ username: 'admin', role: 'admin', user_id: 'u1' }),
  );
  vi.resetModules();
  const useApi = await import('../../../hooks/useApi');
  apiMock = vi.mocked(useApi.api);
  apiMock.mockReset();

  const { useAuthStore } = await import('../../../store/authStore');
  useAuthStore.setState({
    user: { username: 'admin', role: 'admin', user_id: 'u1' },
    isAuthenticated: true,
  });

  const mod = await import('./SystemdServices');
  SystemdServices = mod.default;
});

const makeApi = () => ({
  fetch: vi.fn(),
  toast: vi.fn(),
  navigate: vi.fn(),
  navigateGlobal: vi.fn(),
  config: {},
  pluginId: 'systemd',
  pluginName: 'Systemd',
  t: vi.fn(),
});

const renderPage = (api: PluginAPI = makeApi() as unknown as PluginAPI) =>
  render(<SystemdServices api={api} />);

describe('SystemdServices — états de la page', () => {
  it('renders the loading panel while fetching', () => {
    apiMock.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Chargement des services...')).toBeInTheDocument();
  });

  it('renders the empty panel with the exact French strings', async () => {
    apiMock.mockResolvedValue({
      results: [{ command: 'systemd.list_services_route', status: 200, data: { services: [] } }],
    });
    renderPage();
    expect(await screen.findByText('Aucun service trouvé')).toBeInTheDocument();
  });

  it('renders service rows with name, state, status and actions (protecting ssh.service)', async () => {
    apiMock.mockResolvedValue(BATCH_OK);
    renderPage();
    expect(await screen.findByText('ssh.service')).toBeInTheDocument();
    expect(screen.getByText('nginx.service')).toBeInTheDocument();
    expect(screen.getByText('redis.service')).toBeInTheDocument();
    // État via StatusPill
    expect(screen.getAllByText('active')).toHaveLength(2);
    expect(screen.getByText('inactive')).toBeInTheDocument();
    // Statut sub
    expect(screen.getAllByText('running')).toHaveLength(2);
    expect(screen.getByText('dead')).toBeInTheDocument();
    // Actions : stop (redis.service only! ssh.service is protected), start (nginx inactive), restart (all 3)
    expect(screen.getAllByRole('button', { name: 'Arrêter le service' })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: 'Démarrer le service' })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: 'Redémarrer le service' })).toHaveLength(3);
  });

  it('masks stop action for non-admin operators even on unprotected services', async () => {
    const { useAuthStore } = await import('../../../store/authStore');
    useAuthStore.setState({
      user: { username: 'operator', role: 'operator', user_id: 'u2' },
      isAuthenticated: true,
    });

    apiMock.mockResolvedValue(BATCH_OK);
    renderPage();
    expect(await screen.findByText('redis.service')).toBeInTheDocument();

    // No stop button should appear for operator
    expect(screen.queryByRole('button', { name: 'Arrêter le service' })).not.toBeInTheDocument();
  });

  it('renders the error panel and retries via mutate', async () => {
    apiMock.mockRejectedValue(new Error('boom'));
    renderPage();
    const retry = await screen.findByRole('button', { name: /réessayer/i });
    expect(screen.getByText('boom')).toBeInTheDocument();

    apiMock.mockResolvedValue(BATCH_OK);
    fireEvent.click(retry);
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('ssh.service')).toBeInTheDocument();
  });

  it('dispatches the service action via plugin api then refetches via mutate', async () => {
    apiMock.mockResolvedValue(BATCH_OK);
    const api = makeApi();
    api.fetch.mockResolvedValue({ success: true });
    renderPage(api as unknown as PluginAPI);
    await screen.findByText('nginx.service');

    fireEvent.click(screen.getAllByRole('button', { name: 'Redémarrer le service' })[0]);

    await waitFor(() =>
      expect(api.fetch).toHaveBeenCalledWith(
        '/services/ssh.service/restart',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ node_id: 'n1' }),
        }),
      ),
    );
    expect(api.toast).toHaveBeenCalledWith(
      'Action restart exécutée avec succès',
      'success',
    );
  });

  it('shows error toast when API returns success: false', async () => {
    apiMock.mockResolvedValue(BATCH_OK);
    const api = makeApi();
    api.fetch.mockResolvedValue({ success: false, error: 'Service is masked' });
    renderPage(api as unknown as PluginAPI);
    await screen.findByText('nginx.service');

    fireEvent.click(screen.getAllByRole('button', { name: 'Redémarrer le service' })[0]);

    await waitFor(() =>
      expect(api.toast).toHaveBeenCalledWith(
        'Service is masked',
        'error',
      ),
    );
  });
});