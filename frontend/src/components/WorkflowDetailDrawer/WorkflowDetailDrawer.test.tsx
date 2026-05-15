import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { WorkflowDetailDrawer } from './WorkflowDetailDrawer';
import type { WorkflowFailureSummary } from '../../api/workflowMetrics';

// ── Mocks ────────────────────────────────────────────────────────────────────

const mockGetRunHistory = vi.fn();

vi.mock('../../api/workflowMetrics', () => ({
  getAlwaysFailingWorkflows: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  getAlwaysTimingOutWorkflows: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  getWorkflowRunHistory: (...args: unknown[]) => mockGetRunHistory(...args),
}));

// ── Fixtures ─────────────────────────────────────────────────────────────────

const SAMPLE_WORKFLOW: WorkflowFailureSummary = {
  org: 'myorg',
  repo: 'myrepo',
  workflow_name: 'CI Build',
  consecutive_count: 5,
  last_run_at: '2024-06-07T10:00:00Z',
  last_conclusion: 'failure',
};

const TIMEOUT_WORKFLOW: WorkflowFailureSummary = {
  org: 'myorg',
  repo: 'slow-repo',
  workflow_name: 'Integration Tests',
  consecutive_count: 3,
  last_run_at: '2024-06-07T09:00:00Z',
  last_conclusion: 'timed_out',
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
    {
      run_id: 'run-98',
      started_at: '2024-06-05T10:00:00Z',
      conclusion: 'success',
      duration_seconds: 95,
    },
  ],
};

const EMPTY_RUN_HISTORY = {
  org: 'myorg',
  repo: 'myrepo',
  workflow_name: 'CI Build',
  runs: [],
};

// ── Tests ────────────────────────────────────────────────────────────────────

