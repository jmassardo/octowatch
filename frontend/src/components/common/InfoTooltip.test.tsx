import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InfoTooltip } from './InfoTooltip';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('InfoTooltip', () => {
  it('shows tooltip content on hover with formatting', async () => {
    const user = userEvent.setup();

    render(
      <InfoTooltip content="**Important** details live in the [docs](https://example.com)." />,
    );

    await user.hover(screen.getByRole('button', { name: /more information/i }));

    expect(screen.getByRole('tooltip')).toBeInTheDocument();
    expect(screen.getByText('Important').tagName).toBe('STRONG');
    expect(screen.getByRole('link', { name: 'docs' })).toHaveAttribute(
      'href',
      'https://example.com',
    );
  });

  it('chooses bottom placement when there is not enough room above', async () => {
    const user = userEvent.setup();

    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      const testId = this.getAttribute('data-testid');
      if (testId === 'info-tooltip-trigger') {
        return {
          x: 20,
          y: 4,
          width: 18,
          height: 18,
          top: 4,
          right: 38,
          bottom: 22,
          left: 20,
          toJSON: () => ({}),
        } as DOMRect;
      }

      if (testId === 'info-tooltip-panel') {
        return {
          x: 0,
          y: 0,
          width: 180,
          height: 80,
          top: 0,
          right: 180,
          bottom: 80,
          left: 0,
          toJSON: () => ({}),
        } as DOMRect;
      }

      return {
        x: 0,
        y: 0,
        width: 0,
        height: 0,
        top: 0,
        right: 0,
        bottom: 0,
        left: 0,
        toJSON: () => ({}),
      } as DOMRect;
    });

    render(<InfoTooltip content="Placement example" />);
    await user.hover(screen.getByRole('button', { name: /more information/i }));

    expect(screen.getByRole('tooltip')).toHaveAttribute('data-placement', 'bottom');
  });

  it('hides the tooltip after hover leaves', async () => {
    const user = userEvent.setup();

    render(<InfoTooltip content="Hidden when inactive" />);
    const trigger = screen.getByRole('button', { name: /more information/i });

    await user.hover(trigger);
    expect(screen.getByRole('tooltip')).toBeInTheDocument();

    await user.unhover(trigger);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });
});
