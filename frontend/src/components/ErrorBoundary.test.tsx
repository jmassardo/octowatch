import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ErrorBoundary } from './ErrorBoundary';

const ThrowingComponent = () => {
  throw new Error('Test error');
};

describe('ErrorBoundary', () => {
  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <div>Hello</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText('Hello')).toBeTruthy();
  });

  it('renders fallback UI on error', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>,
    );
    expect(screen.getByText('Something went wrong')).toBeTruthy();
    expect(screen.getByText('Test error')).toBeTruthy();
    expect(screen.getByRole('button', { name: /return to dashboard/i })).toBeTruthy();
    vi.restoreAllMocks();
  });

  it('renders custom fallback when provided', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <ErrorBoundary fallback={<div>Custom error</div>}>
        <ThrowingComponent />
      </ErrorBoundary>,
    );
    expect(screen.getByText('Custom error')).toBeTruthy();
    vi.restoreAllMocks();
  });

  it('shows generic message when error has no message', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});

    const EmptyErrorComponent = () => {
      throw new Error('');
    };

    render(
      <ErrorBoundary>
        <EmptyErrorComponent />
      </ErrorBoundary>,
    );
    expect(screen.getByText('An unexpected error occurred.')).toBeTruthy();
    vi.restoreAllMocks();
  });
});
