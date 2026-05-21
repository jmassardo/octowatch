import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { WorkflowsPage } from './index';

/* ── Mocks ─────────────────────────────────────────────────────────── */

const mockListFindings = vi.fn();
const mockGetScores = vi.fn();
const mockGetScanStatus = vi.fn();

vi.mock('../../api/workflowScanner', () => ({
  listWorkflowFindings: (...args: unknown[]) => mockListFindings(...args),
  getRepoSecurityScores: (...args: unknown[]) => mockGetScores(...args),
  getScanStatus: (...args: unknown[]) => mockGetScanStatus(...args),
}));

vi.mock('../../api/workflowMetrics', () => ({
  getAlwaysFailingWorkflows: vi.fn().mockResolvedValue({ workflows: [], total: 0 }),
  getAlwaysTimingOutWorkflows: vi.fn().mockResolvedValue({ workflows: [], total: 0 }),
  getWorkflowRunHistory: vi.fn().mockResolvedValue({ runs: [], workflow_path: '' }),
}));

/* ── Fixtures ──────────────────────────────────────────────────────── */

const FINDINGS_RESPONSE = {
  findings: [
    {
      id: 1,
      org: 'myorg',
      repo: 'myrepo',
      workflow_path: '.github/workflows/ci.yml',
      rule_id: 'unpinned_action',
      severity: 'high',
      title: 'Unpinned third-party action',
      description: 'Action uses branch ref instead of SHA',
      recommendation: 'Pin to a specific SHA',
      snippet: 'uses: actions/checkout@main',
      first_seen: '2024-06-01T10:00:00Z',
      last_seen: '2024-06-07T10:00:00Z',
      status: 'open',
    },
    {
      id: 2,
      org: 'myorg',
      repo: 'other-repo',
      workflow_path: '.github/workflows/deploy.yml',
      rule_id: 'script_injection',
      severity: 'critical',
      title: 'Script injection risk',
      description: 'Untrusted input used in run step',
      recommendation: 'Use environment variable',
      snippet: 'run: echo ${{ github.event.issue.title }}',
      first_seen: '2024-06-02T10:00:00Z',
      last_seen: '2024-06-06T10:00:00Z',
      status: 'open',
    },
  ],
  total: 2,
};

const SCORES_RESPONSE = [
  {
    org: 'myorg',
    repo: 'myrepo',
    score: 65,
    finding_count: 3,
    critical_count: 0,
    high_count: 2,
  },
  {
    org: 'myorg',
    repo: 'secure-repo',
    score: 95,
    finding_count: 0,
    critical_count: 0,
    high_count: 0,
  },
];

const SCAN_STATUS_RESPONSE = {
  last_scan_at: '2024-06-07T04:00:00Z',
  last_scan_status: 'completed',
  total_scans: 42,
  total_findings: 5,
  repos_scanned: 3,
  next_scheduled_scan: 'Runs every 6 hours and on new audit-log events',
  is_automated: true,
};

/* ── Tests ─────────────────────────────────────────────────────────── */

describe('WorkflowsPage — Findings Tab', () => {
  beforeEach(() => {
    mockListFindings.mockClear();
    mockGetScores.mockClear();
    mockGetScanStatus.mockClear();
    mockListFindings.mockResolvedValue(FINDINGS_RESPONSE);
    mockGetScores.mockResolvedValue(SCORES_RESPONSE);
    mockGetScanStatus.mockResolvedValue(SCAN_STATUS_RESPONSE);
  });

  it('renders page title', async () => {
    renderWithProviders(<WorkflowsPage />);
    expect(await screen.findByText('Workflow Security Scanner')).toBeInTheDocument();
  });

  it('renders finding titles', async () => {
    renderWithProviders(<WorkflowsPage />);
    expect(await screen.findByText('Unpinned third-party action')).toBeInTheDocument();
    expect(await screen.findByText('Script injection risk')).toBeInTheDocument();
  });

  it('shows severity labels', async () => {
    renderWithProviders(<WorkflowsPage />);
    expect(await screen.findByText('high')).toBeInTheDocument();
    expect(await screen.findByText('critical')).toBeInTheDocument();
  });

  it('shows repo paths', async () => {
    renderWithProviders(<WorkflowsPage />);
    expect(await screen.findByText('myorg/myrepo')).toBeInTheDocument();
    expect(await screen.findByText('myorg/other-repo')).toBeInTheDocument();
  });

  it('renders empty state when no findings', async () => {
    mockListFindings.mockResolvedValue({ findings: [], total: 0 });
    renderWithProviders(<WorkflowsPage />);
    expect(await screen.findByText('No workflow findings yet')).toBeInTheDocument();
  });

  it('renders severity filter dropdown', async () => {
    renderWithProviders(<WorkflowsPage />);
    expect(await screen.findByDisplayValue('All severities')).toBeInTheDocument();
  });

  it('renders status filter dropdown', async () => {
    renderWithProviders(<WorkflowsPage />);
    expect(await screen.findByDisplayValue('All statuses')).toBeInTheDocument();
  });
});

