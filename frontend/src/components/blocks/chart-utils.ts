/* ── Formatters for ChartCard ─────────────────────────────────────────── */

export function formatXAxis(tickItem: number, period: string): string {
  const d = new Date(tickItem * 1000);
  if (period === '1h' || period === '6h') {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit' });
}

export function formatTooltipDate(label: unknown): string {
  return new Date(Number(label) * 1000).toLocaleString();
}
