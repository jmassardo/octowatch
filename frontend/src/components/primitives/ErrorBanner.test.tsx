import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ErrorBanner } from './ErrorBanner';

describe('ErrorBanner', () => {
  it('renders the default error message', () => {
    render(<ErrorBanner />);
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('renders a custom error message', () => {
    render(<ErrorBanner message="Network error" />);
    expect(screen.getByText('Network error')).toBeInTheDocument();
  });

  it('shows retry button when onRetry is provided', () => {
    render(<ErrorBanner onRetry={() => {}} />);
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('calls onRetry when retry button is clicked', async () => {
    const user = userEvent.setup();
    const handleRetry = vi.fn();
    render(<ErrorBanner onRetry={handleRetry} />);

    await user.click(screen.getByRole('button', { name: /retry/i }));
    expect(handleRetry).toHaveBeenCalledOnce();
  });

  it('does not show retry button when onRetry is not provided', () => {
    render(<ErrorBanner />);
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
  });
});
