import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { CompliancePage } from './index';

vi.mock('../../api/compliance', () => ({
  getComplianceSummary: vi.fn().mockResolvedValue({
    overall_score: 72.5,
    frameworks_tracked: 4,
    controls_passing: 15,
    controls_total: 20,
    critical_gaps: 5,
    last_assessment_date: '2024-01-15T00:00:00Z',
    frameworks: [
      {
        name: 'soc2',
        display_name: 'SOC 2 Type II',
        score: 80,
        controls_passing: 4,
        controls_total: 5,
        last_generated: '2024-01-15T00:00:00Z',
      },
      {
        name: 'iso27001',
        display_name: 'ISO 27001',
        score: 70,
        controls_passing: 3,
        controls_total: 5,
        last_generated: '2024-01-15T00:00:00Z',
      },
      {
        name: 'nist_csf',
        display_name: 'NIST CSF',
        score: 65,
        controls_passing: 3,
        controls_total: 5,
        last_generated: '2024-01-15T00:00:00Z',
      },
      {
        name: 'gdpr',
        display_name: 'GDPR',
        score: 75,
        controls_passing: 3,
        controls_total: 5,
        last_generated: '2024-01-15T00:00:00Z',
      },
    ],
  }),
  getFrameworkDetail: vi.fn().mockResolvedValue({
    name: 'soc2',
    display_name: 'SOC 2 Type II',
    score: 80,
    controls: [
      {
        control_id: 'CC6.1',
        title: 'Logical Access Controls',
        description: 'Access control test',
        status: 'pass',
        evidence_summary: 'role_changes: 10',
        last_checked: '2024-01-15T00:00:00Z',
        category: 'soc2',
      },
      {
        control_id: 'CC6.2',
        title: 'Authentication',
        description: 'Auth test',
        status: 'not_assessed',
        evidence_summary: '',
        last_checked: '2024-01-15T00:00:00Z',
        category: 'soc2',
      },
    ],
    last_generated: '2024-01-15T00:00:00Z',
  }),
  getPolicyChecks: vi.fn().mockResolvedValue({
    checks: [
      {
        check_name: 'branch_protection',
        display_name: 'Branch Protection on All Repos',
        status: 'pass',
        scope: 'repo',
        last_checked: '2024-01-15T00:00:00Z',
        details: '10 events found',
      },
      {
        check_name: '2fa_enforcement',
        display_name: '2FA Enforcement',
        status: 'fail',
        scope: 'org',
        last_checked: '2024-01-15T00:00:00Z',
        details: 'No evidence found',
      },
    ],
    last_run: '2024-01-15T00:00:00Z',
    checks_passing: 1,
    checks_total: 2,
  }),
  runPolicyChecks: vi.fn().mockResolvedValue({
    checks: [],
    last_run: '2024-01-15T00:00:00Z',
    checks_passing: 0,
    checks_total: 0,
  }),
  getGDPRSummary: vi.fn().mockResolvedValue({
    data_processing_activities: [
      {
        activity_name: 'Audit Event Collection',
        purpose: 'Security monitoring',
        legal_basis: 'Legitimate interest',
        data_categories: ['user identifiers'],
        retention_period: '365 days',
        status: 'active',
      },
    ],
    consent_tracking_enabled: true,
    dsr_requests_total: 5,
    dsr_requests_completed: 3,
    dsr_requests_pending: 2,
    breach_notification_readiness: [
      { item: 'Detection system active', complete: true },
      { item: 'DPO designated', complete: false },
    ],
    data_retention_compliant: true,
    erasure_requests_processed: 3,
    last_updated: '2024-01-15T00:00:00Z',
  }),
}));

vi.mock('../../api/reports', () => ({
  exportReport: vi.fn(),
}));

