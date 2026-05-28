import React, { useMemo } from 'react';

interface NodeTopologyProps {
  nodes: Array<{
    id: string;
    name: string;
    online: boolean;
    state: string;
  }>;
  className?: string;
}

const SVG_W = 500;
const SVG_H = 400;
const CX = SVG_W / 2;
const CY = SVG_H / 2;
const NODE_R = 22;

interface Position {
  x: number;
  y: number;
}

export const NodeTopology: React.FC<NodeTopologyProps> = ({ nodes, className = '' }) => {
  const layout = useMemo<Position[]>(() => {
    if (nodes.length === 0) return [];
    if (nodes.length === 1) return [{ x: CX, y: CY }];

    const radius = Math.min(170, 50 + nodes.length * 20);
    const step = (2 * Math.PI) / nodes.length;

    return nodes.map((_, i) => ({
      x: CX + radius * Math.cos(step * i - Math.PI / 2),
      y: CY + radius * Math.sin(step * i - Math.PI / 2),
    }));
  }, [nodes]);

  if (nodes.length === 0) {
    return (
      <div className={`flex items-center justify-center ${className}`} style={{ minHeight: SVG_H }}>
        <span className="text-xs italic text-ink-muted">Aucun serveur à afficher</span>
      </div>
    );
  }

  return (
    <div className={`relative ${className}`}>
      <svg
        viewBox={`0 0 ${SVG_W} ${SVG_H}`}
        preserveAspectRatio="xMidYMid meet"
        className="w-full h-full select-none"
        style={{ minHeight: SVG_H }}
        role="img"
        aria-label="Topologie des serveurs"
      >
        <defs>
          <filter id="nodeGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <filter id="nodeGlowHover" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="10" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <filter id="hubGlow" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <style>
            {`
              .node-group { transition: opacity 0.25s ease; }
              .node-group:hover .node-body { filter: url(#nodeGlowHover); }
              .node-group:hover .node-dot { fill: #ede7de; }
              .node-dot { transition: fill 0.2s ease; }
            `}
          </style>
        </defs>

        {nodes.length > 1 &&
          layout.map((pos, i) => {
            const next = layout[(i + 1) % nodes.length];
            const aOnline = nodes[i].online;
            const bOnline = nodes[(i + 1) % nodes.length].online;
            const bothOnline = aOnline && bOnline;

            const mx = (pos.x + next.x) / 2;
            const my = (pos.y + next.y) / 2;
            const dx = next.x - pos.x;
            const dy = next.y - pos.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            const bend = Math.min(24, dist * 0.18);
            const cpx = mx - (dy / dist) * bend;
            const cpy = my + (dx / dist) * bend;

            return (
              <path
                key={`edge-${i}`}
                d={`M ${pos.x} ${pos.y} Q ${cpx} ${cpy} ${next.x} ${next.y}`}
                fill="none"
                stroke={bothOnline ? 'rgba(94, 196, 122, 0.2)' : 'rgba(163, 163, 163, 0.1)'}
                strokeWidth={bothOnline ? 1.5 : 1}
                strokeDasharray={bothOnline ? undefined : '3 4'}
                className="transition-colors duration-500"
              />
            );
          })}

        {nodes.length > 1 && (
          <>
            <circle
              cx={CX}
              cy={CY}
              r={3}
              fill="rgba(20, 184, 166, 0.12)"
              filter="url(#hubGlow)"
            />
            <circle
              cx={CX}
              cy={CY}
              r={90}
              fill="none"
              stroke="rgba(200, 180, 160, 0.03)"
              strokeWidth={0.5}
            />
            <circle
              cx={CX}
              cy={CY}
              r={160}
              fill="none"
              stroke="rgba(200, 180, 160, 0.02)"
              strokeWidth={0.5}
            />
          </>
        )}

        {nodes.length === 1 && (
          <>
            <circle
              cx={CX}
              cy={CY}
              r={70}
              fill="none"
              stroke="rgba(94, 196, 122, 0.08)"
              strokeWidth={1}
              strokeDasharray="4 6"
            >
              <animateTransform
                attributeName="transform"
                type="rotate"
                from={`0 ${CX} ${CY}`}
                to={`360 ${CX} ${CY}`}
                dur="10s"
                repeatCount="indefinite"
              />
            </circle>
            <circle
              cx={CX}
              cy={CY}
              r={50}
              fill="none"
              stroke="rgba(20, 184, 166, 0.06)"
              strokeWidth={0.5}
              strokeDasharray="2 8"
            >
              <animateTransform
                attributeName="transform"
                type="rotate"
                from={`360 ${CX} ${CY}`}
                to={`0 ${CX} ${CY}`}
                dur="14s"
                repeatCount="indefinite"
              />
            </circle>
          </>
        )}

        {layout.map((pos, i) => {
          const node = nodes[i];
          const online = node.online;

          return (
            <g key={node.id} className="node-group">
              <title>{`${node.name} · ${node.state}`}</title>

              {online && (
                <circle
                  cx={pos.x}
                  cy={pos.y}
                  r={NODE_R + 10}
                  fill="rgba(94, 196, 122, 0.04)"
                  className="pointer-events-none"
                >
                  <animate
                    attributeName="r"
                    values={`${NODE_R + 8};${NODE_R + 14};${NODE_R + 8}`}
                    dur="3s"
                    repeatCount="indefinite"
                  />
                  <animate
                    attributeName="opacity"
                    values="0.6;0.2;0.6"
                    dur="3s"
                    repeatCount="indefinite"
                  />
                </circle>
              )}

              <circle
                cx={pos.x}
                cy={pos.y}
                r={NODE_R}
                className="node-body"
                fill={online ? '#5ec47a' : '#2a2a2e'}
                filter={online ? 'url(#nodeGlow)' : undefined}
                stroke={online ? 'rgba(94, 196, 122, 0.5)' : 'rgba(163, 163, 163, 0.15)'}
                strokeWidth={online ? 1.5 : 1}
                style={{ cursor: online ? 'pointer' : 'default' }}
              />

              <circle
                cx={pos.x}
                cy={pos.y}
                r={5}
                className="node-dot"
                fill={online ? '#ffffff' : '#555558'}
              />

              <text
                x={pos.x}
                y={pos.y + NODE_R + 18}
                textAnchor="middle"
                fill={online ? '#ede7de' : '#95897c'}
                fontSize={10}
                fontFamily="JetBrains Mono, monospace"
                fontWeight={700}
                className="pointer-events-none"
              >
                {node.name.length > 14 ? `${node.name.slice(0, 12)}..` : node.name}
              </text>

              <text
                x={pos.x}
                y={pos.y + NODE_R + 32}
                textAnchor="middle"
                fill={online ? 'rgba(94, 196, 122, 0.5)' : '#666668'}
                fontSize={7}
                fontFamily="JetBrains Mono, monospace"
                fontWeight={600}
                className="pointer-events-none"
              >
                {node.state.toLowerCase()}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
};
