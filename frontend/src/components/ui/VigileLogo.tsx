import React from 'react';

interface VigileLogoProps {
  className?: string;
}

export const VigileLogo: React.FC<VigileLogoProps> = ({ className }) => {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 200 200"
      className={className}
      fill="none"
    >
      {/* Rounded square frame — bold, theme-aware */}
      <rect
        x="28" y="28" width="144" height="144" rx="28" ry="28"
        stroke="currentColor" strokeWidth="10" fill="none"
      />
      {/* Letter V — bold geometric strokes meeting at bottom-center */}
      <path
        d="M 56,52 L 100,158 L 144,52"
        stroke="currentColor" strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" fill="none"
      />
    </svg>
  );
};
