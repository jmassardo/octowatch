import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HelpPanel } from './HelpPanel';
import type { HelpContent } from './helpContent';

const sampleContent: HelpContent = {
  title: 'Dashboard',
  description: 'Review operational signals for your organizations.',
  concepts: [{ term: 'Views', definition: 'Switch between tailored dashboard views.' }],
  tasks: [{ title: 'Review activity', steps: ['Open the page', 'Inspect the summary cards'] }],
  relatedPages: [{ title: 'Threats', path: '/threats' }],
};

describe('HelpPanel', () => {
  it('renders contextual sections when open', () => {
    render(<HelpPanel open={true} onClose={() => {}} content={sampleContent} />);

    expect(screen.getByRole('dialog', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByText('About this page')).toBeInTheDocument();
    expect(screen.getByText('Key concepts')).toBeInTheDocument();
    expect(screen.getByText('Common tasks')).toBeInTheDocument();
    expect(screen.getByText('Related pages')).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    render(<HelpPanel open={false} onClose={() => {}} content={sampleContent} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('calls onClose when clicking the close button', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    render(<HelpPanel open={true} onClose={onClose} content={sampleContent} />);
    await user.click(screen.getByRole('button', { name: /close help panel/i }));

    expect(onClose).toHaveBeenCalledOnce();
  });

  it('calls onClose when pressing Escape', () => {
    const onClose = vi.fn();

    render(<HelpPanel open={true} onClose={onClose} content={sampleContent} />);
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(onClose).toHaveBeenCalledOnce();
  });

  it('calls onClose when clicking the overlay', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    render(<HelpPanel open={true} onClose={onClose} content={sampleContent} />);
    await user.click(screen.getByTestId('help-panel-overlay'));

    expect(onClose).toHaveBeenCalledOnce();
  });
});