describe('WorkflowDetailDrawer', () => {
  beforeEach(() => {
    mockGetRunHistory.mockClear();
    mockGetRunHistory.mockResolvedValue(RUN_HISTORY_RESPONSE);
  });

  it('does not render when workflow is null', () => {
    renderWithProviders(
      <WorkflowDetailDrawer workflow={null} lookbackDays={30} onClose={() => {}} />,
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders the drawer with workflow name as title', async () => {
    renderWithProviders(
      <WorkflowDetailDrawer workflow={SAMPLE_WORKFLOW} lookbackDays={30} onClose={() => {}} />,
    );
    expect(await screen.findByText('CI Build')).toBeInTheDocument();
  });

  it('renders workflow metadata', async () => {
    renderWithProviders(
      <WorkflowDetailDrawer workflow={SAMPLE_WORKFLOW} lookbackDays={30} onClose={() => {}} />,
    );
    expect(await screen.findByText('Organization')).toBeInTheDocument();
    expect(screen.getByText('myorg')).toBeInTheDocument();
    expect(screen.getByText('Repository')).toBeInTheDocument();
    expect(screen.getByText('myrepo')).toBeInTheDocument();
    expect(screen.getByText('Last conclusion')).toBeInTheDocument();
  });

  it('renders failure pattern analysis section', async () => {
    renderWithProviders(
      <WorkflowDetailDrawer workflow={SAMPLE_WORKFLOW} lookbackDays={30} onClose={() => {}} />,
    );
    expect(await screen.findByText('Failure Pattern Analysis')).toBeInTheDocument();
  });

  it('displays pattern statistics', async () => {
    renderWithProviders(
      <WorkflowDetailDrawer workflow={SAMPLE_WORKFLOW} lookbackDays={30} onClose={() => {}} />,
    );
    // Wait for data to load
    expect(await screen.findByText('Failure Pattern Analysis')).toBeInTheDocument();
    // 67% fail rate (unique text)
    expect(screen.getByText('67%')).toBeInTheDocument();
    // Pattern summary includes the stats
    expect(screen.getByText(/2 of the last 3 runs failed/)).toBeInTheDocument();
  });

  it('renders pattern summary text', async () => {
    renderWithProviders(
      <WorkflowDetailDrawer workflow={SAMPLE_WORKFLOW} lookbackDays={30} onClose={() => {}} />,
    );
    expect(await screen.findByText(/2 of the last 3 runs failed/)).toBeInTheDocument();
  });

  it('renders recent runs section', async () => {
    renderWithProviders(
      <WorkflowDetailDrawer workflow={SAMPLE_WORKFLOW} lookbackDays={30} onClose={() => {}} />,
    );
    expect(await screen.findByText('Recent Runs (3)')).toBeInTheDocument();
  });

  it('renders View links for runs with run_id', async () => {
    renderWithProviders(
      <WorkflowDetailDrawer workflow={SAMPLE_WORKFLOW} lookbackDays={30} onClose={() => {}} />,
    );
    const links = await screen.findAllByText('View →');
    expect(links.length).toBe(3);
    expect(links[0]).toHaveAttribute(
      'href',
      'https://github.com/myorg/myrepo/actions/runs/run-100',
    );
  });

  it('renders remediation guidance section', async () => {
    renderWithProviders(
      <WorkflowDetailDrawer workflow={SAMPLE_WORKFLOW} lookbackDays={30} onClose={() => {}} />,
    );
    expect(await screen.findByText('Remediation Guidance')).toBeInTheDocument();
  });

  it('shows failure-specific suggestions for failure conclusion', async () => {
    renderWithProviders(
      <WorkflowDetailDrawer workflow={SAMPLE_WORKFLOW} lookbackDays={30} onClose={() => {}} />,
    );
    expect(await screen.findByText('Check recent code changes')).toBeInTheDocument();
    expect(await screen.findByText('Review build and test logs')).toBeInTheDocument();
  });

  it('shows timeout-specific suggestions for timed_out conclusion', async () => {
    mockGetRunHistory.mockResolvedValue({
      org: 'myorg',
      repo: 'slow-repo',
      workflow_name: 'Integration Tests',
      runs: [
        {
          run_id: 'run-50',
          started_at: '2024-06-07T09:00:00Z',
          conclusion: 'timed_out',
          duration_seconds: 21600,
        },
      ],
    });

    renderWithProviders(
      <WorkflowDetailDrawer workflow={TIMEOUT_WORKFLOW} lookbackDays={30} onClose={() => {}} />,
    );
    expect(await screen.findByText('Increase the workflow timeout')).toBeInTheDocument();
  });

  it('renders GitHub Actions link', async () => {
    renderWithProviders(
      <WorkflowDetailDrawer workflow={SAMPLE_WORKFLOW} lookbackDays={30} onClose={() => {}} />,
    );
    const link = await screen.findByText('View all runs on GitHub Actions →');
    expect(link).toHaveAttribute('href', 'https://github.com/myorg/myrepo/actions');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('closes when onClose is triggered', async () => {
    const user = userEvent.setup();
    const handleClose = vi.fn();
    renderWithProviders(
      <WorkflowDetailDrawer workflow={SAMPLE_WORKFLOW} lookbackDays={30} onClose={handleClose} />,
    );
    const panel = await screen.findByTestId('drawer-panel');
    const closeBtn = within(panel).getByRole('button', { name: /close/i });
    await user.click(closeBtn);
    expect(handleClose).toHaveBeenCalledOnce();
  });

  it('handles empty run history gracefully', async () => {
    mockGetRunHistory.mockResolvedValue(EMPTY_RUN_HISTORY);
    renderWithProviders(
      <WorkflowDetailDrawer workflow={SAMPLE_WORKFLOW} lookbackDays={30} onClose={() => {}} />,
    );
    expect(await screen.findByText('No runs found in this period.')).toBeInTheDocument();
  });

  it('shows error banner when API call fails', async () => {
    mockGetRunHistory.mockRejectedValue(new Error('Network error'));
    renderWithProviders(
      <WorkflowDetailDrawer workflow={SAMPLE_WORKFLOW} lookbackDays={30} onClose={() => {}} />,
    );
    expect(await screen.findByText('Failed to load run history')).toBeInTheDocument();
  });

  it('fetches run history with correct parameters', async () => {
    renderWithProviders(
      <WorkflowDetailDrawer workflow={SAMPLE_WORKFLOW} lookbackDays={14} onClose={() => {}} />,
    );
    await screen.findByText('Failure Pattern Analysis');
    expect(mockGetRunHistory).toHaveBeenCalledWith({
      org: 'myorg',
      repo: 'myrepo',
      workflow_name: 'CI Build',
      lookback_days: 14,
      limit: 20,
    });
  });

  it('uses accessible dialog role', async () => {
    renderWithProviders(
      <WorkflowDetailDrawer workflow={SAMPLE_WORKFLOW} lookbackDays={30} onClose={() => {}} />,
    );
    const panel = await screen.findByTestId('drawer-panel');
    expect(panel).toHaveAttribute('role', 'dialog');
    expect(panel).toHaveAttribute('aria-modal', 'true');
  });
});
