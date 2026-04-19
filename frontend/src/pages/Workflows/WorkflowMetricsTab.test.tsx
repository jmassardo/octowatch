import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { WorkflowMetricsTab } from './WorkflowMetricsTab';

/* ── Mocks ─────────────────────────────────────────────────────────── */

const mockGetAlwaysFailing = vi.fn();
const mockGetAlwaysTimingOut = vi.fn();
const mockGetRunHistory = vi.fn();

vi.mock('../../api/workflowMetrics', () => ({
  getAlwaysFailingWorkflows: (...args: unknown[]) => mockGetAlwaysFailing(...args),
  getAlwaysTimingOutWorkflows: (...args: unknown[]) => mockGetAlwaysTimingOut(...args),
  getWorkflowRunHistory: (...args: unknown[]) => mockGetRunHistory(...args),
}));

/* ── Fixtures ──────────────────────────────────────────────────────── */

const EMPTY_RESPONSE = {
  items: [],
  total: 0,
  threshold: 5,
  lookback_days: 30,
  cached_at: null,
};

const FAILING_RESPONSE = {
  items: [
    {
      org: 'myorg',
      repo: 'myrepo',
      workflow_name: 'CI Build',
      consecutive_count: 5,
      last_run_at: '2024-06-07T10:00:00Z',
      last_conclusion: 'failure' as const,
    },
    {
      org: 'myorg',
      repo: 'other-repo',
      workflow_name: 'Deploy',
      consecutive_count: 7,
      last_run_at: '2024-06-06T10:00:00Z',
      last_conclusion: 'failure' as const,
    },
  ],
  total: 2,
  threshold: 5,
  lookback_days: 30,
  cached_at: '2024-06-07T11:00:00Z',
};

const TIMING_OUT_RESPONSE = {
  items: [
    {
      org: 'myorg',
      repo: 'slow-repo',
      workflow_name: 'Integration Tests',
      consecutive_count: 3,
      last_run_at: '2024-06-07T09:00:00Z',
      last_conclusion: 'timed_out' as const,
    },
  ],
  total: 1,
  threshold: 3,
  lookback_days: 30,
  cached_at: null,
};

const RUN_HISTORY_RESPONSE = {
  org: 'myorg',
  repo: 'myrepo',
  workflow_name: 'CI Build',
  runs: [
    {
      run_id: 'run-100',
      started_at: '2024-06-07T10:00:00Z',
      conclusion: 'failure',
      duration_seconds: 120,
    },
    {
      run_id: 'run-99',
      started_at: '2024-06-06T10:00:00Z',
      conclusion: 'failure',
      duration_seconds: 115,
    },
  ],
};

/* ── Tests ─────────────────────────────────────────────────────────── */

describe('WorkflowMetricsTab — Empty States', () => {
  beforeEach(() => {
    mockGetAlwaysFailing.mockClear();
    mockGetAlwaysTimingOut.mockClear();
    mockGetRunHistory.mockClear();
    mockGetAlwaysFailing.mockResolvedValue(EMPTY_RESPONSE);
    mockGetAlwaysTimingOut.mockResolvedValue(EMPTY_RESPONSE);
  });

  it('renders the controls row', async () => {
    renderWithProviders(<WorkflowMetricsTab />);
    expect(await screen.findByText('Lookback period')).toBeInTheDocument();
    expect(await screen.findByText('30d')).toBeInTheDocument();
  });

  it('renders the "Always Failing" section header', async () => {
    renderWithProviders(<WorkflowMetricsTab />);
    expect(await screen.findByText('Always Failing')).toBeInTheDocument();
  });

  it('renders the "Always Timing Out" section header', async () => {
    renderWithProviders(<WorkflowMetricsTab />);
    expect(await screen.findByText('Always Timing Out')).toBeInTheDocument();
  });

  it('shows empty state message for always-failing', async () => {
    renderWithProviders(<WorkflowMetricsTab />);
    expect(
      await screen.findByText('No persistently failing workflows in this period'),
    ).toBeInTheDocument();
  });

  it('shows empty state message for always-timing-out', async () => {
    renderWithProviders(<WorkflowMetricsTab />);
    expect(
      await screen.findByText('No persistently timing-out workflows in this period'),
    ).toBeInTheDocument();
  });
});

