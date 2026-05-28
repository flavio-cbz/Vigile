import React from 'react';

export type VigileStatus = 'calm' | 'attentive' | 'alert' | 'critical' | 'dormant';

interface VigileEyeProps {
  /** Fleet health status driving the eye visual */
  status: VigileStatus;
  /** Context label for the aria-label (screen readers, not displayed) */
  context?: 'fleet' | 'server';
  /** Size in px (width & height equal, viewBox is 32×32) */
  size?: number;
  /** Additional class names forwarded to the root <svg> */
  className?: string;
}

const statusConfig: Record<
  VigileStatus,
  { color: string; pupilX: number; pupilScale: number; label: string }
> = {
  calm:      { color: '#5ec47a', pupilX: 0,  pupilScale: 1,   label: 'Serein — tout est opérationnel' },
  attentive: { color: '#d4a850', pupilX: 4,  pupilScale: 1.15, label: 'Attentif — surveillance renforcée' },
  alert:     { color: '#e07070', pupilX: 0,  pupilScale: 1.3,  label: 'Alerte — action requise' },
  critical:  { color: '#e07070', pupilX: 0,  pupilScale: 1.5,  label: 'Critique — intervention nécessaire' },
  dormant:   { color: '#95897c', pupilX: -6, pupilScale: 0.5,  label: 'Inactif — en attente' },
};

/**
 * VigileEye — an SVG eye mascot that reflects fleet / server health.
 *
 * 5 visual states driven entirely by CSS animations:
 * - calm:       gentle 4s pulse    → everything stable
 * - attentive:  pupil scans L/R    → one warning threshold crossed
 * - alert:      faster 1.5s pulse  → multiple warnings
 * - critical:   rapid 0.8s + glow  → panic / offline nodes
 * - dormant:    scaleY(0.15) slit  → no data, waiting
 *
 * Zero external dependencies. ~1.8 KB gzipped.
 * GPU-composited via CSS animations — safe on Raspberry Pi 4 Chromium.
 * Respects `prefers-reduced-motion`.
 */
