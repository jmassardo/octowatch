import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderWithProviders } from '../../test/utils';
import { useCommandPalette } from '../../hooks/useCommandPalette';
import { CommandPalette } from './CommandPalette';

const navigateMock = vi.fn();
const listEventsMock = vi.fn();
const listDetectionsMock = vi.fn();
const searchActorsMock = vi.fn();

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('../../api/events', () => ({
  listEvents: (...args: unknown[]) => listEventsMock(...args),
}));

vi.mock('../../api/detections', () => ({
  listDetections: (...args: unknown[]) => listDetectionsMock(...args),
}));

vi.mock('../../api/actors', () => ({
  searchActors: (...args: unknown[]) => searchActorsMock(...args),
}));

function PaletteHarness() {
  const palette = useCommandPalette();
  return palette.isOpen ? <CommandPalette isOpen={palette.isOpen} onClose={palette.close} /> : null;
}

async function advanceDebounce() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 350));
  });
}

describe('CommandPalette', () => {
  beforeEach(() => {
    localStorage.clear();
    navigateMock.mockReset();
    listEventsMock.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 6,
      has_next: false,
    });
    listDetectionsMock.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 12,
      has_next: false,
    });
    searchActorsMock.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('opens with Cmd+K and closes with Escape', async () => {
    renderWithProviders(<PaletteHarness />);

    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    expect(await screen.findByRole('dialog', { name: 'Command palette' })).toBeInTheDocument();

    fireEvent.keyDown(screen.getByLabelText('Search command palette'), { key: 'Escape' });

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Command palette' })).not.toBeInTheDocument();
    });
  });

  it('returns matching pages for fuzzy page search', async () => {
    renderWithProviders(<PaletteHarness />);

    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    const input = await screen.findByLabelText('Search command palette');
    fireEvent.change(input, { target: { value: 'rprts' } });

    await advanceDebounce();

    expect(await screen.findByText('Reports')).toBeInTheDocument();
    expect(screen.getAllByText('Pages').length).toBeGreaterThan(0);
  });

  it('supports arrow navigation and Enter execution', async () => {
    renderWithProviders(<PaletteHarness />);

    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    const input = await screen.findByLabelText('Search command palette');
    const options = await screen.findAllByRole('option');

    fireEvent.keyDown(input, { key: 'ArrowDown' });

    await waitFor(() => {
      expect(options[1]).toHaveAttribute('aria-selected', 'true');
    });

    fireEvent.keyDown(input, { key: 'Enter' });

    expect(navigateMock).toHaveBeenCalledWith('/threats');
  });

  it('shows recent searches when opened with an empty query', async () => {
    localStorage.setItem(
      'octowatch-command-palette-recent-searches',
      JSON.stringify(['security review', 'workflow health']),
    );

    renderWithProviders(<PaletteHarness />);

    fireEvent.keyDown(window, { key: 'k', metaKey: true });

    expect(await screen.findByText('security review')).toBeInTheDocument();
    expect(screen.getByText('workflow health')).toBeInTheDocument();
  });
});
