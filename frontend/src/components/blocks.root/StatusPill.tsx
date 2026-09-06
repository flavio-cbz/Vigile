import type React from 'react';
import type { StatusPillProps } from './types';

const DEFAULT_ACTIVE_STATES = ['running', 'active'];

export const StatusPill: React.FC<StatusPillProps> = ({
  status,
  activeStates = DEFAULT_ACTIVE_STATES,
}) => {
  const isActive = activeStates.includes(status.toLowerCase());

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold leading-none ${
        isActive
          ? 'bg-green-custom/10 text-green-custom border border-green-custom/20'
          : 'bg-zinc-800 text-zinc-400 border border-zinc-700/50'
      }`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          isActive ? 'bg-green-custom animate-pulse' : 'bg-zinc-500'
        }`}
      />
      {status}
    </span>
  );
};

export default StatusPill;
