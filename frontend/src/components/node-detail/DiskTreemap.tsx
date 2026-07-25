import React, { useMemo, useRef, useEffect, useState, useCallback } from 'react';
import { hierarchy, treemap, treemapSquarify } from 'd3-hierarchy';
import type { HierarchyRectangularNode } from 'd3-hierarchy';
import type { DiskNode } from '../../types/disk';

interface DiskTreemapProps {
  root: DiskNode;
  onDrill: (path: string) => void;
}

const COLORS = [
  '#f59e0b', '#f97316', '#ef4444', '#eab308', '#84cc16',
  '#22c55e', '#14b8a6', '#06b6d4', '#3b82f6', '#8b5cf6',
  '#a855f7', '#ec4899', '#f43f5e', '#fb923c', '#fbbf24',
];

const GHOST_COLOR = '#4b5563';
const MIN_LABEL_WIDTH = 40;
const MIN_LABEL_HEIGHT = 20;

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const value = bytes / Math.pow(1024, i);
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[i]}`;
}

function getColor(index: number, total: number): string {
  if (total <= 1) return COLORS[0];
  return COLORS[index % COLORS.length];
}

function isGhost(d: HierarchyRectangularNode<DiskNode>): boolean {
  return d.data.name.includes('(small)') || d.data.name.includes('(others)');
}

export const DiskTreemap: React.FC<DiskTreemapProps> = ({ root, onDrill }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 600, height: 400 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        const { width } = entry.contentRect;
        setDimensions({ width: Math.max(width, 200), height: Math.max(Math.round(width * 0.55), 200) });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const nodes = useMemo(() => {
    if (!root || root.size === 0) return [];
    const rootDatum = hierarchy(root)
      .sum((d) => (d.is_dir ? 0 : d.size))
      .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
    const laid = treemap<DiskNode>()
      .tile(treemapSquarify)
      .size([dimensions.width, dimensions.height])
      .padding(1)(rootDatum);
    return laid.leaves() as HierarchyRectangularNode<DiskNode>[];
  }, [root, dimensions.width, dimensions.height]);

  const handleDrill = useCallback(
    (path: string) => {
      onDrill(path);
    },
    [onDrill],
  );

  if (!root || root.size === 0 || nodes.length === 0) {
    return (
      <div className="py-12 text-center text-text-3 text-xs bg-surface/20 border border-border rounded-lg">
        No data to display
      </div>
    );
  }

  return (
    <div ref={containerRef} className="w-full">
      <svg
        width={dimensions.width}
        height={dimensions.height}
        className="w-full h-auto border border-border rounded-lg overflow-hidden bg-surface"
      >
        {nodes.map((d, i) => {
          const w = d.x1 - d.x0;
          const h = d.y1 - d.y0;
          const ghost = isGhost(d);
          const fill = ghost ? GHOST_COLOR : getColor(i, nodes.length);
          const isClickable = d.data.is_dir && !ghost;
          return (
            <g key={d.data.path}>
              <rect
                x={d.x0}
                y={d.y0}
                width={w}
                height={h}
                fill={fill}
                fillOpacity={ghost ? 0.3 : 0.75}
                stroke="var(--color-surface, #1e1e2e)"
                strokeWidth={1}
                rx={2}
                className={isClickable ? 'cursor-pointer' : ''}
                onClick={isClickable ? () => handleDrill(d.data.path) : undefined}
              />
              {w >= MIN_LABEL_WIDTH && h >= MIN_LABEL_HEIGHT && (
                <text
                  x={d.x0 + 4}
                  y={d.y0 + 14}
                  fill={ghost ? '#9ca3af' : '#f3f4f6'}
                  fontSize={10}
                  fontFamily="var(--font-interface, monospace)"
                  className={isClickable ? 'cursor-pointer pointer-events-auto' : 'pointer-events-none'}
                  onClick={isClickable ? () => handleDrill(d.data.path) : undefined}
                >
                  {d.data.name}
                </text>
              )}
              {w >= MIN_LABEL_WIDTH && h >= 34 && (
                <text
                  x={d.x0 + 4}
                  y={d.y0 + 26}
                  fill={ghost ? '#6b7280' : '#d1d5db'}
                  fontSize={9}
                  fontFamily="var(--font-mono, monospace)"
                  className="pointer-events-none"
                >
                  {formatBytes(d.value ?? 0)}
                </text>
              )}
              <title>
                {d.data.name}
                {'\n'}
                {formatBytes(d.value ?? 0)}
                {ghost ? '\n(grouped small files)' : d.data.is_dir ? '\n(directory)' : ''}
              </title>
            </g>
          );
        })}
      </svg>
    </div>
  );
};
