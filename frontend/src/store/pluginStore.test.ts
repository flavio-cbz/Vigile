import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../hooks/useApi';
import { DEFAULT_ACTIVE_PLUGINS, usePluginStore } from './pluginStore';
import type { AdminPluginInfo, PluginPageEntry } from '../types/plugins';

vi.mock('../hooks/useApi', () => ({
  api: vi.fn(),
}));

const apiMock = vi.mocked(api);

function makePage(overrides: Partial<PluginPageEntry> = {}): PluginPageEntry {
  return {
    plugin_id: 'metrics',
    id: 'metrics',
    title: 'Metrics',
    icon: null,
    sidebar: true,
    component: 'MetricsHistory',
    route: '/plugins/metrics/history',
    roles: ['admin'],
    params: [],
    ...overrides,
  };
}

function makeAdminPlugin(overrides: Partial<AdminPluginInfo> = {}): AdminPluginInfo {
  return {
    id: 'metrics',
    name: 'Metrics',
    description: '',
    category: 'system',
    schema: {},
    enabled: true,
    loaded: true,
    config: {},
    ...overrides,
  };
}

type RouteHandlers = Record<string, () => Promise<unknown>>;

const mockApiRoutes = (routes: RouteHandlers) => {
  apiMock.mockImplementation(((url: string) =>
    routes[url]
      ? routes[url]()
      : Promise.reject(new Error(`Unhandled URL in test mock: ${String(url)}`))) as unknown as typeof api);
};

describe('pluginStore.refreshRegistry', () => {
  beforeEach(() => {
    usePluginStore.setState({
      pages: [],
      loading: false,
      error: null,
      apiVersion: null,
      activePluginIds: [...DEFAULT_ACTIVE_PLUGINS],
    });
  });

  afterEach(() => {
    apiMock.mockReset();
  });

  it('refetches pages and active plugins and reports success', async () => {
    mockApiRoutes({
      '/api/plugins/pages': () =>
        Promise.resolve({ version: 1, pages: [makePage()] }),
      '/api/admin/plugins': () =>
        Promise.resolve([
          makeAdminPlugin({ id: 'metrics', enabled: true, loaded: true }),
          makeAdminPlugin({ id: 'docker', enabled: true, loaded: false }),
          makeAdminPlugin({ id: 'plex', enabled: false, loaded: false }),
        ]),
    });

    await expect(usePluginStore.getState().refreshRegistry()).resolves.toBe(true);

    expect(apiMock).toHaveBeenCalledWith('/api/plugins/pages');
    expect(apiMock).toHaveBeenCalledWith('/api/admin/plugins');
    expect(usePluginStore.getState().pages).toEqual([makePage()]);
    expect(usePluginStore.getState().activePluginIds).toEqual(['metrics']);
  });

  it('retries once after a failed attempt then succeeds', async () => {
    let pagesCalls = 0;
    mockApiRoutes({
      '/api/plugins/pages': () => {
        pagesCalls += 1;
        return pagesCalls === 1
          ? Promise.reject(new Error('transient network failure'))
          : Promise.resolve({ version: 1, pages: [makePage({ plugin_id: 'docker', id: 'docker' })] });
      },
      '/api/admin/plugins': () =>
        Promise.resolve([makeAdminPlugin({ id: 'docker' })]),
    });

    await expect(usePluginStore.getState().refreshRegistry()).resolves.toBe(true);

    expect(pagesCalls).toBe(2);
    expect(apiMock).toHaveBeenCalledTimes(4);
    expect(usePluginStore.getState().pages).toEqual([makePage({ plugin_id: 'docker', id: 'docker' })]);
    expect(usePluginStore.getState().activePluginIds).toEqual(['docker']);
  });

  it('returns false and preserves previous state when both fetches keep failing', async () => {
    usePluginStore.setState({
      pages: [makePage()],
      activePluginIds: ['legacy-plugin'],
    });
    mockApiRoutes({
      '/api/plugins/pages': () => Promise.reject(new Error('network down')),
      '/api/admin/plugins': () => Promise.reject(new Error('network down')),
    });

    await expect(usePluginStore.getState().refreshRegistry()).resolves.toBe(false);

    expect(usePluginStore.getState().pages).toEqual([makePage()]);
    expect(usePluginStore.getState().activePluginIds).toEqual(['legacy-plugin']);
  });
});
