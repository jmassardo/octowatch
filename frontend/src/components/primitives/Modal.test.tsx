import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Modal } from './Modal';

describe('Modal', () => {
  it('renders children content when open', () => {
    render(
      <Modal open={true} onClose={() => {}}>
        <p>Modal content</p>
      </Modal>,
    );
    expect(screen.getByText('Modal content')).toBeInTheDocument();
  });

  it('does not render when open is false', () => {
    render(
      <Modal open={false} onClose={() => {}}>
        <p>Hidden content</p>
      </Modal>,
    );
    expect(screen.queryByText('Hidden content')).not.toBeInTheDocument();
  });

  it('calls onClose on Escape key', () => {
    const handleClose = vi.fn();
    render(
      <Modal open={true} onClose={handleClose}>
        <p>Content</p>
      </Modal>,
    );

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalledOnce();
  });

  it('has accessible close button when title is provided', async () => {
    const user = userEvent.setup();
    const handleClose = vi.fn();
    render(
      <Modal open={true} onClose={handleClose} title="My Modal">
        <p>Content</p>
      </Modal>,
    );

    const closeBtn = screen.getByRole('button', { name: /close/i });
    expect(closeBtn).toBeInTheDocument();

    await user.click(closeBtn);
    expect(handleClose).toHaveBeenCalledOnce();
  });

  it('renders the title when provided', () => {
    render(
      <Modal open={true} onClose={() => {}} title="Settings">
        <p>Content</p>
      </Modal>,
    );
    expect(screen.getByText('Settings')).toBeInTheDocument();
  });

  it('calls onClose when clicking the backdrop', async () => {
    const user = userEvent.setup();
    const handleClose = vi.fn();
    render(
      <Modal open={true} onClose={handleClose} title="Test">
        <p>Modal body</p>
      </Modal>,
    );

    // The backdrop is the outermost portal element with the backdrop CSS class
    const backdrop = document.querySelector('.backdrop');
    expect(backdrop).toBeInTheDocument();
    await user.click(backdrop!);
    expect(handleClose).toHaveBeenCalledOnce();
  });

  it('does not call onClose when clicking inside the dialog', async () => {
    const user = userEvent.setup();
    const handleClose = vi.fn();
    render(
      <Modal open={true} onClose={handleClose} title="Test">
        <p>Inner content</p>
      </Modal>,
    );

    await user.click(screen.getByText('Inner content'));
    expect(handleClose).not.toHaveBeenCalled();
  });

  /* ---------------------------------------------------------------- */
  /*  Accessibility (Issue #49 & #57)                                  */
  /* ---------------------------------------------------------------- */

  it('has role="dialog" and aria-modal="true"', () => {
    render(
      <Modal open={true} onClose={() => {}} title="A11y Test">
        <p>Accessible modal</p>
      </Modal>,
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('has aria-labelledby pointing to the title', () => {
    render(
      <Modal open={true} onClose={() => {}} title="My Title">
        <p>Body</p>
      </Modal>,
    );
    const dialog = screen.getByRole('dialog');
    const labelledBy = dialog.getAttribute('aria-labelledby');
    expect(labelledBy).toBeTruthy();
    const titleEl = document.getElementById(labelledBy!);
    expect(titleEl).toHaveTextContent('My Title');
  });

  it('traps focus within the modal on Tab', async () => {
    const user = userEvent.setup();
    render(
      <Modal open={true} onClose={() => {}} title="Focus Trap Test">
        <button>First</button>
        <button>Second</button>
      </Modal>,
    );

    // The close button should be auto-focused on open
    const closeBtn = screen.getByRole('button', { name: /close/i });
    // Wait for requestAnimationFrame focus
    await vi.waitFor(() => {
      expect(document.activeElement).toBe(closeBtn);
    });

    // Tab through: Close -> First -> Second -> wraps back to Close
    await user.tab();
    expect(document.activeElement).toBe(screen.getByText('First'));

    await user.tab();
    expect(document.activeElement).toBe(screen.getByText('Second'));

    await user.tab();
    // Should wrap back to Close button
    expect(document.activeElement).toBe(closeBtn);
  });

  it('traps focus on Shift+Tab (reverse)', async () => {
    const user = userEvent.setup();
    render(
      <Modal open={true} onClose={() => {}} title="Reverse Focus">
        <button>First</button>
        <button>Second</button>
      </Modal>,
    );

    const closeBtn = screen.getByRole('button', { name: /close/i });
    await vi.waitFor(() => {
      expect(document.activeElement).toBe(closeBtn);
    });

    // Shift+Tab from the close button should wrap to the last element
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(screen.getByText('Second'));
  });

  it('restores focus to previously focused element on close', async () => {
    const triggerBtn = document.createElement('button');
    triggerBtn.textContent = 'Trigger';
    document.body.appendChild(triggerBtn);
    triggerBtn.focus();

    const { rerender } = render(
      <Modal open={true} onClose={() => {}} title="Restore Test">
        <p>Content</p>
      </Modal>,
    );

    // Focus moved into modal
    const closeBtn = screen.getByRole('button', { name: /close/i });
    await vi.waitFor(() => {
      expect(document.activeElement).toBe(closeBtn);
    });

    // Close the modal
    rerender(
      <Modal open={false} onClose={() => {}} title="Restore Test">
        <p>Content</p>
      </Modal>,
    );

    // Focus should return to the trigger button
    expect(document.activeElement).toBe(triggerBtn);

    document.body.removeChild(triggerBtn);
  });
});
