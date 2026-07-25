import React from 'react';

const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className = '', ...props }, ref) => (
    <div
      ref={ref}
      className={`rounded-xl border border-border-strong bg-surface/95 shadow-2xl ${className}`}
      {...props}
    />
  ),
);
Card.displayName = 'Card';

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className = '', ...props }, ref) => (
    <div
      ref={ref}
      className={`flex flex-col space-y-1.5 p-3 border-b border-border/40 ${className}`}
      {...props}
    />
  ),
);
CardHeader.displayName = 'CardHeader';

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className = '', ...props }, ref) => (
    <div ref={ref} className={`p-3 ${className}`} {...props} />
  ),
);
CardContent.displayName = 'CardContent';

export { Card, CardHeader, CardContent };