export const VigileEye: React.FC<VigileEyeProps> = ({
  status,
  context = 'fleet',
  size = 24,
  className = '',
}) => {
  const config = statusConfig[status];
  const isCritical = status === 'critical';
  // status === 'dormant' handled via CSS class `.ve-root--dormant`
  const pupilRadius = 3 * config.pupilScale;

  return (
    <svg
      viewBox="0 0 32 32"
      width={size}
      height={size}
      role="img"
      aria-label={`Vigile — ${config.label} (${context === 'fleet' ? 'vue parc' : 'vue serveur'})`}
      className={`ve-root ve-root--${status}${className ? ' ' + className : ''}`}
    >
      <style>{`
        .ve-root {
          display: block;
          overflow: visible;
        }

        /* ── Eye shape (almond / surveillance camera lens) ── */
        .ve-shape {
          fill: none;
          stroke: ${config.color};
          stroke-width: 1.3;
          stroke-linecap: round;
          stroke-linejoin: round;
          transition: stroke 0.4s ease, stroke-width 0.4s ease;
        }

        /* ── Inner elements ── */
        .ve-inner {
          transition: transform 0.6s cubic-bezier(0.4, 0, 0.2, 1);
          transform-origin: 16px 16px;
        }

        .ve-iris {
          transition: fill 0.4s ease, opacity 0.6s ease;
        }

        .ve-pupil-group {
          transform-origin: 16px 16px;
        }

        .ve-pupil {
          transition: fill 0.4s ease;
        }

        .ve-highlight {
          transition: opacity 0.6s ease;
        }

        .ve-glow-ring {
          transform-origin: 16px 16px;
        }

        /* ================================================
               STATE: CALM
               Gentle breathing pulse, fully open eye.
            ================================================ */
        .ve-root--calm .ve-shape {
          animation: ve-calmPulse 4s ease-in-out infinite;
        }
        @keyframes ve-calmPulse {
          0%, 100% { opacity: 0.6; }
          50%      { opacity: 1; }
        }

        /* ================================================
               STATE: ATTENTIVE
               Pupil slowly scans left-right.
               Slightly elevated iris opacity.
            ================================================ */
        .ve-root--attentive .ve-pupil-group {
          animation: ve-scan 3s ease-in-out infinite;
        }
        @keyframes ve-scan {
          0%, 100% { transform: translateX(-5px); }
          50%      { transform: translateX(5px); }
        }

        .ve-root--attentive .ve-shape {
          animation: ve-attentivePulse 3s ease-in-out infinite;
        }
        @keyframes ve-attentivePulse {
          0%, 100% { opacity: 0.7; }
          50%      { opacity: 1; }
        }

        /* ================================================
               STATE: ALERT
               Faster pulse (1.5s), visible stroke emphasis.
               Pupil is already dilated by pupilScale.
            ================================================ */
        .ve-root--alert .ve-shape {
          animation: ve-alertPulse 1.5s ease-in-out infinite;
        }
        @keyframes ve-alertPulse {
          0%, 100% { opacity: 0.7; stroke-width: 1.3; }
          50%      { opacity: 1;   stroke-width: 1.6; }
        }

        /* ================================================
               STATE: CRITICAL
               Rapid pulse (0.8s) + expanding glow ring.
               Max pupil dilation.
            ================================================ */
        .ve-root--critical .ve-shape {
          animation: ve-criticalPulse 0.8s ease-in-out infinite;
        }
        @keyframes ve-criticalPulse {
          0%, 100% { opacity: 0.7; stroke-width: 1.3; }
          50%      { opacity: 1;   stroke-width: 1.8; }
        }

        .ve-root--critical .ve-glow-ring {
          animation: ve-criticalGlow 0.8s ease-in-out infinite;
        }
        @keyframes ve-criticalGlow {
          0%, 100% { opacity: 0.1; transform: scale(1); }
          50%      { opacity: 0.35; transform: scale(1.12); }
        }

        /* ================================================
               STATE: DORMANT
               Eye collapses to a near-closed slit (scaleY 0.15).
               Low opacity, muted colors, no motion.
            ================================================ */
        .ve-root--dormant .ve-inner {
          transform: scaleY(0.15);
        }
        .ve-root--dormant .ve-shape {
          stroke-width: 2;
          stroke-opacity: 0.35;
        }
        .ve-root--dormant .ve-iris {
          opacity: 0.2;
        }
        .ve-root--dormant .ve-highlight {
          opacity: 0.1;
        }

        /* ================================================
               ACCESSIBILITY: prefers-reduced-motion
               Kill ALL animations, keep static state visuals.
            ================================================ */
        @media (prefers-reduced-motion: reduce) {
          .ve-shape,
          .ve-pupil-group,
          .ve-glow-ring {
            animation: none !important;
          }
          .ve-root--dormant .ve-inner {
            transition: none;
          }
        }
      `}</style>

      {/* Glow ring — only rendered for critical state */}
      {isCritical && (
        <circle
          cx="16"
          cy="16"
          r="11"
          fill="none"
          stroke={config.color}
          strokeWidth="1.5"
          opacity="0.15"
          className="ve-glow-ring"
        />
      )}

      {/* Eye inner group — scaled down for dormant (half-closed effect) */}
      <g className="ve-inner">
        {/* Almond eye shape */}
        <path
          d="M5 16 C5 9 12 7 16 7 C20 7 27 9 27 16 C27 23 20 25 16 25 C12 25 5 23 5 16 Z"
          className="ve-shape"
        />

        {/* Iris — coloured fill behind the pupil */}
        <circle cx="16" cy="16" r="6" fill={config.color} opacity={0.75} className="ve-iris" />

        {/* Pupil — position + scale driven by config */}
        <g className="ve-pupil-group" style={{ transformOrigin: '16px 16px' }}>
          <circle
            cx={16 + config.pupilX}
            cy="16"
            r={pupilRadius}
            fill={config.color}
            className="ve-pupil"
          />
        </g>

        {/* Specular highlight — tiny white dot giving the eye "life" */}
        <circle cx="19" cy="13" r="1.5" fill="white" opacity={0.65} className="ve-highlight" />
      </g>
    </svg>
  );
};
