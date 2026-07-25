import React from 'react';

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const Spinner: React.FC<SpinnerProps> = ({ size = 'md', className = '' }) => {
  const getSize = () => {
    switch (size) {
      case 'sm':
        return 'w-4 h-4 border-2';
      case 'lg':
        return 'w-10 h-10 border-3';
      case 'md':
      default:
        return 'w-6 h-6 border-2';
    }
  };

  return (
    <div className={`flex items-center justify-center ${className}`}>
      <div
        className={`animate-spin rounded-full border-t-accent border-r-accent/30 border-b-accent/30 border-l-accent/30 ${getSize()}`}
      />
    </div>
  );
};
