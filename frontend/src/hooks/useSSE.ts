import { useState, useRef, useCallback } from 'react';
import { useAuthStore } from '../store/authStore';
import { useLocaleStore } from '../store/localeStore';

export function useSSE() {
  const [streaming, setStreaming] = useState(false);
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const disconnect = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    if (readerRef.current) {
      readerRef.current.cancel().catch(() => {});
      readerRef.current = null;
    }
    setStreaming(false);
  }, []);

  const connect = useCallback(async (
    url: string,
    body: object,
    onEvent: (event: { type: string; [key: string]: any }) => void,
    onDone?: () => void,
    onError?: (err: Error) => void,
    readTimeoutMs: number = 60000
  ) => {
    disconnect();
    setStreaming(true);

    const token = useAuthStore.getState().accessToken;
    const locale = useLocaleStore.getState().locale || 'fr';
    const controller = new AbortController();
    controllerRef.current = controller;
    const connectionTimeout = window.setTimeout(() => controller.abort(), 30000);

    try {
      const response = await fetch(url, {
        method: 'POST',
        credentials: 'include',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
          'Accept-Language': locale,
        },
        body: JSON.stringify(body),
      });

      window.clearTimeout(connectionTimeout);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('Streaming not supported by browser/server response');
      }

      readerRef.current = reader;
      const decoder = new TextDecoder();
      let buffer = '';

      let value: Uint8Array | undefined;
      let done = false;
      while (true) {
        let perReadTimeout: number | null = null;
        try {
          perReadTimeout = window.setTimeout(() => controller.abort(), readTimeoutMs);
          const result = await reader.read();
          value = result.value;
          done = result.done;
          window.clearTimeout(perReadTimeout);
          perReadTimeout = null;
          if (done) break;
        } finally {
          if (perReadTimeout !== null) {
            window.clearTimeout(perReadTimeout);
          }
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data:')) continue;

          try {
            const rawJson = trimmed.substring(5).trim();
            if (!rawJson) continue;
            const data = JSON.parse(rawJson);
            onEvent(data);
          } catch {
            // Ignore parse errors on partial streams
          }
        }
      }
      if (onDone) onDone();
    } catch (err: any) {
      console.error('SSE Stream error:', err);
      if (onError) onError(err);
    } finally {
      window.clearTimeout(connectionTimeout);
      setStreaming(false);
      readerRef.current = null;
      controllerRef.current = null;
    }
  }, [disconnect]);

  return {
    connect,
    disconnect,
    streaming,
  };
}
