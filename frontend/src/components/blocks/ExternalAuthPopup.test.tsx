/**
 * Tests for ExternalAuthPopup block — contract §7.
 * TDD: written FIRST (red phase) before the component exists.
 * Covers: idle → waiting → success/error/timeout/cancelled state machine,
 * window.open call, window.closed detection → cancel, cancel button always active.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { ExternalAuthPopup } from './ExternalAuthPopup';
import type { ExternalAuthPopupProps } from './types';

const BASE_CONFIG = {
  start_command: 'plex.auth.start',
  cancel_command: 'plex.auth.cancel',
  status_channel: 'plex.auth.status',
  popup_size: { w: 600, h: 700 },
} as const;

function makeProps(overrides?: Partial<ExternalAuthPopupProps>): ExternalAuthPopupProps {
  return {
    context: {
      api: {
        fetch: vi.fn(),
        navigate: vi.fn(),
        navigateGlobal: vi.fn(),
        config: {},
        pluginId: 'plex',
        pluginName: 'Plex',
        t: (_key: string) => _key,
        toast: vi.fn(),
      } as unknown as ExternalAuthPopupProps['context']['api'],
      subscribeStatus: vi.fn(),
    } as unknown as ExternalAuthPopupProps['context'],
    config: BASE_CONFIG,
    title: 'Connexion au compte Plex',
    ...overrides,
  };
}

function makePropsWithFetch(fetchMock: ReturnType<typeof vi.fn>) {
  const base = makeProps();
  return makeProps({
    context: { ...base.context, api: { ...base.context.api, fetch: fetchMock } as unknown as ExternalAuthPopupProps['context']['api'] },
  });
}

async function clickAndFlush(btn: HTMLElement) {
  await act(async () => {
    fireEvent.click(btn);
    await new Promise<void>((r) => { queueMicrotask(r); });
  });
}

let windowOpenSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  windowOpenSpy = vi.fn().mockReturnValue({ closed: false, close: vi.fn() });
  vi.stubGlobal('open', windowOpenSpy);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('ExternalAuthPopup', () => {
  it('renders a connect button in idle state', () => {
    render(<ExternalAuthPopup {...makeProps()} />);
    expect(screen.getByRole('button', { name: /connecter/i })).toBeInTheDocument();
  });

  it('does not render a cancel button in idle state', () => {
    render(<ExternalAuthPopup {...makeProps()} />);
    expect(screen.queryByRole('button', { name: /annuler/i })).not.toBeInTheDocument();
  });

  it('does not call start_command on mount', () => {
    const props = makeProps();
    render(<ExternalAuthPopup {...props} />);
    expect(props.context.api.fetch).not.toHaveBeenCalled();
  });

  it('invokes start_command on click', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ auth_url: 'https://plex.tv/auth/#!?code=abc' });
    const props = makePropsWithFetch(fetchMock);
    render(<ExternalAuthPopup {...props} />);
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));
    expect(fetchMock).toHaveBeenCalledWith(BASE_CONFIG.start_command, { method: 'POST' });
  });

  it('opens popup with auth_url from start_command response', async () => {
    const authUrl = 'https://plex.tv/auth/#!?code=abc123';
    const fetchMock = vi.fn().mockResolvedValue({ auth_url: authUrl });
    const props = makePropsWithFetch(fetchMock);
    render(<ExternalAuthPopup {...props} />);
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));
    expect(windowOpenSpy).toHaveBeenCalledWith(authUrl, expect.any(String), 'width=600,height=700');
  });

  it('shows cancel button when in waiting state', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ auth_url: 'https://plex.tv/auth' });
    const props = makePropsWithFetch(fetchMock);
    render(<ExternalAuthPopup {...props} />);
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));
    expect(screen.getByRole('button', { name: /annuler/i })).toBeInTheDocument();
  });

  it('hides the connect button when in waiting state', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ auth_url: 'https://plex.tv/auth' });
    const props = makePropsWithFetch(fetchMock);
    render(<ExternalAuthPopup {...props} />);
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));
    expect(screen.queryByRole('button', { name: /connecter/i })).not.toBeInTheDocument();
  });

  it('displays a waiting message in French during waiting state', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ auth_url: 'https://plex.tv/auth' });
    const props = makePropsWithFetch(fetchMock);
    render(<ExternalAuthPopup {...props} />);
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));
    expect(screen.getByText(/en attente|authentification/i)).toBeInTheDocument();
  });

  it('invokes cancel_command when cancel button is clicked', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ auth_url: 'https://plex.tv/auth' })
      .mockResolvedValueOnce(undefined);
    const props = makePropsWithFetch(fetchMock);
    render(<ExternalAuthPopup {...props} />);
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));
    await clickAndFlush(screen.getByRole('button', { name: /annuler/i }));
    expect(fetchMock).toHaveBeenCalledWith(BASE_CONFIG.cancel_command, { method: 'POST' });
  });

  it('closes the popup on cancel', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ auth_url: 'https://plex.tv/auth' })
      .mockResolvedValueOnce(undefined);
    const popupObj = { closed: false, close: vi.fn() };
    windowOpenSpy.mockReturnValue(popupObj);
    const props = makePropsWithFetch(fetchMock);
    render(<ExternalAuthPopup {...props} />);
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));
    await clickAndFlush(screen.getByRole('button', { name: /annuler/i }));
    expect(popupObj.close).toHaveBeenCalled();
  });

  it('shows cancelled state after cancel', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ auth_url: 'https://plex.tv/auth' })
      .mockResolvedValueOnce(undefined);
    const props = makePropsWithFetch(fetchMock);
    render(<ExternalAuthPopup {...props} />);
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));
    await clickAndFlush(screen.getByRole('button', { name: /annuler/i }));
    expect(screen.getByText(/annulé|cancel/i)).toBeInTheDocument();
  });

  it('calls cancel_command when popup is detected closed', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ auth_url: 'https://plex.tv/auth' })
      .mockResolvedValueOnce(undefined);
    const popupObj = { closed: false, close: vi.fn() };
    windowOpenSpy.mockReturnValue(popupObj);
    const props = makePropsWithFetch(fetchMock);
    render(<ExternalAuthPopup {...props} />);
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));

    popupObj.closed = true;
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    expect(fetchMock).toHaveBeenCalledWith(BASE_CONFIG.cancel_command, { method: 'POST' });
  });

  it('renders success message in French', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ auth_url: 'https://plex.tv/auth' });
    const props = makePropsWithFetch(fetchMock);
    render(<ExternalAuthPopup {...props} />);
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));

    const subscribeMock = props.context.subscribeStatus as ReturnType<typeof vi.fn>;
    const statusHandler = subscribeMock.mock.calls[0][1];
    await act(async () => { statusHandler({ status: 'success' }); });
    expect(screen.getByText(/réussie|success/i)).toBeInTheDocument();
  });

  it('renders error message in French', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ auth_url: 'https://plex.tv/auth' });
    const props = makePropsWithFetch(fetchMock);
    render(<ExternalAuthPopup {...props} />);
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));

    const subscribeMock = props.context.subscribeStatus as ReturnType<typeof vi.fn>;
    const statusHandler = subscribeMock.mock.calls[0][1];
    await act(async () => { statusHandler({ status: 'error' }); });
    expect(screen.getByText(/erreur|error/i)).toBeInTheDocument();
  });

  it('renders timeout message in French', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ auth_url: 'https://plex.tv/auth' });
    const props = makePropsWithFetch(fetchMock);
    render(<ExternalAuthPopup {...props} />);
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));

    const subscribeMock = props.context.subscribeStatus as ReturnType<typeof vi.fn>;
    const statusHandler = subscribeMock.mock.calls[0][1];
    await act(async () => { statusHandler({ status: 'timeout' }); });
    expect(screen.getByText(/expiré|timeout/i)).toBeInTheDocument();
  });

  it('allows retrying after success', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ auth_url: 'https://plex.tv/auth' })
      .mockResolvedValueOnce({ auth_url: 'https://plex.tv/auth2' });
    const props = makePropsWithFetch(fetchMock);
    render(<ExternalAuthPopup {...props} />);
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));

    const subscribeMock = props.context.subscribeStatus as ReturnType<typeof vi.fn>;
    const statusHandler = subscribeMock.mock.calls[0][1];
    await act(async () => { statusHandler({ status: 'success' }); });

    await clickAndFlush(screen.getByRole('button', { name: /reconnecter|réessayer/i }));
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));

    expect(windowOpenSpy).toHaveBeenCalledTimes(2);
  });

  it('uses popup_size from config for window.open', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ auth_url: 'https://plex.tv/auth' });
    const config = { ...BASE_CONFIG, popup_size: { w: 500, h: 600 } };
    const props = makeProps({ config, context: { ...makeProps().context, api: { ...makeProps().context.api, fetch: fetchMock } as unknown as ExternalAuthPopupProps['context']['api'] } });
    render(<ExternalAuthPopup {...props} />);
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));
    expect(windowOpenSpy).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      'width=500,height=600',
    );
  });

  it('renders the title prop as heading', () => {
    render(<ExternalAuthPopup {...makeProps()} />);
    expect(screen.getByText('Connexion au compte Plex')).toBeInTheDocument();
  });

  it('renders a default title when no title prop provided', () => {
    render(<ExternalAuthPopup {...makeProps({ title: undefined })} />);
    expect(screen.getByText(/authentification|connexion/i)).toBeInTheDocument();
  });

  it('closes popup and dispatches cancel command on unmount if popup is open', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ auth_url: 'https://plex.tv/auth' });
    const popupCloseSpy = vi.fn();
    windowOpenSpy.mockReturnValue({ closed: false, close: popupCloseSpy });
    const props = makePropsWithFetch(fetchMock);
    const { unmount } = render(<ExternalAuthPopup {...props} />);
    await clickAndFlush(screen.getByRole('button', { name: /connecter/i }));

    expect(windowOpenSpy).toHaveBeenCalled();
    unmount();

    expect(popupCloseSpy).toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledWith(BASE_CONFIG.cancel_command, { method: 'POST' });
  });
});
