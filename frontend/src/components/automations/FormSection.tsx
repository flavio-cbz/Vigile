import React from 'react';

interface SectionProps {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}

export function Section({ title, icon, children }: SectionProps) {
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-3">
        {icon}
        <h3 className="text-sm font-semibold text-text-1 uppercase tracking-wider">{title}</h3>
      </div>
      <div className="space-y-3">
        {children}
      </div>
    </div>
  );
}

interface FormRowProps {
  label: string;
  children: React.ReactNode;
}

export function FormRow({ label, children }: FormRowProps) {
  return (
    <div className="space-y-1">
      <label className="form-label text-xs">{label}</label>
      {children}
    </div>
  );
}
