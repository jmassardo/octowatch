import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { ChainsPane } from './ChainsPane';

/* ── Mocks ─────────────────────────────────────────────────────────── */

const mockListChains = vi.fn().mockResolvedValue({
  items: [
    {
      chain_id: 'chain-1',
      title: 'Correlated: Suspicious access',
      status: 'open',
      severity: 'high',
      assignee: 'alice',
      created_at: '2025-06-01T10:00:00Z',
      updated_at: '2025-06-01T12:00:00Z',
      resolved_at: null,
      detection_count: 3,
    },
    {
      chain_id: 'chain-2',
      title: 'Correlated: Token abuse',
      status: 'investigating',
      severity: 'critical',
      assignee: null,
      created_at: '2025-06-02T08:00:00Z',
      updated_at: '2025-06-02T09:00:00Z',
      resolved_at: null,
      detection_count: 2,
    },
  ],
  total: 2,
  page: 1,
  page_size: 25,
  has_next: false,
});

const mockGetChainMetrics = vi.fn().mockResolvedValue({
  active_chains: 5,
  avg_chain_size: 3.2,
  chains_resolved_today: 1,
  total_chains: 12,
});

const mockGetChain = vi.fn().mockResolvedValue({
  chain_id: 'chain-1',
  title: 'Correlated: Suspicious access',
  status: 'open',
  severity: 'high',
  assignee: 'alice',
  notes: null,
  created_at: '2025-06-01T10:00:00Z',
  updated_at: '2025-06-01T12:00:00Z',
  resolved_at: null,
  members: [
    {
      detection_id: 1,
      correlation_type: 'actor_target',
      confidence: 0.9,
      added_at: '2025-06-01T10:00:00Z',
      detection_title: 'Suspicious repo access',
      detection_severity: 'high',
      detection_status: 'open',
      detection_actor: 'alice',
      detection_triggered_at: '2025-06-01T09:55:00Z',
    },
    {
      detection_id: 2,
      correlation_type: 'actor_category',
      confidence: 0.8,
      added_at: '2025-06-01T10:00:00Z',
      detection_title: 'Token creation',
      detection_severity: 'medium',
      detection_status: 'open',
      detection_actor: 'alice',
      detection_triggered_at: '2025-06-01T09:50:00Z',
    },
  ],
  detection_count: 2,
});

const mockUpdateChain = vi.fn().mockResolvedValue({});

vi.mock('../../api/correlations', () => ({
  listChains: (...args: unknown[]) => mockListChains(...args),
  getChainMetrics: () => mockGetChainMetrics(),
  getChain: (...args: unknown[]) => mockGetChain(...args),
  updateChain: (...args: unknown[]) => mockUpdateChain(...args),
  mergeChain: vi.fn().mockResolvedValue({}),
  runCorrelation: vi.fn().mockResolvedValue({}),
}));

describe('ChainsPane', () => {
  beforeEach(() => {
    mockListChains.mockClear();
    mockGetChainMetrics.mockClear();
    mockGetChain.mockClear();
    mockUpdateChain.mockClear();
  });

  it('renders metric cards', async () => {
    renderWithProviders(<ChainsPane />);
    expect(await screen.findByText('Active Chains')).toBeInTheDocument();
    expect(await screen.findByText('Avg Chain Size')).toBeInTheDocument();
    expect(await screen.findByText('Resolved Today')).toBeInTheDocument();
    expect(await screen.findByText('Total Chains')).toBeInTheDocument();
  });

  it('renders metric values when loaded', async () => {
    renderWithProviders(<ChainsPane />);
    expect(await screen.findByText('5')).toBeInTheDocument();
    expect(await screen.findByText('3.2')).toBeInTheDocument();
    expect(await screen.findByText('1')).toBeInTheDocument();
    expect(await screen.findByText('12')).toBeInTheDocument();
  });

  it('renders chain list items', async () => {
    renderWithProviders(<ChainsPane />);
    expect(await screen.findByText('Correlated: Suspicious access')).toBeInTheDocument();
    expect(await screen.findByText('Correlated: Token abuse')).toBeInTheDocument();
  });

  it('renders status filter dropdown', async () => {
    renderWithProviders(<ChainsPane />);
    const select = await screen.findByLabelText('Filter by status');
    expect(select).toBeInTheDocument();
  });

  it('renders severity labels for chains', async () => {
    renderWithProviders(<ChainsPane />);
    expect(await screen.findByText('high')).toBeInTheDocument();
    expect(await screen.findByText('critical')).toBeInTheDocument();
  });

  it('renders detection count for chains', async () => {
    renderWithProviders(<ChainsPane />);
    expect(await screen.findByText('3')).toBeInTheDocument();
    expect(await screen.findByText('2')).toBeInTheDocument();
  });

  it('shows empty state when no chains', async () => {
    mockListChains.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      page_size: 25,
      has_next: false,
    });
    renderWithProviders(<ChainsPane />);
    expect(await screen.findByText('No investigation chains found')).toBeInTheDocument();
  });

  it('opens chain detail drawer when row clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ChainsPane />);
    const row = await screen.findByText('Correlated: Suspicious access');
    await user.click(row);

    await waitFor(() => {
      expect(mockGetChain).toHaveBeenCalledWith('chain-1');
    });
  });
});
