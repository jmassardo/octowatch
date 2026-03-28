import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { ReportsPage } from './index';

vi.mock('../../hooks/useOrg');

import { useOrg } from '../../hooks/useOrg';

const mockUseOrg = vi.mocked(useOrg);

vi.mock('../../api/reports', () => ({
  getMauReport: vi.fn().mockResolvedValue({
    report_type: 'mau',
    org: null,
    granularity: 'daily',
    window_days: 30,
    generated_at: '2024-01-15T00:00:00Z',
    data: [{ bucket: '2024-01-01', unique_actor_count: 42 }],
  }),
  getSeatUtilizationReport: vi.fn().mockResolvedValue({
    report_type: 'seat_utilization',
    org: null,
    granularity: 'daily',
    window_days: 30,
    generated_at: '2024-01-15T00:00:00Z',
    data: [{ bucket: '2024-01-01', active_seat_count: 10 }],
  }),
  getActionsVolumeReport: vi.fn().mockResolvedValue({
    report_type: 'actions_volume',
    org: null,
    granularity: 'daily',
    window_days: 30,
    generated_at: '2024-01-15T00:00:00Z',
    data: [
      { bucket: '2024-01-01', workflow_runs_total: 100 },
      { bucket: '2024-01-02', workflow_runs_total: 120 },
    ],
  }),
  getCopilotSeatsReport: vi.fn().mockResolvedValue({
    report_type: 'copilot_seats',
    org: null,
    granularity: 'daily',
    window_days: 30,
    generated_at: '2024-01-15T00:00:00Z',
    data: [{ bucket: '2024-01-01', seats_assigned: 5 }],
  }),
  exportReport: vi.fn(),
  getReportCatalog: vi.fn().mockResolvedValue([]),
}));

describe('ReportsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseOrg.mockReturnValue({ selectedOrg: '', setSelectedOrg: vi.fn() });
  });

  it('renders page title and subtitle', () => {
    renderWithProviders(<ReportsPage />);
    expect(screen.getByText('Reports')).toBeInTheDocument();
    expect(
      screen.getByText('On-demand metric reports with CSV export'),
    ).toBeInTheDocument();
  });

  it('shows empty state when no reports in catalog', async () => {
    renderWithProviders(<ReportsPage />);
    expect(
      await screen.findByText(/No reports generated yet/),
    ).toBeInTheDocument();
  });

  it('renders report cards from catalog API data', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'security_posture',
        title: 'Security Posture Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: ['security', 'automated'],
      },
      {
        id: 'report-2',
        type: 'dora_metrics',
        title: 'DORA Metrics Report',
        generated_at: '2024-06-14T08:00:00Z',
        status: 'completed',
        tags: ['dora'],
      },
    ]);

    renderWithProviders(<ReportsPage />);

    expect(await screen.findByText('Security Posture Report')).toBeInTheDocument();
    expect(screen.getByText('DORA Metrics Report')).toBeInTheDocument();
  });

  it('renders PDF and CSV buttons for catalog report cards', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'security_posture',
        title: 'Security Posture Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);

    renderWithProviders(<ReportsPage />);

    await screen.findByText('Security Posture Report');
    const pdfButtons = screen.getAllByRole('button', { name: 'PDF' });
    const csvButtons = screen.getAllByRole('button', { name: 'CSV' });
    expect(pdfButtons).toHaveLength(1);
    expect(csvButtons).toHaveLength(1);
  });

  it('renders window selector with 30d, 60d, 90d buttons', () => {
    renderWithProviders(<ReportsPage />);
    expect(screen.getByText('Window:')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '30d' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '60d' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '90d' }),
    ).toBeInTheDocument();
  });

  it('calls exportReport with pdf format when PDF button is clicked', async () => {
    const { exportReport, getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'security_posture',
        title: 'Security Posture Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    await screen.findByText('Security Posture Report');
    const pdfButtons = screen.getAllByRole('button', { name: 'PDF' });
    await user.click(pdfButtons[0]);
    expect(exportReport).toHaveBeenCalledWith('security_posture', 'pdf');
  });

  it('calls exportReport with csv format when CSV button is clicked', async () => {
    const { exportReport, getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'security_posture',
        title: 'Security Posture Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    await screen.findByText('Security Posture Report');
    const csvButtons = screen.getAllByRole('button', { name: 'CSV' });
    await user.click(csvButtons[0]);
    expect(exportReport).toHaveBeenCalledWith('security_posture', 'csv');
  });

  it('updates window days when selector buttons are clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    expect(screen.getByText(/last 30 days/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '60d' }));
    expect(screen.getByText(/last 60 days/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '90d' }));
    expect(screen.getByText(/last 90 days/)).toBeInTheDocument();
  });

  it('renders summary card with data bucket counts', async () => {
    renderWithProviders(<ReportsPage />);
    expect(screen.getByText(/Data summary/)).toBeInTheDocument();
    expect(screen.getByText('Total MAU buckets')).toBeInTheDocument();
    expect(screen.getByText('Actions buckets')).toBeInTheDocument();
    expect(screen.getByText('Seat util buckets')).toBeInTheDocument();
    expect(screen.getByText('Copilot seat buckets')).toBeInTheDocument();
  });

  it('renders org-scoped tags showing "All orgs" when no org is selected and catalog has items', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'security_posture',
        title: 'Test Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    renderWithProviders(<ReportsPage />);
    await screen.findByText('Test Report');
    const allOrgLabels = screen.getAllByText('All orgs');
    expect(allOrgLabels).toHaveLength(1);
  });

  it('renders org-scoped tags showing selected org name when catalog has items', async () => {
    mockUseOrg.mockReturnValue({ selectedOrg: 'my-org', setSelectedOrg: vi.fn() });
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'security_posture',
        title: 'Test Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    renderWithProviders(<ReportsPage />);
    await screen.findByText('Test Report');
    const orgLabels = screen.getAllByText('my-org');
    expect(orgLabels).toHaveLength(1);
  });

  it('summary values are clickable when numeric', async () => {
    const { container } = renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      const grid = container.querySelector('.summaryGrid')!;
      const clickableValues = grid.querySelectorAll('.clickableValue');
      expect(clickableValues.length).toBeGreaterThan(0);
    });
    const grid = container.querySelector('.summaryGrid')!;
    const clickableValues = grid.querySelectorAll('.clickableValue');
    clickableValues.forEach((el) => {
      expect(el.getAttribute('role')).toBe('button');
    });
  });

  it('clicking bucket value opens modal', async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(container.querySelector('.clickableValue')).not.toBeNull();
    });
    const clickable = container.querySelector('.clickableValue')!;
    await user.click(clickable);
    // Modal renders a table with bucket data columns
    expect(screen.getByRole('table')).toBeInTheDocument();
  });

  it('report titles have clickable styling when catalog has items', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'security_posture',
        title: 'Test Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    const { container } = renderWithProviders(<ReportsPage />);
    await screen.findByText('Test Report');
    const clickableTitles = container.querySelectorAll('.reportTitleClickable');
    expect(clickableTitles).toHaveLength(1);
    clickableTitles.forEach((el) => {
      expect(el.getAttribute('role')).toBe('button');
    });
  });
});
