import { t as translate } from '../i18n';

/**
 * Formats a heartbeat timestamp into a human-readable duration since the node went offline.
 * e.g., "3h42", "42m", "2j 5h"
 */
export const formatOfflineDuration = (timestamp: number | null | undefined): string => {
  if (!timestamp) {
    return translate('common.unknown');
  }

  const parsedTime = timestamp < 9999999999 ? timestamp * 1000 : timestamp;
  const now = Date.now();
  const diffMs = now - parsedTime;

  if (diffMs <= 0) {
    return translate('common.just_now');
  }

  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours < 24) {
    return `${hours}h${remainingMinutes.toString().padStart(2, '0')}`;
  }

  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return `${days}j ${remainingHours}h`;
};

/**
 * Formats a Unix timestamp or Date into a human-readable datetime string "JJ/MM à HH:MM".
 * e.g., "12/06 à 14:30"
 */
export const formatUptime = (seconds: number | undefined | null): string => {
  if (seconds === undefined || seconds === null) return '—';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.round(hours)}h`;
  const days = Math.floor(hours / 24);
  const remainingHours = Math.round(hours % 24);
  return `${days}j ${remainingHours}h`;
};

/**
 * Formats a signed duration in seconds into a compact relative label with dynamic units.
 * e.g., -30 → "-30s", -300 → "-5min", -10800 → "-3h", -93600 → "-1j 2h"
 * Used for chart axis ticks / tooltips so long windows don't render as "-300min".
 */
export const formatRelativeDuration = (seconds: number): string => {
  const sign = seconds < 0 ? '-' : '';
  const abs = Math.abs(seconds);
  if (abs < 60) return `${sign}${Math.round(abs)}s`;
  const minutes = Math.floor(abs / 60);
  if (minutes < 60) return `${sign}${minutes}min`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours < 24) {
    return remainingMinutes > 0
      ? `${sign}${hours}h${remainingMinutes.toString().padStart(2, '0')}`
      : `${sign}${hours}h`;
  }
  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return remainingHours > 0 ? `${sign}${days}j ${remainingHours}h` : `${sign}${days}j`;
};

export const formatDateTime = (timestamp: number | null | undefined): string => {
  if (!timestamp) {
    return translate('common.unknown');
  }
  const parsedTime = timestamp < 9999999999 ? timestamp * 1000 : timestamp;
  const date = new Date(parsedTime);
  const pad = (n: number) => String(n).padStart(2, '0');
  const day = pad(date.getDate());
  const month = pad(date.getMonth() + 1);
  const hours = pad(date.getHours());
  const minutes = pad(date.getMinutes());
  return `${day}/${month} à ${hours}:${minutes}`;
};
