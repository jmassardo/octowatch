import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SkipToContent } from './SkipToContent';

describe('SkipToContent', () => {
  it('renders a skip link for the main content landmark', () => {
    render(<SkipToContent />);

    expect(screen.getByRole('link', { name: /skip to main content/i })).toHaveAttribute(
      'href',
      '#main-content',
    );
  });

  it('moves focus to the target landmark when activated', async () => {
    const user = userEvent.setup();

    render(
      <>
        <SkipToContent />
        <main id="main-content">Main content</main>
      </>,
    );

    await user.click(screen.getByRole('link', { name: /skip to main content/i }));

    expect(screen.getByRole('main')).toHaveFocus();
  });
});
