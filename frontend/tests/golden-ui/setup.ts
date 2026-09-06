import { test as setup, expect } from '@playwright/test';
import { writeFileSync, mkdirSync } from 'fs';
import path from 'path';

/**
 * One-time demo login (guest/guest) — saves storageState + the first CONNECTED
 * demo node id for the baseline projects. Keeps the test run at ZERO logins so
 * the master's LOGIN_LIMIT (5 req/min/IP) can never trip mid-run.
 */

const AUTH_DIR = path.join(import.meta.dirname, '.auth');

setup('demo login + node id', async ({ request }) => {
  const loginRes = await request.post('/api/auth/login', {
    data: { username: 'guest', password: 'guest' },
  });
  expect(loginRes.ok()).toBeTruthy();
  const loginData = (await loginRes.json()) as { access_token: string; refresh_token: string };
  expect(loginData.access_token).toBeTruthy();

  const meRes = await request.get('/api/auth/me', {
    headers: { Authorization: `Bearer ${loginData.access_token}` },
  });
  expect(meRes.ok()).toBeTruthy();
  const me = (await meRes.json()) as { username: string; role: string; user_id: string };

  const nodesRes = await request.get('/api/nodes', {
    headers: { Authorization: `Bearer ${loginData.access_token}` },
  });
  expect(nodesRes.ok()).toBeTruthy();
  const nodesData = (await nodesRes.json()) as unknown;
  const list = Array.isArray(nodesData)
    ? (nodesData as Array<{ id: string; state?: string }>)
    : ((nodesData as { nodes?: Array<{ id: string; state?: string }> }).nodes ?? []);
  const connected = list.find((n) => n.state === 'CONNECTED');
  const nodeId = connected?.id ?? list[0]?.id ?? '';
  expect(nodeId).toBeTruthy();

  mkdirSync(AUTH_DIR, { recursive: true });
  writeFileSync(
    path.join(AUTH_DIR, 'state.json'),
    JSON.stringify({
      cookies: [],
      origins: [
        {
          origin: 'http://localhost:5173',
          localStorage: [
            { name: 'vigile_access_token', value: loginData.access_token },
            { name: 'vigile_refresh_token', value: loginData.refresh_token },
            { name: 'vigile_user', value: JSON.stringify(me) },
          ],
        },
      ],
    }),
  );
  writeFileSync(path.join(AUTH_DIR, 'node-id.json'), JSON.stringify({ nodeId }));
});