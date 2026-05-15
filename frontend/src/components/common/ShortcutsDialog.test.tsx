import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '../common/ToastProvider';
import { HotkeyProvider } from '../../contexts/HotkeyProvider';
import { useHotkeys, type HotkeyBinding } from '../../hooks/useHotkeys';
import { ShortcutsDialog } from './ShortcutsDialog';
import { useState, useCallback, useMemo } from 'react';

/* ── Mocks ───────────────────────────────────────────────────────── */

vi.mock('../GuidedTour/tourStorage', () => ({
  isTourCompleted: () => true,
  resetTour: vi.fn(),
}));

/* ── Helpers ─────────────────────────────────────────────────────── */

function LocationDisplay() {
  const loc = useLocation();
  return <div data-testid="location">{loc.pathname}</div>;
}

/**
 * A minimal harness that registers the same shortcuts AppShell does
 * without dragging in Sidebar / TopBar / GuidedTour dependencies.
 */
function ShortcutHarness({ initialRoute = '/' }: { initialRoute?: string }) {
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  const openShortcuts = useCallback(() => setShortcutsOpen(true), []);
  const closeShortcuts = useCallback(() => setShortcutsOpen(false), []);

  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ToastProvider>
        <MemoryRouter initialEntries={[initialRoute]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <HotkeyProvider>
            <ShortcutHarnessInner
              shortcutsOpen={shortcutsOpen}
              openShortcuts={openShortcuts}
              closeShortcuts={closeShortcuts}
            />
          </HotkeyProvider>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

function ShortcutHarnessInner({
  shortcutsOpen,
  openShortcuts,
  closeShortcuts,
}: {
  shortcutsOpen: boolean;
  openShortcuts: () => void;
  closeShortcuts: () => void;
}) {
  const bindings: HotkeyBinding[] = useMemo(
    () => [
      { key: '?', handler: openShortcuts, label: 'Show keyboard shortcuts', category: 'General' },
      { key: 'g d', handler: () => {}, label: 'Go to Dashboard', category: 'Navigation' },
    ],
    [openShortcuts],
  );

  useHotkeys(bindings);

  return (
    <>
      <Routes>
        <Route path="*" element={<LocationDisplay />} />
      </Routes>
      <ShortcutsDialog open={shortcutsOpen} onClose={closeShortcuts} />
    </>
  );
}

function NavigationHarness() {
  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ToastProvider>
        <MemoryRouter initialEntries={['/']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <HotkeyProvider>
            <NavigationHarnessInner />
          </HotkeyProvider>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

function NavigationHarnessInner() {
  /* We can't use react-router's useNavigate in tests with MemoryRouter
     the same way as in the real app, so we capture navigation via location. */
  const loc = useLocation();
  const [target, setTarget] = useState(loc.pathname);

  const bindings: HotkeyBinding[] = useMemo(
    () => [
      {
        key: 'g d',
        handler: () => setTarget('/dashboard'),
        label: 'Go to Dashboard',
        category: 'Navigation',
      },
    ],
    [],
  );

  useHotkeys(bindings);

  return <div data-testid="nav-target">{target}</div>;
}

/* ── Tests ────────────────────────────────────────────────────────── */

describe('ShortcutsDialog', () => {
  it('opens the shortcuts dialog when "?" is pressed', async () => {
    render(<ShortcutHarness />);

    expect(screen.queryByText('Keyboard Shortcuts')).not.toBeInTheDocument();

    fireEvent.keyDown(document, { key: '?' });

    await waitFor(() => {
      expect(screen.getByText('Keyboard Shortcuts')).toBeInTheDocument();
    });
  });

  it('closes the shortcuts dialog on Escape', async () => {
    render(<ShortcutHarness />);

    /* Open dialog */
    fireEvent.keyDown(document, { key: '?' });
    await waitFor(() => {
      expect(screen.getByText('Keyboard Shortcuts')).toBeInTheDocument();
    });

    /* Close dialog */
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => {
      expect(screen.queryByText('Keyboard Shortcuts')).not.toBeInTheDocument();
    });
  });

  it('displays shortcut entries grouped by category', async () => {
    render(<ShortcutHarness />);

    fireEvent.keyDown(document, { key: '?' });

    await waitFor(() => {
      expect(screen.getByText('Navigation')).toBeInTheDocument();
      expect(screen.getByText('General')).toBeInTheDocument();
      expect(screen.getByText('Go to Dashboard')).toBeInTheDocument();
      expect(screen.getByText('Show keyboard shortcuts')).toBeInTheDocument();
    });
  });
});

describe('Keyboard navigation sequences', () => {
  it('triggers "g then d" navigation handler', async () => {
    render(<NavigationHarness />);

    expect(screen.getByTestId('nav-target')).toHaveTextContent('/');

    /* Press 'g', then 'd' */
    fireEvent.keyDown(document, { key: 'g' });
    fireEvent.keyDown(document, { key: 'd' });

    await waitFor(() => {
      expect(screen.getByTestId('nav-target')).toHaveTextContent('/dashboard');
    });
  });
});

describe('Input suppression', () => {
  function InputHarness() {
    const [fired, setFired] = useState(false);

    const bindings: HotkeyBinding[] = useMemo(
      () => [{ key: '?', handler: () => setFired(true), label: 'Test', category: 'General' }],
      [],
    );

    useHotkeys(bindings);

    return (
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <ToastProvider>
          <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <HotkeyProvider>
              <input data-testid="text-input" type="text" />
              <div data-testid="fired">{fired ? 'yes' : 'no'}</div>
            </HotkeyProvider>
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>
    );
  }

  it('suppresses shortcuts when typing in an input field', async () => {
    const user = userEvent.setup();
    render(<InputHarness />);

    const input = screen.getByTestId('text-input');
    await user.click(input);

    /* Type '?' inside the input — hotkey should NOT fire. */
    fireEvent.keyDown(input, { key: '?' });

    expect(screen.getByTestId('fired')).toHaveTextContent('no');
  });

  it('fires shortcut when not focused on input', () => {
    render(<InputHarness />);

    fireEvent.keyDown(document, { key: '?' });

    expect(screen.getByTestId('fired')).toHaveTextContent('yes');
  });
});
