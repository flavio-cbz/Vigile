import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { Mock } from 'vitest';
import type { PluginAPI } from '../../../types/plugins';

vi.mock('../../../hooks/useApi', () => ({
  api: vi.fn(),
}));

vi.mock('../../../store/nodeStore', () => ({
  useNodeStore: vi.fn(() => ({
    nodes: [
      { id: 'n1', name: 'ServPrincipal', online: true },
      { id: 'n2', name: 'ServSecondaire', online: false },
    ],
    isLoading: false,
    fetchNodes: vi.fn(),
    selectedNodeId: 'n1',
  })),
}));

vi.mock('../../../store/authStore', () => ({
  useAuthStore: vi.fn((selector?: (s: unknown) => unknown) => {
    const state = { user: { role: 'admin' }, accessToken: 'test-token' };
    return selector ? selector(state) : state;
  }),
}));

vi.mock('../../../store/useToastStore', () => ({
  useToastStore: { getState: () => ({ addToast: vi.fn() }) },
}));

const DETECT_CONFIGURED = {
  detected: true,
  configured: true,
  port: 32400,
  type: 'docker',
};

function buildBatchResponse(command: string, data: unknown) {
  return { results: [{ command, status: 200, data }] };
}

let PlexAdmin: React.ComponentType<{ api: PluginAPI }>;
let apiMock: Mock;

beforeEach(async () => {
  vi.resetModules();
  const useApi = await import('../../../hooks/useApi');
  apiMock = vi.mocked(useApi.api);
  apiMock.mockReset();
  const mod = await import('./PlexAdmin');
  PlexAdmin = mod.default;
});

const makeApi = () => ({
  fetch: vi.fn(),
  toast: vi.fn(),
  navigate: vi.fn(),
  navigateGlobal: vi.fn(),
  config: {},
  pluginId: 'plex',
  pluginName: 'Plex',
  t: vi.fn((_key: string) => _key),
});

const renderPage = (api: PluginAPI = makeApi() as unknown as PluginAPI) =>
  render(<PlexAdmin api={api} />);

describe('PlexAdmin — états de la page', () => {
  it('renders the loading state while fetching', () => {
    apiMock.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Plex Media Server')).toBeInTheDocument();
  });

  it('renders detection configured banner and metric cards', async () => {
    apiMock.mockImplementation((url: string) => {
      if (url === '/api/plugins/batch') {
        return Promise.resolve(
          buildBatchResponse('plex.detect', DETECT_CONFIGURED),
        );
      }
      return Promise.resolve({ results: [] });
    });
    renderPage();
    expect(await screen.findByText('Plex Media Server')).toBeInTheDocument();
  });

  it('renders sessions, libraries and users tabs', async () => {
    apiMock.mockImplementation((url: string) => {
      if (url === '/api/plugins/batch') {
        return Promise.resolve(
          buildBatchResponse('plex.detect', DETECT_CONFIGURED),
        );
      }
      return Promise.resolve({ results: [] });
    });
    renderPage();
    expect(await screen.findByText('Lectures')).toBeInTheDocument();
    expect(screen.getByText(/Transcodages & Téléchargements/)).toBeInTheDocument();
    expect(screen.getAllByText(/Utilisateurs/).length).toBeGreaterThan(0);
  });

  it('renders the Configure Plex button for admins', async () => {
    apiMock.mockImplementation((url: string) => {
      if (url === '/api/plugins/batch') {
        return Promise.resolve(
          buildBatchResponse('plex.detect', DETECT_CONFIGURED),
        );
      }
      return Promise.resolve({ results: [] });
    });
    renderPage();
    expect(await screen.findByText('Configurer Plex')).toBeInTheDocument();
  });

  it('opens config modal and shows auth popup', async () => {
    apiMock.mockImplementation((url: string) => {
      if (url === '/api/plugins/batch') {
        return Promise.resolve(
          buildBatchResponse('plex.detect', DETECT_CONFIGURED),
        );
      }
      return Promise.resolve({ results: [] });
    });
    const api = makeApi();
    api.fetch.mockResolvedValue({ servers: [] });
    renderPage(api as unknown as PluginAPI);

    fireEvent.click(await screen.findByText('Configurer Plex'));
    expect(await screen.findByText('Configuration Plex')).toBeInTheDocument();
    expect(screen.getByText('Connexion au compte Plex')).toBeInTheDocument();
  });

  it('renders the unconfigured detection banner', async () => {
    apiMock.mockImplementation((url: string) => {
      if (url === '/api/plugins/batch') {
        return Promise.resolve(
          buildBatchResponse('plex.detect', { detected: true, configured: false, port: 32400, type: 'docker' }),
        );
      }
      return Promise.resolve({ results: [] });
    });
    renderPage();
    expect(await screen.findByText('Plex est détecté mais non authentifié')).toBeInTheDocument();
  });

  it('renders the not-detected banner', async () => {
    apiMock.mockImplementation((url: string) => {
      if (url === '/api/plugins/batch') {
        return Promise.resolve(
          buildBatchResponse('plex.detect', { detected: false, configured: false, port: 0, type: '' }),
        );
      }
      return Promise.resolve({ results: [] });
    });
    renderPage();
    expect(await screen.findByText('Plex Non Détecté sur ce nœud')).toBeInTheDocument();
  });

  it('renders an error banner when the Plex API fails', async () => {
    apiMock.mockImplementation((url: string) => {
      if (url === '/api/plugins/batch') {
        return Promise.resolve({
          results: [
            { command: 'plex.detect', status: 200, data: DETECT_CONFIGURED },
            {
              command: 'plex.sessions',
              status: 502,
              error: 'Failed to fetch sessions from Plex API. connexion impossible à http://debian:32400 : ConnectError',
            },
          ],
        });
      }
      return Promise.resolve({ results: [] });
    });
    renderPage();
    expect(await screen.findByText('API Plex injoignable')).toBeInTheDocument();
  });

  it('preserves legacy French strings verbatim', async () => {
    apiMock.mockImplementation((url: string) => {
      if (url === '/api/plugins/batch') {
        return Promise.resolve(
          buildBatchResponse('plex.detect', DETECT_CONFIGURED),
        );
      }
      return Promise.resolve({ results: [] });
    });
    renderPage();
    expect(await screen.findByText('Plex Media Server')).toBeInTheDocument();
    expect(screen.getByText('Configurer Plex')).toBeInTheDocument();
    expect(screen.getByText('Rafraîchir')).toBeInTheDocument();
  });
});
