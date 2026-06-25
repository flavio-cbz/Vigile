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
