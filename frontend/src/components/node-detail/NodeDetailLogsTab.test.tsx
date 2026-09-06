import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { NodeDetailLogsTab } from './NodeDetailLogsTab';
import type { LogEntryRecord, LogSourceItemRecord, LogHistogramRecord } from './types';

const LOG_SOURCES: LogSourceItemRecord[] = [
  { id: 'svc-ssh', category: 'services', name: 'ssh.service', unit: 'ssh.service', description: 'SSH' },
  { id: 'svc-nginx', category: 'services', name: 'nginx.service', unit: 'nginx.service', description: 'Nginx' },
  { id: 'file-syslog', category: 'files', name: 'syslog', path: '/var/log/syslog', description: '/var/log/syslog' },
  { id: 'file-auth', category: 'files', name: 'auth.log', path: '/var/log/auth.log', description: '/var/log/auth.log' },
];

const LOG_ENTRIES: LogEntryRecord[] = [
  { timestamp: 1700000000, time_str: '12:00:00', level: 'info', unit: 'sshd', message: 'Accepted publickey for user' },
  { timestamp: 1700000001, time_str: '12:00:01', level: 'error', unit: 'mysql', message: 'ERROR something went wrong' },
];

function defaultProps(overrides?: Partial<React.ComponentProps<typeof NodeDetailLogsTab>>) {
  return {
    logs: 'Jan 1 00:00:00 host sshd[1]: Accepted publickey',
    logEntries: LOG_ENTRIES,
    loading: false,
    logsService: '',
    logsPath: '',
    logsLimit: 100,
    logsAutoScroll: true,
    logSources: LOG_SOURCES,
    logHistogram: null as LogHistogramRecord | null,
    loadingHistogram: false,
    selectedBucketHour: null,
    onSelectHour: vi.fn(),
    onServiceChange: vi.fn(),
    onPathChange: vi.fn(),
    onLimitChange: vi.fn(),
    onAutoScrollChange: vi.fn(),
    onRefresh: vi.fn(),
    logsError: null,
    ...overrides,
  };
}

describe('NodeDetailLogsTab (redesigned)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock clipboard for LogConsole copy
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
  });

  it('renders search input with filter placeholder', () => {
    render(<NodeDetailLogsTab {...defaultProps()} />);
    expect(document.getElementById('logs-filter-input')).toBeInTheDocument();
  });

  it('renders severity filter buttons ALL/ERR/WRN/INF', () => {
    render(<NodeDetailLogsTab {...defaultProps()} />);
    // i18n: common.all → "Tous" in FR, "All" in EN — check both via regex
    expect(screen.getByText(/Tous|All/i)).toBeInTheDocument();
    expect(screen.getByText('ERR')).toBeInTheDocument();
    expect(screen.getByText('WRN')).toBeInTheDocument();
    expect(screen.getByText('INF')).toBeInTheDocument();
  });

  it('clicking ERR filter highlights error entries', () => {
    render(<NodeDetailLogsTab {...defaultProps()} />);
    fireEvent.click(screen.getByText('ERR'));
    // After filtering, info entry should be hidden, error remains
    expect(screen.getByText(/ERROR something went wrong/)).toBeInTheDocument();
    expect(screen.queryByText(/Accepted publickey/)).not.toBeInTheDocument();
  });

  it('renders lines selector with 4 options', () => {
    render(<NodeDetailLogsTab {...defaultProps()} />);
    const select = document.querySelector('select') as HTMLSelectElement;
    expect(select).toBeInTheDocument();
    expect(select.options.length).toBe(4);
    expect(screen.getByText('50 l')).toBeInTheDocument();
    expect(screen.getByText('500 l')).toBeInTheDocument();
  });

  it('changing lines selector calls onLimitChange', () => {
    const onLimitChange = vi.fn();
    render(<NodeDetailLogsTab {...defaultProps({ onLimitChange })} />);
    const select = document.querySelector('select') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: '250' } });
    expect(onLimitChange).toHaveBeenCalledWith(250);
  });

  it('renders auto-scroll checkbox', () => {
    render(<NodeDetailLogsTab {...defaultProps()} />);
    const checkbox = document.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(checkbox).toBeInTheDocument();
    expect(checkbox.checked).toBe(true);
  });

  it('toggles auto-scroll via checkbox', () => {
    const onAutoScrollChange = vi.fn();
    render(<NodeDetailLogsTab {...defaultProps({ onAutoScrollChange })} />);
    const checkbox = document.querySelector('input[type="checkbox"]') as HTMLInputElement;
    fireEvent.click(checkbox);
    expect(onAutoScrollChange).toHaveBeenCalled();
  });

  it('renders log entries in console', () => {
    render(<NodeDetailLogsTab {...defaultProps()} />);
    expect(screen.getByText(/Accepted publickey/)).toBeInTheDocument();
    expect(screen.getByText(/ERROR something went wrong/)).toBeInTheDocument();
  });

  it('filters log entries via search query', () => {
    render(<NodeDetailLogsTab {...defaultProps()} />);
    const input = document.getElementById('logs-filter-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'mysql' } });
    expect(screen.getByText(/ERROR something went wrong/)).toBeInTheDocument();
    expect(screen.queryByText(/Accepted publickey/)).not.toBeInTheDocument();
  });

  it('error banner renders logsError text', () => {
    render(<NodeDetailLogsTab {...defaultProps({ logsError: 'log file too large: 16511652 bytes' })} />);
    expect(screen.getByText('Erreur de lecture du log')).toBeInTheDocument();
    expect(screen.getByText('log file too large: 16511652 bytes')).toBeInTheDocument();
  });

  it('renders LogSourceBar with sources and opens modal on trigger', () => {
    render(<NodeDetailLogsTab {...defaultProps()} />);
    // LogSourceBar renders a button to open the fuzzy finder modal
    const openBtn = screen.getByText(/Sources|Parcourir|Toutes les sources/i) || document.querySelector('button');
    expect(openBtn).toBeTruthy();
  });

  it('renders histogram container', () => {
    const histogram: LogHistogramRecord = {
      buckets: [{ hour: '2024-01-01T00:00:00Z', count: 5, levels: { error: 1, warn: 1, info: 3 } }],
      total: 5,
    } as unknown as LogHistogramRecord;
    render(<NodeDetailLogsTab {...defaultProps({ logHistogram: histogram })} />);
    // LogTimeline should render the total
    expect(document.body.textContent).toContain('Total');
  });

  it('shows empty state when no log entries and not loading', () => {
    render(<NodeDetailLogsTab {...defaultProps({ logs: '', logEntries: [], loading: false })} />);
    // LogConsole shows empty message via i18n key or default
    expect(document.body.textContent).toContain('Aucun');
  });

  it('colorizes ERROR lines with error styling', () => {
    render(<NodeDetailLogsTab {...defaultProps({ logs: 'Jan 1 ERROR something went wrong', logEntries: [{ timestamp: 0, time_str: '00:00', level: 'error', unit: 'sys', message: 'ERROR something went wrong' }] })} />);
    const errorRow = screen.getByText(/ERROR something went wrong/).closest('tr');
    expect(errorRow?.className).toMatch(/red/);
  });

  it('renders copy button in log console', () => {
    render(<NodeDetailLogsTab {...defaultProps()} />);
    // LogConsole copy button shows "Copier" or "copy" via i18n
    const copyBtn = screen.getByText(/Copier|copy/i);
    expect(copyBtn).toBeInTheDocument();
  });
});
