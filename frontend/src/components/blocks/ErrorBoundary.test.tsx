import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { ErrorBoundary } from './ErrorBoundary';

const Bomb = ({ shouldThrow }: { shouldThrow: boolean }) => {
  if (shouldThrow) throw new Error('boom');
  return <div>survived</div>;
};

describe('ErrorBoundary', () => {
  it('renders children when no error occurs', () => {
    render(
      <ErrorBoundary>
        <div>content</div>
      </ErrorBoundary>
    );
    expect(screen.getByText('content')).toBeInTheDocument();
  });

  it('catches render errors and shows the fallback with retry', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <ErrorBoundary onRetry={vi.fn()}>
        <Bomb shouldThrow />
      </ErrorBoundary>
    );
    expect(screen.getByText('Une erreur est survenue')).toBeInTheDocument();
    expect(screen.getByText('boom')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Réessayer' })).toBeInTheDocument();
  });

  it('retry resets the boundary and re-renders children', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const Wrapper = () => {
      const [shouldThrow, setShouldThrow] = useState(true);
      return (
        <ErrorBoundary onRetry={() => setShouldThrow(false)}>
          <Bomb shouldThrow={shouldThrow} />
        </ErrorBoundary>
      );
    };
    render(<Wrapper />);
    expect(screen.getByText('Une erreur est survenue')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Réessayer' }));
    expect(screen.getByText('survived')).toBeInTheDocument();
  });

  it('supports a custom fallback node', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <ErrorBoundary fallback={<div>custom fallback</div>}>
        <Bomb shouldThrow />
      </ErrorBoundary>
    );
    expect(screen.getByText('custom fallback')).toBeInTheDocument();
  });
});