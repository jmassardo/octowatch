import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Drawer } from './Drawer';

describe('Drawer', () => {
  it('renders children content when open', () => {
    render(
      <Drawer open={true} onClose={() => {}} title="Test Drawer">
        <p>Drawer content</p>
      </Drawer>,
    );
    expect(screen.getByText('Drawer content')).toBeInTheDocument();
  });

  it('does not render when open is false', () => {
    render(
      <Drawer open={false} onClose={() => {}} title="Test">
        <p>Hidden content</p>
      </Drawer>,
    );
    expect(screen.queryByText('Hidden content')).not.toBeInTheDocument();
  });

  it('calls onClose on Escape key', () => {
    const handleClose = vi.fn();
    render(
      <Drawer open={true} onClose={handleClose} title="Test">
        <p>Content</p>
      </Drawer>,
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalledOnce();
  });

  it('calls onClose when clicking the backdrop', async () => {
    const user = userEvent.setup();
    const handleClose = vi.fn();
    render(
      <Drawer open={true} onClose={handleClose} title="Test">
        <p>Panel body</p>
      </Drawer>,
    );
    const backdrop = screen.getByTestId('drawer-backdrop');
    await user.click(backdrop);
    expect(handleClose).toHaveBeenCalledOnce();
  });

  it('does not call onClose when clicking inside the panel', async () => {
    const user = userEvent.setup();
    const handleClose = vi.fn();
    render(
      <Drawer open={true} onClose={handleClose} title="Test">
        <p>Inner content</p>
      </Drawer>,
    );
    await user.click(screen.getByText('Inner content'));
    expect(handleClose).not.toHaveBeenCalled();
  });

  it('has accessible close button', async () => {
    const user = userEvent.setup();
    const handleClose = vi.fn();
    render(
      <Drawer open={true} onClose={handleClose} title="My Drawer">
        <p>Content</p>
      </Drawer>,
    );
    const panel = screen.getByTestId('drawer-panel');
    const closeBtn = within(panel).getByRole('button', { name: /close/i });
    expect(closeBtn).toBeInTheDocument();
    await user.click(closeBtn);
    expect(handleClose).toHaveBeenCalledOnce();
  });

  it('has role="dialog" and aria-modal', () => {
    render(
      <Drawer open={true} onClose={() => {}} title="Accessible Drawer">
        <p>Content</p>
      </Drawer>,
    );
    const panel = screen.getByTestId('drawer-panel');
    expect(panel).toHaveAttribute('role', 'dialog');
    expect(panel).toHaveAttribute('aria-modal', 'true');
  });

  it('uses aria-labelledby pointing to the title', () => {
    render(
      <Drawer open={true} onClose={() => {}} title="Developer Info" titleId="dev-name">
        <p>Content</p>
      </Drawer>,
    );
    const panel = screen.getByTestId('drawer-panel');
    expect(panel).toHaveAttribute('aria-labelledby', 'dev-name');
    const titleEl = document.getElementById('dev-name');
    expect(titleEl).toBeInTheDocument();
    expect(titleEl?.textContent).toBe('Developer Info');
  });

  it('renders the title text', () => {
    render(
      <Drawer open={true} onClose={() => {}} title="Settings Panel">
        <p>Body</p>
      </Drawer>,
    );
    expect(screen.getByText('Settings Panel')).toBeInTheDocument();
  });

  it('traps focus inside the panel on Tab', () => {
    render(
      <Drawer open={true} onClose={() => {}} title="Focus Test">
        <button>First</button>
        <button>Second</button>
      </Drawer>,
    );

    const panel = screen.getByTestId('drawer-panel');
    const buttons = within(panel).getAllByRole('button');
    // buttons: [Close, First, Second]
    const closeBtn = buttons[0]!;
    const secondBtn = buttons[2]!;

    // Focus the last button and press Tab → should wrap to close button
    secondBtn.focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(closeBtn);

    // Shift+Tab from close → should wrap to last button
    closeBtn.focus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(secondBtn);
  });
});
