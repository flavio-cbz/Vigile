import { lazy } from 'react';
import type { BlockComponent } from './types';

/**
 * Block component registry. The BlockRenderer dispatches on `config.type`
 * against this registry (fail-closed: an unknown type renders an error card,
 * never a blank page).
 *
 * Kept in its own module so BlockRenderer.tsx only exports components
 * (react-refresh/only-export-components).
 */

const registry = new Map<string, BlockComponent>();

/**
 * Registers a block component under its `config.type` key.
 */
export function registerBlock(type: string, component: BlockComponent): void {
  registry.set(type, component);
}

/**
 * Resolves a block component by type. Returns undefined for unregistered types.
 */
export function getBlockComponent(type: string): BlockComponent | undefined {
  return registry.get(type);
}

function normalizeBlockModule(mod: Record<string, unknown>, name: string): { default: BlockComponent } {
  const component = (mod.default ?? mod[name]) as BlockComponent;
  return { default: component };
}

/**
 * Lazy-registers a planned block component.
 * Accepts either a default or a named export matching the file name
 * (e.g. ExternalAuthPopup has no default export).
 */
function lazyBlock(name: string, importer: () => Promise<Record<string, unknown>>): BlockComponent {
  return lazy(() => importer().then((mod) => normalizeBlockModule(mod, name)));
}

// Landed block components (static imports, fully analyzed):
registerBlock('chart-card', lazyBlock('ChartCard', () => import('./ChartCard')));
registerBlock('data-table', lazyBlock('DataTable', () => import('./DataTable')));
registerBlock('status-pill', lazyBlock('StatusPill', () => import('./StatusPill')));
registerBlock('action-button-row', lazyBlock('ActionButtonRow', () => import('./ActionButtonRow')));
registerBlock('external-auth-popup', lazyBlock('ExternalAuthPopup', () => import('./ExternalAuthPopup')));

// Rest of the block catalog (files landed during J2-T8..T12, promoted from
// template `pending()` imports to static lazy imports — same block types).
registerBlock('tabs', lazyBlock('Tabs', () => import('./Tabs')));
registerBlock('list-card', lazyBlock('ListCard', () => import('./ListCard')));
registerBlock('banner', lazyBlock('Banner', () => import('./Banner')));
registerBlock('metric-cards-grid', lazyBlock('MetricCardsGrid', () => import('./MetricCardsGrid')));
registerBlock('node-selector', lazyBlock('NodeSelector', () => import('./NodeSelector')));
registerBlock('filter-panel', lazyBlock('FilterPanel', () => import('./FilterPanel')));
registerBlock('page-header', lazyBlock('PageHeader', () => import('./PageHeader')));