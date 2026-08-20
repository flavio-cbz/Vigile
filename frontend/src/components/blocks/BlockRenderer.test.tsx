import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import type { ComponentProps } from 'react';
import { BlockRenderer } from './BlockRenderer';
import { registerBlock } from './registry';
import { useAuthStore } from '../../store/authStore';
import { useNodeStore } from '../../store/nodeStore';
import { useToastStore } from '../../store/useToastStore';
import type { BlockConfig, BlockProps } from './types';

const TestBlock = ({ context, config, state, data }: BlockProps) => (
  <div data-testid="test-block">
    <span data-testid="block-type">{config.type}</span>
    <span data-testid="block-state">{state}</span>
    <span data-testid="block-node-id">{context.node_id ?? 'none'}</span>
    <span data-testid="block-roles">{context.roles.join(',')}</span>
    <span data-testid="block-data">{JSON.stringify(data ?? null)}</span>
    <span data-testid="block-params">{JSON.stringify(context.params)}</span>
    <span data-testid="block-config">{JSON.stringify(context.config)}</span>
  </div>
);

const FetchProbe = ({ context }: BlockProps) => (
  <button onClick={() => void context.api.fetch('/containers')}>fetch</button>
);

const NavProbe = ({ context }: BlockProps) => (
  <button onClick={() => context.navigate('/sub')}>nav</button>
);

const ToastProbe = ({ context }: BlockProps) => (
  <button onClick={() => context.toast('hello', 'success')}>toast</button>
);

const ThrowingBlock = () => {
  throw new Error('block exploded');
};

const renderRenderer = (
  blocks: BlockConfig[],
  props: Partial<Omit<ComponentProps<typeof BlockRenderer>, 'blocks'>> = {}
) =>
  render(
    <MemoryRouter initialEntries={['/plugins/docker/containers']}>
      <BlockRenderer pluginId="docker" blocks={blocks} {...props} />
    </MemoryRouter>
  );

