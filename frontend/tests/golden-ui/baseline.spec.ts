import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'fs';
import path from 'path';

/**
 * Golden UI baseline captures — J1 gate (pre-migration reference).
 *
 * Matrix: 7 pages × 4 themes × 3 viewports (projects) = 84 screenshots.
 * Themes come from src/design/themes.ts: warm-dark (default), cool-dark,
 * gray-dark, light. Viewports come from the Playwright projects.
 *
 * Auth: demo mode (guest/guest) — the setup project logs in ONCE and saves a
 * storageState consumed by all viewport projects; the auth store reads
 * localStorage at module init. The login page itself is captured unauthenticated.
 *
 * Naming: {page}_{theme}_{viewport}.png in tests/golden-ui/baselines/.
 */

const THEMES = ['warm-dark', 'cool-dark', 'gray-dark', 'light'] as const;

interface PageDef {
  name: string;
  path: string; // '{id}' is replaced with the first CONNECTED demo node id
  waitFor: string; // selector proving the page mounted
  settleMs: number; // extra settle time for async data / chart animations
}

const PAGES: PageDef[] = [
  { name: 'login', path: '/login', waitFor: 'form', settleMs: 1500 },
  { name: 'dashboard', path: '/', waitFor: 'nav', settleMs: 3000 },
  { name: 'nodes-list', path: '/servers', waitFor: 'nav', settleMs: 3000 },
  { name: 'node-containers', path: '/nodes/{id}?tab=containers', waitFor: 'nav', settleMs: 3000 },
  { name: 'node-services', path: '/nodes/{id}?tab=services', waitFor: 'nav', settleMs: 3000 },
  { name: 'metrics-history', path: '/nodes/{id}?tab=metrics', waitFor: 'nav', settleMs: 3000 },
  { name: 'plex-admin', path: '/plugins/plex', waitFor: 'nav', settleMs: 3000 },
];

let nodeId: string;

test.beforeAll(() => {
  const { nodeId: cachedNodeId } = JSON.parse(
    readFileSync(path.join(import.meta.dirname, '.auth', 'node-id.json'), 'utf8'),
  ) as { nodeId: string };
  nodeId = cachedNodeId;
  expect(nodeId).toBeTruthy();
});

async function seedContext(page: Page, theme: string): Promise<void> {
  await page.addInitScript(
    ({ themeName }) => {
      localStorage.setItem('vigile_theme', themeName);
      // Plex OAuth opens a popup window — stub it so the PIN state is captured
      // without spawning a real browser window.
      window.open = () => null;
    },
    { themeName: theme },
  );
}

async function capturePlexPin(page: Page): Promise<void> {
  // The connect button lives INSIDE the config modal (PlexAdmin.tsx:767-778) —
  // it is never rendered on the page itself. Open the modal first: the header
  // "Configurer Plex" button (admin-gated, always present for the demo admin
  // user) or the banner CTA ("Configurer Plex Maintenant" / "Lier Plex.tv
  // Maintenant") depending on the node's detection state.
  const headerBtn = page.getByRole('button', { name: 'Configurer Plex', exact: true });
  const bannerBtn = page.getByRole('button', { name: /Configurer Plex Maintenant|Lier Plex\.tv Maintenant/ });
  if (await headerBtn.isVisible().catch(() => false)) {
    await headerBtn.click();
  } else {
    await bannerBtn.click();
  }
  await page.getByRole('heading', { name: 'Configuration Plex' }).waitFor({ timeout: 10_000 });

  const connectBtn = page.getByRole('button', { name: /Se connecter avec Plex|Re-connecter Plex/ });
  // At 768x1024 the sidebar's stacking context renders ABOVE the modal (app
  // bug, out of scope for the gate) and intercepts the button's click point.
  // Synthetic click bypasses hit-testing; React's delegated listener still fires.
  await connectBtn.dispatchEvent('click', { bubbles: true, cancelable: true });
  // PIN code element (PlexAdmin.tsx:783): <code class="... text-orange-400 ...">XXXX</code>
  // — the accent class is text-orange-400, NOT text-accent.
  await page.waitForSelector('code.text-orange-400', { timeout: 15_000 });
  await page.waitForTimeout(500);
}

for (const theme of THEMES) {
  for (const pageDef of PAGES) {
    test(`${pageDef.name} — ${theme}`, async ({ page }, testInfo) => {
      const viewport = testInfo.project.name;

      await seedContext(page, theme);

      const path = pageDef.path.replace('{id}', nodeId);
      await page.goto(path);
      await page.waitForLoadState('domcontentloaded');
      await page.waitForSelector(pageDef.waitFor, { timeout: 20_000 });
      await page.waitForTimeout(pageDef.settleMs);

      if (pageDef.name === 'plex-admin') {
        await capturePlexPin(page);
      }

      await page.screenshot({
        path: `tests/golden-ui/baselines/${pageDef.name}_${theme}_${viewport}.png`,
      });
    });
  }
}