describe('CompliancePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the page header', async () => {
    renderWithProviders(<CompliancePage />, { route: '/compliance' });
    await waitFor(() => {
      expect(screen.getByText('Compliance Center')).toBeInTheDocument();
    });
  });

  it('renders summary metric cards', async () => {
    renderWithProviders(<CompliancePage />, { route: '/compliance' });
    await waitFor(() => {
      expect(screen.getByText('Overall Score')).toBeInTheDocument();
    });
    expect(screen.getByText('72.5%')).toBeInTheDocument();
    expect(screen.getByText('Frameworks Tracked')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('Controls Passing')).toBeInTheDocument();
    expect(screen.getByText('15 / 20')).toBeInTheDocument();
    expect(screen.getByText('Critical Gaps')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('Last Assessment')).toBeInTheDocument();
  });

  it('renders all tabs', async () => {
    renderWithProviders(<CompliancePage />, { route: '/compliance' });
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument();
    });
    expect(screen.getByRole('tab', { name: 'SOC 2' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'ISO 27001' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'NIST CSF' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'GDPR' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Policy Checks' })).toBeInTheDocument();
  });

  it('shows framework cards on overview tab', async () => {
    renderWithProviders(<CompliancePage />, { route: '/compliance' });
    await waitFor(() => {
      expect(screen.getByText('SOC 2 Type II')).toBeInTheDocument();
    });
    // "ISO 27001", "NIST CSF", "GDPR" appear both in tabs and cards
    expect(screen.getAllByText('ISO 27001').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('NIST CSF').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('GDPR').length).toBeGreaterThanOrEqual(2);
  });

  it('shows Generate All Reports button in header', async () => {
    renderWithProviders(<CompliancePage />, { route: '/compliance' });
    await waitFor(() => {
      expect(screen.getByText('Generate All Reports')).toBeInTheDocument();
    });
  });

  it('navigates to SOC 2 tab on click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CompliancePage />, { route: '/compliance' });

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'SOC 2' })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('tab', { name: 'SOC 2' }));

    await waitFor(() => {
      expect(screen.getByText('Generate Report')).toBeInTheDocument();
    });
  });

  it('navigates to framework tab from framework card click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CompliancePage />, { route: '/compliance' });

    await waitFor(() => {
      expect(screen.getByText('SOC 2 Type II')).toBeInTheDocument();
    });

    // Click the SOC 2 card
    await user.click(screen.getByText('SOC 2 Type II'));

    await waitFor(() => {
      expect(screen.getByText('Generate Report')).toBeInTheDocument();
    });
  });

  it('navigates to GDPR tab', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CompliancePage />, { route: '/compliance' });

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'GDPR' })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('tab', { name: 'GDPR' }));

    await waitFor(() => {
      expect(screen.getByText('Data Processing Activities')).toBeInTheDocument();
    });
  });

  it('renders GDPR processing activities', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CompliancePage />, { route: '/compliance' });

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'GDPR' })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('tab', { name: 'GDPR' }));

    await waitFor(() => {
      expect(screen.getByText('Audit Event Collection')).toBeInTheDocument();
    });
  });

  it('renders GDPR breach checklist', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CompliancePage />, { route: '/compliance' });

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'GDPR' })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('tab', { name: 'GDPR' }));

    await waitFor(() => {
      expect(screen.getByText('Detection system active')).toBeInTheDocument();
    });
    expect(screen.getByText('DPO designated')).toBeInTheDocument();
  });

  it('navigates to Policy Checks tab', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CompliancePage />, { route: '/compliance' });

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Policy Checks' })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('tab', { name: 'Policy Checks' }));

    await waitFor(() => {
      expect(screen.getByText('Run All Checks')).toBeInTheDocument();
    });
  });

  it('renders policy check data table', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CompliancePage />, { route: '/compliance' });

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Policy Checks' })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('tab', { name: 'Policy Checks' }));

    await waitFor(() => {
      expect(screen.getByText('Branch Protection on All Repos')).toBeInTheDocument();
    });
    expect(screen.getByText('2FA Enforcement')).toBeInTheDocument();
  });

  it('marks the active tab correctly', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CompliancePage />, { route: '/compliance' });

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument();
    });

    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true');

    await user.click(screen.getByRole('tab', { name: 'SOC 2' }));

    expect(screen.getByRole('tab', { name: 'SOC 2' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'false');
  });
});
