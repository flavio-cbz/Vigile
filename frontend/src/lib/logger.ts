type LogLevel = 'debug' | 'info' | 'warn' | 'error';
const LOG_LEVELS: Record<LogLevel, number> = { debug: 0, info: 1, warn: 2, error: 3 };
const currentLevel: LogLevel = (import.meta.env.VITE_LOG_LEVEL as LogLevel) || 'warn';

export const logger = {
  debug: (...args: unknown[]) => { if (LOG_LEVELS[currentLevel] <= 0) console.debug('[vigile]', ...args); },
  info: (...args: unknown[]) => { if (LOG_LEVELS[currentLevel] <= 1) console.info('[vigile]', ...args); },
  warn: (...args: unknown[]) => { if (LOG_LEVELS[currentLevel] <= 2) console.warn('[vigile]', ...args); },
  error: (...args: unknown[]) => { if (LOG_LEVELS[currentLevel] <= 3) console.error('[vigile]', ...args); },
};
