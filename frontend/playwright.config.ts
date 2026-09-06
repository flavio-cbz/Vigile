import { defineConfig, devices } from '@playwright/test';

/**
 * Golden UI baseline captures — J1 gate.
 *
 * Targets the Vite dev server (http://localhost:5173) which proxies /api and /ws
 * to the Master (127.0.0.1:8003, demo mode — see frontend/.env.local). The dev
 * server reflects the CURRENT source, unlike master/static/ which holds the last
 * compiled build.
 *
 * The setup project performs the single demo login (guest/guest) and saves a
 * storageState consumed by the viewport projects — the test run itself performs
 * ZERO logins, so the master's LOGIN_LIMIT (5 req/min/IP) can never trip.
 *
 * Baseline screenshots are written to tests/golden-ui/baselines/ with the naming
 * convention {page}_{theme}_{viewport}.png (viewport = project name).
 */
export default defineConfig({
  testDir: './tests/golden-ui',
  timeout: 60_000,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [['list']],
  outputDir: 'tests/golden-ui/baselines',
  use: {
    baseURL: 'http://localhost:5173',
    screenshot: 'on',
    trace: 'off',
    video: 'off',
  },
  projects: [
    {
      name: 'setup',
      testMatch: /setup\.ts/,
    },
    {
      name: '1440x900',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
        storageState: 'tests/golden-ui/.auth/state.json',
      },
      dependencies: ['setup'],
    },
    {
      name: '768x1024',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 768, height: 1024 },
        storageState: 'tests/golden-ui/.auth/state.json',
      },
      dependencies: ['setup'],
    },
    {
      name: '375x812',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 375, height: 812 },
        storageState: 'tests/golden-ui/.auth/state.json',
      },
      dependencies: ['setup'],
    },
  ],
});