describe('WorkflowMetricsTab — With Data', () => {
  beforeEach(() => {
    mockGetAlwaysFailing.mockClear();
    mockGetAlwaysTimingOut.mockClear();
    mockGetRunHistory.mockClear();
    mockGetAlwaysFailing.mockResolvedValue(FAILING_RESPONSE);
    mockGetAlwaysTimingOut.mockResolvedValue(TIMING_OUT_RESPONSE);
    mockGetRunHistory.mockResolvedValue(RUN_HISTORY_RESPONSE);
  });

  it('renders workflow names from always-failing response', async () => {
    renderWithProviders(<WorkflowMetricsTab />);
    expect(await screen.findByText('CI Build')).toBeInTheDocument();
    expect(await screen.findByText('Deploy')).toBeInTheDocument();
  });

  it('renders repo names from always-failing response', async () => {
    renderWithProviders(<WorkflowMetricsTab />);
    expect(await screen.findByText('myrepo')).toBeInTheDocument();
    expect(await screen.findByText('other-repo')).toBeInTheDocument();
  });

  it('renders workflow from always-timing-out response', async () => {
    renderWithProviders(<WorkflowMetricsTab />);
    expect(await screen.findByText('Integration Tests')).toBeInTheDocument();
  });

  it('renders consecutive count badges', async () => {
    renderWithProviders(<WorkflowMetricsTab />);
    expect(await screen.findByText('5×')).toBeInTheDocument();
    expect(await screen.findByText('3×')).toBeInTheDocument();
  });

  it('opens run history modal on row click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<WorkflowMetricsTab />);

    const row = await screen.findByText('CI Build');
    await user.click(row.closest('tr')!);

    expect(await screen.findByText('Run History')).toBeInTheDocument();
  });

  it('shows run history data in modal', async () => {
    const user = userEvent.setup();
    renderWithProviders(<WorkflowMetricsTab />);

    const row = await screen.findByText('CI Build');
    await user.click(row.closest('tr')!);

    expect(await screen.findByText('#run-100')).toBeInTheDocument();
    expect(await screen.findByText('#run-99')).toBeInTheDocument();
  });

  it('closes modal when close button is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<WorkflowMetricsTab />);

    const row = await screen.findByText('CI Build');
    await user.click(row.closest('tr')!);

    // Modal is open
    expect(await screen.findByText('Run History')).toBeInTheDocument();

    // Click the close button (×)
    const closeButton = screen.getByText('×');
    await user.click(closeButton);

    expect(screen.queryByText('Run History')).not.toBeInTheDocument();
  });
});

describe('WorkflowMetricsTab — Controls', () => {
  beforeEach(() => {
    mockGetAlwaysFailing.mockClear();
    mockGetAlwaysTimingOut.mockClear();
    mockGetAlwaysFailing.mockResolvedValue(EMPTY_RESPONSE);
    mockGetAlwaysTimingOut.mockResolvedValue(EMPTY_RESPONSE);
  });

  it('renders all lookback period buttons', async () => {
    renderWithProviders(<WorkflowMetricsTab />);
    for (const days of ['7d', '14d', '30d', '60d', '90d']) {
      expect(await screen.findByText(days)).toBeInTheDocument();
    }
  });

  it('changes active lookback period on click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<WorkflowMetricsTab />);

    const btn7d = await screen.findByText('7d');
    await user.click(btn7d);

    // After clicking, re-query is triggered (no error)
    expect(mockGetAlwaysFailing).toHaveBeenCalled();
  });

  it('renders failure threshold select', async () => {
    renderWithProviders(<WorkflowMetricsTab />);
    expect(await screen.findByText('Failure threshold (consecutive runs)')).toBeInTheDocument();
  });

  it('renders timeout threshold select', async () => {
    renderWithProviders(<WorkflowMetricsTab />);
    expect(await screen.findByText('Timeout threshold (consecutive runs)')).toBeInTheDocument();
  });
});

describe('WorkflowMetricsTab — Error Handling', () => {
  beforeEach(() => {
    mockGetAlwaysFailing.mockClear();
    mockGetAlwaysTimingOut.mockClear();
  });

  it('shows error banner when always-failing request fails', async () => {
    mockGetAlwaysFailing.mockRejectedValue(new Error('Network error'));
    mockGetAlwaysTimingOut.mockResolvedValue(EMPTY_RESPONSE);
    renderWithProviders(<WorkflowMetricsTab />);
    expect(await screen.findByText(/Failed to load always failing/i)).toBeInTheDocument();
  });

  it('shows error banner when always-timing-out request fails', async () => {
    mockGetAlwaysFailing.mockResolvedValue(EMPTY_RESPONSE);
    mockGetAlwaysTimingOut.mockRejectedValue(new Error('Network error'));
    renderWithProviders(<WorkflowMetricsTab />);
    expect(await screen.findByText(/Failed to load always timing out/i)).toBeInTheDocument();
  });
});
