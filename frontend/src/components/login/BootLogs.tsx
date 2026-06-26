import React, { useEffect, useRef, useState } from 'react';
import { Terminal as TerminalIcon } from 'lucide-react';
import { useLocale } from '../../i18n';
import { usePolling } from '../../hooks/usePolling';

const BOOT_LOG_LINES = [
  'SECURE MANAGER: Cryptography layer loaded (Ed25519 standard).',
  'DATABASE: aiosqlite pool initialized.',
  'AUDIT: Append-only hash chain checked. Integrity validated.',
  'WEBSOCKET: join listener configured on port 8000.',
  'NODE MANAGER: Loading active worker inventory...',
  'SYSTEM: 3 nodes loaded. Health checks resolved.',
  'PLUGINS: metric snapshot scanning active (60s tick).',
  'RATE LIMITER: Sliding window setup initialized.',
  'LLM INTEGRITY: Custom OpenAI complete client active.',
  'SYSTEM: challenge response handshake initialized.',
];

const MAX_LOG_LINES = 15;
const INITIAL_LOG_LINES = 6;
const POLL_INTERVAL_MS = 4500;
const LOG_TIMING_OFFSET_MS = 3000;

const colorForLine = (log: string): string => {
  if (log.includes('SECURE') || log.includes('AUDIT') || log.includes('Integrity')) {
    return 'text-accent';
  }
  if (log.includes('validated') || log.includes('initialized') || log.includes('loaded')) {
    return 'text-severity-ok';
  }
  return 'text-text-3';
};

export const BootLogs: React.FC = () => {
  const { t } = useLocale();
  const [logs, setLogs] = useState<string[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const initial = BOOT_LOG_LINES.slice(0, INITIAL_LOG_LINES).map((log, i) => {
      const ts = new Date(Date.now() - (INITIAL_LOG_LINES - i) * LOG_TIMING_OFFSET_MS).toLocaleTimeString();
      return `[${ts}] ${log}`;
    });
    setLogs(initial);
  }, []);

  usePolling('login_boot_logs_tick', () => {
    setLogs((prev) => {
      const next = BOOT_LOG_LINES[Math.floor(Math.random() * BOOT_LOG_LINES.length)];
      const ts = new Date().toLocaleTimeString();
      const full = `[${ts}] ${next}`;
      const update = [...prev, full];
      if (update.length > MAX_LOG_LINES) update.shift();
      return update;
    });
  }, POLL_INTERVAL_MS);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [logs]);

  return (
    <div className="font-mono text-[11px] text-text-3 leading-relaxed p-4 bg-black/40 border border-border rounded-lg h-44 overflow-hidden flex flex-col justify-end relative shadow-inner">
      <div className="absolute top-2 left-3 flex items-center gap-1.5 text-[8px] text-text-3 uppercase tracking-wider font-semibold pointer-events-none select-none">
        <TerminalIcon className="w-3 h-3 text-accent animate-pulse" />
        <span>{t('login.boot_logs_title')}</span>
      </div>
      <div ref={ref} className="overflow-y-auto max-h-[140px] space-y-1 pr-1 no-scrollbar">
        {logs.map((log, i) => (
          <div key={i} className={colorForLine(log)}>
            {log}
          </div>
        ))}
      </div>
    </div>
  );
};
