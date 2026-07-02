import { useEffect, useState } from 'react';

interface VersionResponse {
  version: string;
}

export function useVersion(): string | null {
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetch('/api/version', { credentials: 'include' })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: VersionResponse | null) => {
        if (!cancelled && data?.version) {
          setVersion(data.version);
        }
      })
      .catch(() => {
        // Footer version is non-critical; fail silently.
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return version;
}
