import React from 'react';

interface InsightTextProps {
  children: React.ReactNode;
  className?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  title?: string;
}

export const InsightText: React.FC<InsightTextProps> = ({ children, className = '', size = 'md', title }) => {
  const getSizeClass = () => {
    switch (size) {
      case 'sm':
        return 'text-lg md:text-xl';
      case 'lg':
        return 'text-2xl md:text-3xl lg:text-4xl';
      case 'xl':
        return 'text-3xl md:text-4xl lg:text-5xl';
      case 'md':
      default:
        return 'text-xl md:text-2xl';
    }
  };

  return (
    <span className={`font-serif tracking-wide text-text-1 leading-snug ${getSizeClass()} ${className}`} title={title}>
      {children}
    </span>
  );
};