describe('WorkflowsPage — Scores Tab', () => {
  beforeEach(() => {
    mockListFindings.mockClear();
    mockGetScores.mockClear();
    mockGetScanStatus.mockClear();
    mockListFindings.mockResolvedValue(FINDINGS_RESPONSE);
    mockGetScores.mockResolvedValue(SCORES_RESPONSE);
    mockGetScanStatus.mockResolvedValue(SCAN_STATUS_RESPONSE);
  });

  it('switches to scores tab and shows repo scores', async () => {
    const user = userEvent.setup();
    renderWithProviders(<WorkflowsPage />);
    const scoresTab = await screen.findByRole('button', { name: 'Repo Scores' });
    await user.click(scoresTab);
    expect(await screen.findByText('myorg/myrepo')).toBeInTheDocument();
    expect(await screen.findByText('myorg/secure-repo')).toBeInTheDocument();
  });

  it('shows score values', async () => {
    const user = userEvent.setup();
    renderWithProviders(<WorkflowsPage />);
    await user.click(await screen.findByRole('button', { name: 'Repo Scores' }));
    expect(await screen.findByText('65')).toBeInTheDocument();
    expect(await screen.findByText('95')).toBeInTheDocument();
  });

  it('shows finding counts on score cards', async () => {
    const user = userEvent.setup();
    renderWithProviders(<WorkflowsPage />);
    await user.click(await screen.findByRole('button', { name: 'Repo Scores' }));
    expect(await screen.findByText('3 findings')).toBeInTheDocument();
    expect(await screen.findByText('0 findings')).toBeInTheDocument();
  });
});

describe('WorkflowsPage — Error Handling', () => {
  beforeEach(() => {
    mockListFindings.mockClear();
    mockGetScores.mockClear();
    mockGetScanStatus.mockClear();
    mockGetScanStatus.mockResolvedValue(SCAN_STATUS_RESPONSE);
  });

  it('shows error banner on findings failure', async () => {
    mockListFindings.mockRejectedValue(new Error('Network error'));
    renderWithProviders(<WorkflowsPage />);
    expect(await screen.findByText('Failed to load findings')).toBeInTheDocument();
  });
});

describe('WorkflowsPage — Scan Status', () => {
  beforeEach(() => {
    mockListFindings.mockClear();
    mockGetScores.mockClear();
    mockGetScanStatus.mockClear();
    mockListFindings.mockResolvedValue(FINDINGS_RESPONSE);
    mockGetScores.mockResolvedValue(SCORES_RESPONSE);
  });

  it('displays scan status with last scan time', async () => {
    mockGetScanStatus.mockResolvedValue(SCAN_STATUS_RESPONSE);
    renderWithProviders(<WorkflowsPage />);
    expect(await screen.findByText(/3 repos/)).toBeInTheDocument();
    expect(await screen.findByText(/5 findings/)).toBeInTheDocument();
  });

  it('shows awaiting message when no scans have run', async () => {
    mockGetScanStatus.mockResolvedValue({
      ...SCAN_STATUS_RESPONSE,
      last_scan_at: null,
      last_scan_status: null,
    });
    renderWithProviders(<WorkflowsPage />);
    expect(
      await screen.findByText('Awaiting first scan — data will appear automatically'),
    ).toBeInTheDocument();
  });

  it('renders guidance box with automated scanning description', async () => {
    mockGetScanStatus.mockResolvedValue(SCAN_STATUS_RESPONSE);
    renderWithProviders(<WorkflowsPage />);
    expect(await screen.findByText(/Fully automated/)).toBeInTheDocument();
    expect(await screen.findByText(/every 6 hours/)).toBeInTheDocument();
  });

  it('deep links to scores tab via ?tab=scores query param', async () => {
    mockGetScanStatus.mockResolvedValue(SCAN_STATUS_RESPONSE);
    mockGetScores.mockResolvedValue(SCORES_RESPONSE);
    renderWithProviders(<WorkflowsPage />, { route: '/workflows?tab=scores' });

    expect(await screen.findByText('myorg/myrepo')).toBeInTheDocument();
  });

  it('deep links to a specific finding via ?finding= query param', async () => {
    mockGetScanStatus.mockResolvedValue(SCAN_STATUS_RESPONSE);
    mockListFindings.mockResolvedValue(FINDINGS_RESPONSE);
    renderWithProviders(<WorkflowsPage />, { route: '/workflows?finding=1' });

    // The detail panel should show the finding details (title appears in both table and panel)
    const titles = await screen.findAllByText('Unpinned third-party action');
    expect(titles.length).toBeGreaterThanOrEqual(2); // table row + panel header
    expect(screen.getByText('Action uses branch ref instead of SHA')).toBeInTheDocument();
  });

  it('applies severity filter from URL query param', async () => {
    mockGetScanStatus.mockResolvedValue(SCAN_STATUS_RESPONSE);
    mockListFindings.mockResolvedValue(FINDINGS_RESPONSE);
    renderWithProviders(<WorkflowsPage />, { route: '/workflows?severity=high' });

    await screen.findByText('Unpinned third-party action');
    // The severity filter select should have the value from URL
    expect(mockListFindings).toHaveBeenCalledWith(expect.objectContaining({ severity: 'high' }));
  });
});
