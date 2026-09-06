import '@testing-library/jest-dom/vitest';

class LocalStorageMock {
  private store: Record<string, string> = {};

  get length() {
    return Object.keys(this.store).length;
  }

  clear() {
    this.store = {};
  }

  getItem(key: string) {
    return this.store[key] || null;
  }

  setItem(key: string, value: string) {
    this.store[key] = String(value);
  }

  removeItem(key: string) {
    delete this.store[key];
  }

  key(index: number) {
    const keys = Object.keys(this.store);
    return keys[index] || null;
  }
}

Object.defineProperty(globalThis, 'localStorage', {
  value: new LocalStorageMock(),
  configurable: true,
  writable: true,
});

class MockEventSource {
  url: string;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private listeners = new Map<string, Array<(ev: Event) => void>>();

  constructor(url: string) {
    this.url = url;
  }

  addEventListener(type: string, listener: (ev: Event) => void): void {
    const list = this.listeners.get(type) ?? [];
    list.push(listener);
    this.listeners.set(type, list);
  }

  removeEventListener(type: string, listener: (ev: Event) => void): void {
    const list = this.listeners.get(type);
    if (list) {
      this.listeners.set(type, list.filter((l) => l !== listener));
    }
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, data: unknown): void {
    const event = new MessageEvent(type, { data: JSON.stringify(data) });
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }
}

(globalThis as unknown as { EventSource: typeof MockEventSource }).EventSource = MockEventSource;
