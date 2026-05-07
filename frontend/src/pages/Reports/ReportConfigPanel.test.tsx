import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { ReportConfigPanel } from './ReportConfigPanel';

vi.mock('../../hooks/useOrg', () => ({
  useOrg: vi.fn().mockReturnValue({ selectedOrg: '', setSelectedOrg: vi.fn() }),
}));

vi.mock('../../api/reports', () => ({
  runCustomReport: vi.fn().mockResolvedValue({
    report_id: 1,
    report_name: 'Test Report',
    data_sources: ['events'],
    generated_at: '2024-06-15T10:00:00Z',
    window_days: 30,
    org: null,
    data: [{ action: 'repos.create', actor: 'octocat' }],
    row_count: 1,
  }),
  exportReport: vi.fn(),
}));

describe('ReportConfigPanel', () => {
  const mockOnClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the config panel with template name', () => {
    renderWithProviders(
      <ReportConfigPanel
        template={{
          id: 'test',
          type: 'mau',
          title: 'Test Template Report',
          generated_at: null,
          status: 'available',
          tags: [],
        }}
        onClose={mockOnClose}
      />,
    );
    expect(screen.getByTestId('report-config-panel')).toBeInTheDocument();
    expect(screen.getByText('Test Template Report')).toBeInTheDocument();
  });

  it('renders time window preset buttons', () => {
    renderWithProviders(
      <ReportConfigPanel
        template={{
          id: 'test',
          type: 'mau',
          title: 'Test',
          generated_at: null,
          status: 'available',
          tags: [],
        }}
        onClose={mockOnClose}
      />,
    );
    expect(screen.getByRole('button', { name: 'Last 7 days' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Last 14 days' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Last 30 days' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Last 90 days' })).toBeInTheDocument();
  });

  it('renders date inputs for custom range', () => {
    renderWithProviders(
      <ReportConfigPanel
        template={{
          id: 'test',
          type: 'mau',
          title: 'Test',
          generated_at: null,
          status: 'available',
          tags: [],
        }}
        onClose={mockOnClose}
      />,
    );
    expect(screen.getByLabelText('Start date')).toBeInTheDocument();
    expect(screen.getByLabelText('End date')).toBeInTheDocument();
  });

  it('renders organization filter input', () => {
    renderWithProviders(
      <ReportConfigPanel
        template={{
          id: 'test',
          type: 'mau',
          title: 'Test',
          generated_at: null,
          status: 'available',
          tags: [],
        }}
        onClose={mockOnClose}
      />,
    );
    expect(screen.getByLabelText('Organization filter')).toBeInTheDocument();
  });

  it('renders granularity buttons', () => {
    renderWithProviders(
      <ReportConfigPanel
        template={{
          id: 'test',
          type: 'mau',
          title: 'Test',
          generated_at: null,
          status: 'available',
          tags: [],
        }}
        onClose={mockOnClose}
      />,
    );
    expect(screen.getByRole('button', { name: 'Daily' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Weekly' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Monthly' })).toBeInTheDocument();
  });

  it('renders Run Report button', () => {
    renderWithProviders(
      <ReportConfigPanel
        template={{
          id: 'test',
          type: 'mau',
          title: 'Test',
          generated_at: null,
          status: 'available',
          tags: [],
        }}
        onClose={mockOnClose}
      />,
    );
    expect(screen.getByRole('button', { name: 'Run Report' })).toBeInTheDocument();
  });

  it('close button calls onClose', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <ReportConfigPanel
        template={{
          id: 'test',
          type: 'mau',
          title: 'Test',
          generated_at: null,
          status: 'available',
          tags: [],
        }}
        onClose={mockOnClose}
      />,
    );

    await user.click(screen.getByRole('button', { name: '✕' }));
    expect(mockOnClose).toHaveBeenCalledOnce();
  });

  it('renders with custom report name', () => {
    renderWithProviders(
      <ReportConfigPanel
        customReport={{
          id: 1,
          name: 'My Custom Report',
          description: null,
          owner_login: 'testuser',
          data_sources: ['events'],
          columns: [],
          filters: [],
          grouping: { group_by: null, time_bucket: null },
          visualization: 'table',
          is_shared: false,
          shared_with: [],
          last_run_at: null,
          created_at: '2024-06-15T10:00:00Z',
          updated_at: '2024-06-15T10:00:00Z',
        }}
        onClose={mockOnClose}
      />,
    );
    expect(screen.getByText('My Custom Report')).toBeInTheDocument();
  });

  it('clicking window preset updates active button', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <ReportConfigPanel
        template={{
          id: 'test',
          type: 'mau',
          title: 'Test',
          generated_at: null,
          status: 'available',
          tags: [],
        }}
        onClose={mockOnClose}
      />,
    );

    const sevenDayButton = screen.getByRole('button', { name: 'Last 7 days' });
    await user.click(sevenDayButton);

    // The 7-day button should now have the active class
    expect(sevenDayButton.className).toContain('windowBtnActive');
  });

  it('renders export buttons for template reports', () => {
    renderWithProviders(
      <ReportConfigPanel
        template={{
          id: 'test',
          type: 'mau',
          title: 'Test',
          generated_at: null,
          status: 'available',
          tags: [],
        }}
        onClose={mockOnClose}
      />,
    );
    // Export buttons appear after running or for templates with type
    expect(screen.getByRole('button', { name: 'CSV' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'XLSX' })).toBeInTheDocument();
  });
});
