import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ErrorState } from './ErrorState';

describe('ErrorState', () => {
  it('renders default title and message', () => {
    render(<ErrorState />);
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText(/Unable to connect/)).toBeInTheDocument();
  });

  it('renders custom title and message', () => {
    render(<ErrorState title="Oops" message="Custom error" />);
    expect(screen.getByText('Oops')).toBeInTheDocument();
    expect(screen.getByText('Custom error')).toBeInTheDocument();
  });

  it('renders retry button when onRetry provided', async () => {
    const retry = vi.fn();
    render(<ErrorState onRetry={retry} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it('does not render retry button without onRetry', () => {
    render(<ErrorState />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('renders custom icon', () => {
    render(<ErrorState icon="💥" />);
    expect(screen.getByText('💥')).toBeInTheDocument();
  });

  it('has role="alert" for accessibility', () => {
    render(<ErrorState />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});
