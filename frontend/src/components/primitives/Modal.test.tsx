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
});
