import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ChartCard, formatXAxis, formatTooltipDate } from './ChartCard';
import type { ChartCardConfig } from './ChartCard';

// Mock recharts ResponsiveContainer to avoid jsdom layout issues
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container">{children}</div>
    ),
  };
});

const baseConfig: ChartCardConfig = {
  title: 'Utilisation du Processeur (CPU)',
  dataKey: 'cpu_percent',
  color: '#f97316',
  gradientId: 'cpuColor',
  period: '24h',
};

const sampleData = [
  { node_id: 'n1', collected_at: 1700000000, cpu_percent: 45, mem_percent: 60, disk_percent: 30 },
  { node_id: 'n1', collected_at: 1700000600, cpu_percent: 50, mem_percent: 62, disk_percent: 31 },
  { node_id: 'n1', collected_at: 1700001200, cpu_percent: 35, mem_percent: 58, disk_percent: 32 },
];

describe('ChartCard — formatXAxis', () => {
  it('formats as time-only for 1h period (no month)', () => {
    const result = formatXAxis(1700000000, '1h');
    expect(result).not.toMatch(/jan|fév|mar|avr|mai|jun|jul|aoû|sep|oct|nov|déc/i);
  });

  it('formats as time-only for 6h period (no month)', () => {
    const result = formatXAxis(1700000000, '6h');
    expect(result).not.toMatch(/jan|fév|mar|avr|mai|jun|jul|aoû|sep|oct|nov|déc/i);
  });

  it('formats as date+time for 24h period (includes month)', () => {
    const result = formatXAxis(1700000000, '24h');
    const shortResult = formatXAxis(1700000000, '1h');
    expect(result.length).toBeGreaterThan(shortResult.length);
    expect(result).not.toBe(shortResult);
  });

  it('formats as date+time for 7d period (includes month)', () => {
    const result = formatXAxis(1700000000, '7d');
    const shortResult = formatXAxis(1700000000, '6h');
    expect(result.length).toBeGreaterThan(shortResult.length);
    expect(result).not.toBe(shortResult);
  });
});

describe('ChartCard — formatTooltipDate', () => {
  it('formats a unix timestamp to locale string', () => {
    const result = formatTooltipDate(1700000000);
    expect(typeof result).toBe('string');
    expect(result.length).toBeGreaterThan(0);
  });

  it('handles numeric string input', () => {
    const result = formatTooltipDate('1700000000');
    expect(typeof result).toBe('string');
    expect(result.length).toBeGreaterThan(0);
  });
});

describe('ChartCard — busy state', () => {
  it('renders spinner with orange border token', () => {
    render(
      <ChartCard
        context={{}}
        config={baseConfig}
        state="busy"
        data={[]}
      />,
    );
    const spinner = screen.getByRole('status');
    expect(spinner.className).toContain('border-t-2');
    expect(spinner.className).toContain('border-orange-500');
  });

  it('renders loading text in French', () => {
    render(
      <ChartCard
        context={{}}
        config={baseConfig}
        state="busy"
        data={[]}
      />,
    );
    expect(screen.getByText(/chargement/i)).toBeInTheDocument();
  });
});

describe('ChartCard — empty state', () => {
  it('renders the exact French empty string from contract §2', () => {
    render(
      <ChartCard
        context={{}}
        config={baseConfig}
        state="empty"
        data={[]}
      />,
    );
    expect(screen.getByText('Aucune métrique enregistrée')).toBeInTheDocument();
  });

  it('renders an AlertCircle icon', () => {
    const { container } = render(
      <ChartCard
        context={{}}
        config={baseConfig}
        state="empty"
        data={[]}
      />,
    );
    // AlertCircle from lucide-react renders an SVG
    const svgIcons = container.querySelectorAll('svg');
    expect(svgIcons.length).toBeGreaterThan(0);
  });
});

describe('ChartCard — error state', () => {
  it('renders error message', () => {
    render(
      <ChartCard
        context={{}}
        config={baseConfig}
        state="error"
        data={[]}
        error="Connection failed"
      />,
    );
    expect(screen.getByText('Connection failed')).toBeInTheDocument();
  });

  it('renders retry button when onRetry is provided', () => {
    const onRetry = vi.fn();
    render(
      <ChartCard
        context={{}}
        config={baseConfig}
        state="error"
        data={[]}
        error="Timeout"
        onRetry={onRetry}
      />,
    );
    const retryBtn = screen.getByRole('button', { name: /réessayer/i });
    fireEvent.click(retryBtn);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('does not render retry button when onRetry is absent', () => {
    render(
      <ChartCard
        context={{}}
        config={baseConfig}
        state="error"
        data={[]}
        error="Timeout"
      />,
    );
    expect(screen.queryByRole('button', { name: /réessayer/i })).not.toBeInTheDocument();
  });
});

describe('ChartCard — idle state', () => {
  it('renders a placeholder', () => {
    const { container } = render(
      <ChartCard
        context={{}}
        config={baseConfig}
        state="idle"
        data={[]}
      />,
    );
    // Should render something (placeholder skeleton)
    expect(container.firstChild).toBeTruthy();
    // Should NOT show chart content
    expect(screen.queryByText(baseConfig.title)).not.toBeInTheDocument();
  });
});

describe('ChartCard — data state', () => {
  it('renders the chart title from config', () => {
    render(
      <ChartCard
        context={{}}
        config={baseConfig}
        state="data"
        data={sampleData}
      />,
    );
    expect(screen.getByText('Utilisation du Processeur (CPU)')).toBeInTheDocument();
  });

  it('renders ResponsiveContainer with chart wrapper', () => {
    const { container } = render(
      <ChartCard
        context={{}}
        config={baseConfig}
        state="data"
        data={sampleData}
      />,
    );
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    const wrapper = container.querySelector('.rounded-xl.border');
    expect(wrapper).toBeTruthy();
  });

  it('renders chart with configured height class', () => {
    const { container } = render(
      <ChartCard
        context={{}}
        config={baseConfig}
        state="data"
        data={sampleData}
      />,
    );
    const heightDiv = container.querySelector('.h-64');
    expect(heightDiv).toBeTruthy();
  });

  it('renders Activity icon with configured color', () => {
    const { container } = render(
      <ChartCard
        context={{}}
        config={baseConfig}
        state="data"
        data={sampleData}
      />,
    );
    const icon = container.querySelector('svg.text-orange-500, svg[style*="color"]');
    expect(icon).toBeTruthy();
  });
});
