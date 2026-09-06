import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { Mock } from 'vitest';
import type { PluginAPI } from '../../../types/plugins';
import { useAuthStore } from '../../../store/authStore';

// Réseau mocké : le hook useBlockData réel POSTe sur /api/plugins/batch.
vi.mock('../../../hooks/useApi', () => ({
  api: vi.fn(),
}));

const CONTAINERS = [
  {
    node_id: 'n1',
    id: 'abc123def456',
    name: 'nginx',
    image: 'nginx:latest',
    state: 'running',
    ports: ['0.0.0.0:80->80/tcp', '0.0.0.0:443->443/tcp'],
  },
  {
    node_id: 'n1',
    id: 'xyz789uvw012',
    name: 'redis',
    image: 'redis:7',
    state: 'exited',
    ports: [],
  },
];

const BATCH_OK = {
  results: [{ command: 'docker.list_containers_route', status: 200, data: { containers: CONTAINERS } }],
};

let DockerContainers: React.ComponentType<{ api: PluginAPI }>;
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

  const mod = await import('./DockerContainers');
  DockerContainers = mod.default;
});

const makeApi = () => ({
  fetch: vi.fn(),
  toast: vi.fn(),
  navigate: vi.fn(),
  navigateGlobal: vi.fn(),
  config: {},
  pluginId: 'docker',
  pluginName: 'Docker',
  t: vi.fn(),
});

const renderPage = (api: PluginAPI = makeApi() as unknown as PluginAPI) =>
  render(<DockerContainers api={api} />);

describe('DockerContainers — états de la page', () => {
  it('renders the loading panel while fetching', () => {
    apiMock.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Chargement des conteneurs...')).toBeInTheDocument();
  });

  it('renders the empty panel with the exact French strings', async () => {
    apiMock.mockResolvedValue({
      results: [{ command: 'docker.list_containers_route', status: 200, data: { containers: [] } }],
    });
    renderPage();
    expect(await screen.findByText('Aucun conteneur trouvé')).toBeInTheDocument();
  });

  it('renders container rows with name, image, state, ports and the action buttons for admin', async () => {
    apiMock.mockResolvedValue(BATCH_OK);
    renderPage();
    expect(await screen.findByText('nginx')).toBeInTheDocument();
    expect(screen.getByText('nginx:latest')).toBeInTheDocument();
    expect(screen.getByText('redis')).toBeInTheDocument();
    expect(screen.getByText('redis:7')).toBeInTheDocument();
    // Statut via StatusPill
    expect(screen.getByText('running')).toBeInTheDocument();
    expect(screen.getByText('exited')).toBeInTheDocument();
    // Ports chips + fallback em-dash
    expect(screen.getByText('0.0.0.0:80->80/tcp')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
    // Actions : stop (nginx running), start (redis exited), restart (les deux), delete (redis exited pour admin)
    expect(screen.getAllByRole('button', { name: 'Arrêter le conteneur' })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: 'Démarrer le conteneur' })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: 'Redémarrer le conteneur' })).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: 'Supprimer le conteneur' })).toHaveLength(1);
  });

  it('renders the error panel and retries via mutate', async () => {
    apiMock.mockRejectedValue(new Error('boom'));
    renderPage();
    const retry = await screen.findByRole('button', { name: /réessayer/i });
    expect(screen.getByText('boom')).toBeInTheDocument();

    apiMock.mockResolvedValue(BATCH_OK);
    fireEvent.click(retry);
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('nginx')).toBeInTheDocument();
  });

  it('dispatches the container restart action with container_name via plugin api', async () => {
    apiMock.mockResolvedValue(BATCH_OK);
    const api = makeApi();
    api.fetch.mockResolvedValue({ success: true });
    renderPage(api as unknown as PluginAPI);
    await screen.findByText('nginx');

    fireEvent.click(screen.getAllByRole('button', { name: 'Redémarrer le conteneur' })[0]);

    await waitFor(() =>
      expect(api.fetch).toHaveBeenCalledWith(
        '/containers/abc123def456/restart',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ node_id: 'n1', container_name: 'nginx' }),
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
    api.fetch.mockResolvedValue({ success: false, error: 'Container is already stopped' });
    renderPage(api as unknown as PluginAPI);
    await screen.findByText('nginx');

    fireEvent.click(screen.getAllByRole('button', { name: 'Redémarrer le conteneur' })[0]);

    await waitFor(() =>
      expect(api.toast).toHaveBeenCalledWith(
        'Container is already stopped',
        'error',
      ),
    );
  });

  it('opens ConfirmDeleteModal on delete click and deletes when name matches', async () => {
    apiMock.mockResolvedValue(BATCH_OK);
    const api = makeApi();
    api.fetch.mockResolvedValue({ success: true });
    renderPage(api as unknown as PluginAPI);
    await screen.findByText('redis');

    const deleteBtn = screen.getByRole('button', { name: 'Supprimer le conteneur' });
    fireEvent.click(deleteBtn);

    // Modal title appears
    expect(await screen.findByText('Supprimer le conteneur Docker')).toBeInTheDocument();

    const input = screen.getByPlaceholderText(/Tapez "redis" pour confirmer/i);
    const confirmBtn = screen.getByRole('button', { name: 'Supprimer définitivement' });

    // Confirm button is disabled until name matches
    expect(confirmBtn).toBeDisabled();

    fireEvent.change(input, { target: { value: 'redis' } });
    expect(confirmBtn).not.toBeDisabled();

    fireEvent.click(confirmBtn);

    await waitFor(() =>
      expect(api.fetch).toHaveBeenCalledWith(
        '/containers/xyz789uvw012/delete',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ node_id: 'n1', container_name: 'redis' }),
        }),
      ),
    );
  });
});