import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EmptyState } from './EmptyState';

describe('EmptyState', () => {
  it('renders title and description', () => {
    render(<EmptyState title="No items" description="Nothing here" />);
    expect(screen.getByText('No items')).toBeInTheDocument();
    expect(screen.getByText('Nothing here')).toBeInTheDocument();
  });

  it('renders icon when provided', () => {
    render(<EmptyState title="Empty" icon="🎉" />);
    expect(screen.getByText('🎉')).toBeInTheDocument();
  });

  it('renders CTA button and fires action', async () => {
    const action = vi.fn();
    render(<EmptyState title="Empty" ctaLabel="Add" ctaAction={action} />);
    await userEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(action).toHaveBeenCalledTimes(1);
  });

  it('does not render CTA when no action', () => {
    render(<EmptyState title="Empty" ctaLabel="Add" />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('uses variant defaults', () => {
    render(<EmptyState variant="filtered" title="No results match filters" />);
    expect(screen.getByText('No results match filters')).toBeInTheDocument();
    expect(screen.getByText('🔍')).toBeInTheDocument();
  });

  it('overrides variant defaults with explicit props', () => {
    render(<EmptyState variant="filtered" title="Custom title" icon="🚀" />);
    expect(screen.getByText('Custom title')).toBeInTheDocument();
    expect(screen.getByText('🚀')).toBeInTheDocument();
  });

  it('has role="status" for accessibility', () => {
    render(<EmptyState title="Test" />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders setup variant defaults', () => {
    render(<EmptyState variant="setup" title="No detections found" />);
    expect(screen.getByText('🛡️')).toBeInTheDocument();
  });
});
