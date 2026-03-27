import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { ReportsPage } from './index';

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
}));

describe('ReportsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders page title and subtitle', () => {
    renderWithProviders(<ReportsPage />);
    expect(screen.getByText('Reports')).toBeInTheDocument();
    expect(
      screen.getByText('On-demand metric reports with CSV export'),
    ).toBeInTheDocument();
  });

  it('renders all four report cards with correct titles', () => {
    renderWithProviders(<ReportsPage />);
    expect(
      screen.getByText('Monthly Security Posture — January 2024'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Engineering Velocity Q4 2023 — Executive Summary',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Access Review — Outside Collaborators and PAT Inventory',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('DORA Metrics — December 2023'),
    ).toBeInTheDocument();
  });

  it('renders date and page info for each report', () => {
    renderWithProviders(<ReportsPage />);
    expect(
      screen.getByText('Generated Jan 15, 2024 · 47 pages'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Generated Jan 1, 2024 · 12 pages'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Generated Dec 28, 2023 · 23 pages'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Generated Jan 2, 2024 · 8 pages'),
    ).toBeInTheDocument();
  });

  it('renders tags for reports', () => {
    renderWithProviders(<ReportsPage />);
    expect(screen.getByText('14 critical findings')).toBeInTheDocument();
    expect(screen.getByText('8 medium')).toBeInTheDocument();
    expect(screen.getByText('automated')).toBeInTheDocument();
    expect(screen.getByText('velocity')).toBeInTheDocument();
    expect(screen.getByText('847 deploys')).toBeInTheDocument();
    expect(screen.getByText('94.2% pipeline health')).toBeInTheDocument();
    expect(screen.getByText('47 collaborators')).toBeInTheDocument();
    expect(screen.getByText('12 expiring tokens')).toBeInTheDocument();
    expect(screen.getByText('quarterly')).toBeInTheDocument();
    expect(screen.getByText('Elite performer')).toBeInTheDocument();
    expect(screen.getByText('DORA')).toBeInTheDocument();
  });

  it('renders PDF and CSV buttons for each report card', () => {
    renderWithProviders(<ReportsPage />);
    const pdfButtons = screen.getAllByRole('button', { name: 'PDF' });
    const csvButtons = screen.getAllByRole('button', { name: 'CSV' });
    expect(pdfButtons).toHaveLength(4);
    expect(csvButtons).toHaveLength(4);
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
    const { exportReport } = await import('../../api/reports');
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    const pdfButtons = screen.getAllByRole('button', { name: 'PDF' });
    await user.click(pdfButtons[0]);
    expect(exportReport).toHaveBeenCalledWith('security_posture', 'pdf');
  });

  it('calls exportReport with csv format when CSV button is clicked', async () => {
    const { exportReport } = await import('../../api/reports');
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

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

  it('renders org-scoped tags on report cards', () => {
    renderWithProviders(<ReportsPage />);
    const acmeCorpLabels = screen.getAllByText('acme-corp');
    expect(acmeCorpLabels).toHaveLength(2);
    expect(screen.getByText('globex')).toBeInTheDocument();
  });
});
