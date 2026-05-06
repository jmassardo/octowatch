import { describe, it, expect, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ToastProvider } from './ToastProvider';
import { useToast } from '../../hooks/useToast';

function TestHarness() {
  const { showToast } = useToast();
  return (
    <div>
      <button onClick={() => showToast('Test toast', 'success')}>Fire</button>
      <button onClick={() => showToast('Error toast', 'error')}>Error</button>
    </div>
  );
}

describe('ToastProvider', () => {
  it('renders children', () => {
    render(
      <ToastProvider>
        <div>Child content</div>
      </ToastProvider>,
    );
    expect(screen.getByText('Child content')).toBeInTheDocument();
  });

  it('shows toast when showToast is called', async () => {
    render(
      <ToastProvider>
        <TestHarness />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByText('Fire'));
    expect(screen.getByText('Test toast')).toBeInTheDocument();
  });

  it('limits visible toasts to 3', async () => {
    function ManyToasts() {
      const { showToast } = useToast();
      return (
        <button
          onClick={() => {
            showToast('Toast 1', 'info');
            showToast('Toast 2', 'info');
            showToast('Toast 3', 'info');
            showToast('Toast 4', 'info');
          }}
        >
          Fire many
        </button>
      );
    }
    render(
      <ToastProvider>
        <ManyToasts />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByText('Fire many'));
    const alerts = screen.getAllByRole('alert');
    expect(alerts.length).toBeLessThanOrEqual(3);
  });

  it('dismisses toast on Escape key', async () => {
    render(
      <ToastProvider>
        <TestHarness />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByText('Fire'));
    expect(screen.getByText('Test toast')).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByText('Test toast')).toBeNull();
  });

  it('auto-dismisses after duration', async () => {
    vi.useFakeTimers();
    function QuickToast() {
      const { showToast } = useToast();
      return <button onClick={() => showToast('Quick', 'info', { duration: 100 })}>Quick</button>;
    }
    render(
      <ToastProvider>
        <QuickToast />
      </ToastProvider>,
    );
    await act(async () => {
      screen.getByText('Quick').click();
    });
    expect(screen.getByText('Quick', { selector: 'span' })).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.queryByText('Quick', { selector: '[role="alert"] span' })).toBeNull();
    vi.useRealTimers();
  });
});
