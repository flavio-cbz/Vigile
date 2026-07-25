import { useEffect, useRef } from 'react';

const activeCallbacks = new Map<string, Set<() => void>>();
const activeIntervals = new Map<string, ReturnType<typeof setInterval>>();
const activeRuns = new Map<string, boolean>();

export function usePolling(
  key: string,
  callback: () => void | Promise<void>,
  intervalMs: number,
  enabled = true,
) {
  const savedCallback = useRef(callback);

  useEffect(() => {
    savedCallback.current = callback;
  });

  const runCallback = async () => {
    if (activeRuns.get(key)) return;

    activeRuns.set(key, true);
    try {
      await Promise.resolve(savedCallback.current());
    } finally {
      activeRuns.set(key, false);
    }
  };

  useEffect(() => {
    if (!enabled) return;

    if (!activeCallbacks.has(key)) {
      activeCallbacks.set(key, new Set());
    }
    const callbacks = activeCallbacks.get(key)!;

    // Wrapper local qui pointe vers le callback à jour à chaque render
    const wrapper = () => {
      void runCallback();
    };
    callbacks.add(wrapper);

    if (!activeIntervals.has(key)) {
      void runCallback();
      const id = setInterval(() => {
        const currentCallbacks = activeCallbacks.get(key);
        if (currentCallbacks) {
          currentCallbacks.forEach(cb => cb());
        }
      }, intervalMs);
      activeIntervals.set(key, id);
    }

    return () => {
      const currentCallbacks = activeCallbacks.get(key);
      if (currentCallbacks) {
        currentCallbacks.delete(wrapper);
        if (currentCallbacks.size === 0) {
          activeCallbacks.delete(key);
          const id = activeIntervals.get(key);
          if (id) {
            clearInterval(id);
            activeIntervals.delete(key);
          }
          activeRuns.delete(key);
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, intervalMs, enabled]);
}
