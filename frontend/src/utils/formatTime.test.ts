// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { formatRelativeDuration, formatAgo } from './formatTime';

describe('formatRelativeDuration', () => {
  it('formats seconds', () => {
    expect(formatRelativeDuration(-30)).toBe('-30s');
    expect(formatRelativeDuration(0)).toBe('0s');
  });

  it('formats minutes below one hour', () => {
    expect(formatRelativeDuration(-300)).toBe('-5min');
    expect(formatRelativeDuration(59 * 60 + 30)).toBe('59min');
  });

  it('formats hours below one day', () => {
    expect(formatRelativeDuration(-10800)).toBe('-3h');
    expect(formatRelativeDuration(-3 * 3600 - 30 * 60)).toBe('-3h30');
  });

  it('formats days for long windows', () => {
    expect(formatRelativeDuration(-93600)).toBe('-1j 2h');
    expect(formatRelativeDuration(-172800)).toBe('-2j');
  });
});

describe('formatAgo', () => {
  it('returns jamais for null or undefined', () => {
    expect(formatAgo(null)).toBe('jamais');
    expect(formatAgo(undefined)).toBe('jamais');
  });

  it('formats seconds', () => {
    const nowSec = Math.floor(Date.now() / 1000);
    expect(formatAgo(nowSec - 15)).toBe('il y a 15s');
    expect(formatAgo(nowSec)).toBe('il y a 0s');
  });

  it('formats minutes and seconds', () => {
    const nowSec = Math.floor(Date.now() / 1000);
    expect(formatAgo(nowSec - 135)).toBe('il y a 2m 15s');
  });

  it('formats hours and minutes', () => {
    const nowSec = Math.floor(Date.now() / 1000);
    expect(formatAgo(nowSec - 3665)).toBe('il y a 1h 1m');
  });

  it('formats days', () => {
    const nowSec = Math.floor(Date.now() / 1000);
    expect(formatAgo(nowSec - 90000)).toBe('il y a 1j');
  });
});

