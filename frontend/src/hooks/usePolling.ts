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
  const wrapperRef = useRef<(() => void) | null>(null);

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

    // Stable wrapper created once per component instance for correct StrictMode cleanup
    if (wrapperRef.current === null) {
      wrapperRef.current = () => {
        void runCallback();
      };
    }
    const wrapper = wrapperRef.current;
    callbacks.add(wrapper);

    if (!activeIntervals.has(key)) {
      void runCallback();
      const id = setInterval(() => {
        const currentCallbacks = activeCallbacks.get(key);
        if (currentCallbacks && currentCallbacks.size > 0) {
          currentCallbacks.forEach(cb => cb());
        }
      }, intervalMs);
      activeIntervals.set(key, id);
      if (import.meta.env.DEV) console.debug(`[usePolling] ${key}: interval started (${activeIntervals.size} active)`);
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
            if (import.meta.env.DEV) console.debug(`[usePolling] ${key}: interval cleaned (${activeIntervals.size} remaining)`);
            if (import.meta.env.DEV && activeIntervals.size > 20) {
              console.warn(`[usePolling] ${key}: WARNING - ${activeIntervals.size} active intervals (possible leak)`);
            }
          }
          activeRuns.delete(key);
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, intervalMs, enabled]);
}