describe('BlockRenderer', () => {
  afterEach(() => {
    cleanup();
    useNodeStore.setState({ selectedNodeId: 'all', nodes: [] });
    useAuthStore.setState({ user: null, isAuthenticated: false });
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('dispatches on config.type to the registered block component', () => {
    registerBlock('test-block', TestBlock);
    renderRenderer(
      [{ id: 'b1', type: 'test-block', title: 'Test' }],
      { states: { b1: 'data' }, data: { b1: { x: 1 } } }
    );
    expect(screen.getByTestId('block-type')).toHaveTextContent('test-block');
    expect(screen.getByTestId('block-state')).toHaveTextContent('data');
    expect(screen.getByTestId('block-data')).toHaveTextContent('{"x":1}');
  });

  it('renders an error card for an unknown block type (fail-closed)', () => {
    renderRenderer([{ id: 'b1', type: 'nope', title: 'Nope' }], { states: { b1: 'data' } });
    expect(screen.getByText('Type de bloc inconnu : nope')).toBeInTheDocument();
  });

  it('injects node_id from the nodeStore global selector when needs includes node_id', () => {
    registerBlock('test-block', TestBlock);
    useNodeStore.setState({ selectedNodeId: 'node-42' });
    renderRenderer(
      [{ id: 'b1', type: 'test-block', title: 'Test', needs: ['node_id'] }],
      { states: { b1: 'data' } }
    );
    expect(screen.getByTestId('block-node-id')).toHaveTextContent('node-42');
  });

  it('does not inject node_id when the store selection is "all"', () => {
    registerBlock('test-block', TestBlock);
    useNodeStore.setState({ selectedNodeId: 'all' });
    renderRenderer(
      [{ id: 'b1', type: 'test-block', title: 'Test', needs: ['node_id'] }],
      { states: { b1: 'data' } }
    );
    expect(screen.getByTestId('block-node-id')).toHaveTextContent('none');
  });

  it('injects roles from the auth store session, defaulting to viewer', () => {
    registerBlock('test-block', TestBlock);
    renderRenderer([{ id: 'b1', type: 'test-block', title: 'Test' }], { states: { b1: 'data' } });
    expect(screen.getByTestId('block-roles')).toHaveTextContent('viewer');

    cleanup();
    useAuthStore.setState({ user: { user_id: 'u1', username: 'demo', role: 'operator' } });
    renderRenderer([{ id: 'b1', type: 'test-block', title: 'Test' }], { states: { b1: 'data' } });
    expect(screen.getByTestId('block-roles')).toHaveTextContent('operator');
  });

  it('injects route params from useParams into the context', () => {
    registerBlock('test-block', TestBlock);
    render(
      <MemoryRouter initialEntries={['/plugins/docker/containers/abc']}>
        <Routes>
          <Route
            path="/plugins/docker/containers/:containerId"
            element={
              <BlockRenderer
                pluginId="docker"
                blocks={[{ id: 'b1', type: 'test-block', title: 'Test' }]}
                states={{ b1: 'data' }}
              />
            }
          />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByTestId('block-params')).toHaveTextContent('"containerId":"abc"');
  });

  it('renders the idle placeholder variant', () => {
    renderRenderer([{ id: 'b1', type: 'test-block', title: 'Test' }]);
    expect(screen.getByTestId('block-idle')).toBeInTheDocument();
  });

  it('renders the busy spinner variant with the orange token', () => {
    renderRenderer([{ id: 'b1', type: 'test-block', title: 'Test' }], { states: { b1: 'busy' } });
    const spinner = screen.getByTestId('block-busy').querySelector('.animate-spin');
    expect(spinner).not.toBeNull();
    expect(spinner?.className).toContain('border-t-2');
    expect(spinner?.className).toContain('border-orange-500');
  });

  it('renders the error variant with message and retry', () => {
    const onRetry = vi.fn();
    renderRenderer(
      [{ id: 'b1', type: 'test-block', title: 'Test' }],
      { states: { b1: 'error' }, errors: { b1: new Error('fetch failed') }, onRetry }
    );
    expect(screen.getByText('Une erreur est survenue')).toBeInTheDocument();
    expect(screen.getByText('fetch failed')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Réessayer' }));
    expect(onRetry).toHaveBeenCalledWith('b1');
  });

  it('renders the empty variant with AlertCircle and the French message', () => {
    renderRenderer(
      [{ id: 'b1', type: 'test-block', title: 'Test', emptyMessage: 'Aucun conteneur trouvé' }],
      { states: { b1: 'empty' } }
    );
    expect(screen.getByText('Aucun conteneur trouvé')).toBeInTheDocument();
    // lucide v1.28 renames alert-circle → circle-alert; assert the icon by presence, not class name.
    expect(screen.getByTestId('block-empty').querySelector('svg')).not.toBeNull();
  });

  it('api.fetch prefixes /api/plugins/{pluginId}/', async () => {
    registerBlock('fetch-probe', FetchProbe);
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );
    vi.stubGlobal('fetch', fetchMock);
    renderRenderer([{ id: 'b1', type: 'fetch-probe', title: 'Fetch' }], { states: { b1: 'data' } });
    fireEvent.click(screen.getByRole('button', { name: 'fetch' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe('/api/plugins/docker/containers');
  });

  it('context.navigate prefixes /plugins/{pluginId}/', async () => {
    registerBlock('nav-probe', NavProbe);
    render(
      <MemoryRouter initialEntries={['/plugins/docker/containers']}>
        <Routes>
          <Route
            path="/plugins/docker/containers"
            element={
              <BlockRenderer
                pluginId="docker"
                blocks={[{ id: 'b1', type: 'nav-probe', title: 'Nav' }]}
                states={{ b1: 'data' }}
              />
            }
          />
          <Route path="/plugins/docker/sub" element={<div>landed</div>} />
        </Routes>
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole('button', { name: 'nav' }));
    expect(await screen.findByText('landed')).toBeInTheDocument();
  });

  it('context.toast forwards to the toast store', () => {
    registerBlock('toast-probe', ToastProbe);
    const toastSpy = vi.spyOn(useToastStore.getState(), 'addToast');
    renderRenderer([{ id: 'b1', type: 'toast-probe', title: 'Toast' }], { states: { b1: 'data' } });
    fireEvent.click(screen.getByRole('button', { name: 'toast' }));
    expect(toastSpy).toHaveBeenCalledWith('success', 'hello');
  });

  it('wraps every block in an ErrorBoundary: a throwing block shows the fallback, never a blank page', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    registerBlock('throwing-block', ThrowingBlock);
    renderRenderer([{ id: 'b1', type: 'throwing-block', title: 'Boom' }], { states: { b1: 'data' } });
    expect(await screen.findByText('Une erreur est survenue')).toBeInTheDocument();
    expect(screen.getByText('block exploded')).toBeInTheDocument();
  });
});