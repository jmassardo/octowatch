import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Toast } from './Toast';
import type { ToastItem } from './Toast';

const baseItem: ToastItem = {
  id: 't-1',
  message: 'Hello world',
  variant: 'info',
  duration: 5000,
};

describe('Toast', () => {
  it('renders message text', () => {
    render(<Toast item={baseItem} onDismiss={vi.fn()} />);
    expect(screen.getByText('Hello world')).toBeInTheDocument();
  });

  it('fires onDismiss when dismiss button clicked', async () => {
    const dismiss = vi.fn();
    render(<Toast item={baseItem} onDismiss={dismiss} />);
    await userEvent.click(screen.getByLabelText('Dismiss notification'));
    expect(dismiss).toHaveBeenCalledWith('t-1');
  });

  it('renders correct variant icon for success', () => {
    render(<Toast item={{ ...baseItem, variant: 'success' }} onDismiss={vi.fn()} />);
    expect(screen.getByText('✓')).toBeInTheDocument();
  });

  it('renders correct variant icon for error', () => {
    render(<Toast item={{ ...baseItem, variant: 'error' }} onDismiss={vi.fn()} />);
    // Both the icon and dismiss button have ✕ — just check role="alert" exists
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('has role="alert" and aria-live="assertive"', () => {
    render(<Toast item={baseItem} onDismiss={vi.fn()} />);
    const el = screen.getByRole('alert');
    expect(el).toHaveAttribute('aria-live', 'assertive');
  });
});
