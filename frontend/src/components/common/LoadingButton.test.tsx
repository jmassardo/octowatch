import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LoadingButton } from './LoadingButton';

describe('LoadingButton', () => {
  it('renders children', () => {
    render(<LoadingButton>Save</LoadingButton>);
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
  });

  it('is disabled and shows spinner when loading', () => {
    render(<LoadingButton loading>Save</LoadingButton>);
    const btn = screen.getByRole('button');
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('aria-busy', 'true');
  });

  it('is clickable when not loading', async () => {
    const onClick = vi.fn();
    render(<LoadingButton onClick={onClick}>Save</LoadingButton>);
    await userEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('respects disabled prop', () => {
    render(<LoadingButton disabled>Save</LoadingButton>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('applies className prop', () => {
    render(<LoadingButton className="custom">Save</LoadingButton>);
    expect(screen.getByRole('button').className).toContain('custom');
  });
});
