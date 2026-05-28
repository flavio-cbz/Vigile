import React from 'react';

interface SkeletonProps {
  className?: string;
  width?: string;
  height?: string;
}

export const Skeleton: React.FC<SkeletonProps> = ({ className = '', width, height }) => (
  <div
    className={`rounded-lg skeleton-shimmer ${className}`}
    style={{ width, height }}
  />
);

export const CardSkeleton: React.FC = () => (
  <div className="card p-4 flex flex-col justify-between h-[150px] w-full animate-pulse-subtle">
    <div className="flex justify-between items-center mb-2">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-4 w-12" />
    </div>
    <div className="space-y-2 flex-1 mt-2">
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-5/6" />
    </div>
    <div className="flex justify-between items-center mt-2">
      <Skeleton className="h-3 w-1/4" />
      <Skeleton className="h-6 w-16" />
    </div>
  </div>
);

export const RowSkeleton: React.FC = () => (
  <div className="flex items-center justify-between p-3 border-b border-border animate-pulse-subtle">
    <div className="flex items-center gap-3">
      <Skeleton className="h-8 w-8 rounded-full" />
      <div className="space-y-1">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-3 w-16" />
      </div>
    </div>
    <Skeleton className="h-6 w-20" />
  </div>
);

export const BannerSkeleton: React.FC = () => (
  <div className="p-6 bg-surface-1 border border-border rounded-xl flex items-center justify-between w-full h-[80px] animate-pulse-subtle">
    <div className="flex items-center gap-4">
      <Skeleton className="h-6 w-6 rounded-full" />
      <div className="space-y-1.5">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-3 w-32" />
      </div>
    </div>
    <Skeleton className="h-8 w-24" />
  </div>
);

export const ChartSkeleton: React.FC = () => (
  <div className="card p-4 flex flex-col h-[200px] w-full justify-between animate-pulse-subtle">
    <Skeleton className="h-4 w-1/4 mb-4" />
    <div className="flex items-end gap-2 flex-1">
      <Skeleton className="h-[20%] flex-1" />
      <Skeleton className="h-[40%] flex-1" />
      <Skeleton className="h-[35%] flex-1" />
      <Skeleton className="h-[60%] flex-1" />
      <Skeleton className="h-[50%] flex-1" />
      <Skeleton className="h-[80%] flex-1" />
      <Skeleton className="h-[70%] flex-1" />
    </div>
  </div>
);

export const ProposalCardSkeleton: React.FC = () => (
  <div className="w-[280px] h-[150px] shrink-0 card p-4 flex flex-col justify-between animate-pulse-subtle">
    <div className="flex items-center justify-between border-b border-border pb-1.5">
      <Skeleton className="h-3 w-16" />
      <Skeleton className="h-3 w-20" />
    </div>
    <Skeleton className="h-8 w-full my-2" />
    <div className="flex items-center justify-between">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-4 w-14" />
    </div>
  </div>
);

export const ChatCardSkeleton: React.FC = () => (
  <div className="w-[240px] h-[130px] shrink-0 card p-4 flex flex-col justify-between animate-pulse-subtle">
    <div className="flex items-center gap-1 border-b border-border pb-1">
      <Skeleton className="h-3 w-3 rounded-full" />
      <Skeleton className="h-3 w-20" />
    </div>
    <div className="space-y-1.5 my-1">
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-3/4" />
    </div>
    <Skeleton className="h-3 w-28" />
  </div>
);
