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
        return 'text-[15px] md:text-base font-semibold';
      case 'lg':
        return 'text-xl md:text-2xl lg:text-3xl font-bold';
      case 'xl':
        return 'text-2xl md:text-3xl lg:text-4xl font-extrabold';
      case 'md':
      default:
        return 'text-lg md:text-xl font-semibold';
    }
  };

  return (
    <span className={`font-sans tracking-tight text-text-1 leading-snug ${getSizeClass()} ${className}`} title={title}>
      {children}
    </span>
  );
};
