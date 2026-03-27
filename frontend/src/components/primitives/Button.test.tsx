import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from './Button';

describe('Button', () => {
  it('renders children', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole('button', { name: 'Click me' })).toBeInTheDocument();
  });

  it('calls onClick when clicked', async () => {
    const user = userEvent.setup();
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Press</Button>);

    await user.click(screen.getByRole('button', { name: 'Press' }));
    expect(handleClick).toHaveBeenCalledOnce();
  });

  it('can be disabled', async () => {
    const user = userEvent.setup();
    const handleClick = vi.fn();
    render(
      <Button disabled onClick={handleClick}>
        Disabled
      </Button>,
    );

    const btn = screen.getByRole('button', { name: 'Disabled' });
    expect(btn).toBeDisabled();

    await user.click(btn);
    expect(handleClick).not.toHaveBeenCalled();
  });

  it('applies variant class names', () => {
    render(<Button variant="primary">Primary</Button>);
    const btn = screen.getByRole('button', { name: 'Primary' });
    expect(btn.className).toContain('primary');
  });
});
