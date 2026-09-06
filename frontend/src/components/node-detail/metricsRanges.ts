export type TimeRangePreset = '1h' | '6h' | '12h' | '24h' | '7d' | '30d' | 'custom';

export const TIME_RANGE_PRESETS = ['1h', '6h', '12h', '24h', '7d', '30d'] as const;

export type SelectableTimeRangePreset = (typeof TIME_RANGE_PRESETS)[number];

export const TIME_RANGE_DURATIONS_SEC: Record<SelectableTimeRangePreset, number> = {
  '1h': 3600,
  '6h': 21600,
  '12h': 43200,
  '24h': 86400,
  '7d': 604800,
  '30d': 2592000,
};

export interface CustomRangeSeconds {
  start: number;
  end: number;
}

export function isSelectableTimeRangePreset(value: unknown): value is SelectableTimeRangePreset {
  return typeof value === 'string' && (TIME_RANGE_PRESETS as readonly string[]).includes(value);
}

export function isTimeRangePreset(value: unknown): value is TimeRangePreset {
  return isSelectableTimeRangePreset(value) || value === 'custom';
}

export function sanitizeCustomRangeSeconds(value: unknown): CustomRangeSeconds | null {
  if (!value || typeof value !== 'object') return null;
  const { start, end } = value as { start?: unknown; end?: unknown };
  if (
    typeof start !== 'number' || !Number.isFinite(start) || start <= 0 ||
    typeof end !== 'number' || !Number.isFinite(end) || end <= start
  ) {
    return null;
  }
  return { start, end };
}
